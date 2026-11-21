"""
Write a fake beam-day log (see LOG_FORMAT.md) with a known truth, to test analyze_beam.py.

The fake chip is the reference ISSI SRAM model from decoder_chip.py: 2M x 16 bits,
hidden address scramble, line-shaped clusters. Flip rate follows the beam charge of
each pulse. Optional faults: one SEFI-like readout (hundreds of flips along one
physical row) and one incomplete readout.

Run:  ../.venv/bin/python fake_beam_log.py OUTDIR [--minutes 60] [--mean-cluster 1.2]
          [--layout side_by_side|interleaved] [--seed 1] [--no-faults] [--beam-off]
          [--bunching 0.3]
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from decoder_chip import Chip, ROWS, COLS, ADDR_BITS, BIT_BITS, DIRS  # noqa: E402

RATE_AT_30NC = 0.031      # flips per pulse per chip at 30 nC (section 8, 30 cm behind lead)
CHARGE_NC, CHARGE_CV = 30.0, 0.10
PULSE_HZ, READOUT_EVERY = 10, 10


def flips_for_chip(rng, charge, mean_size, gain=None):
    """Physical flips: (pulse, row, col). Events per pulse proportional to charge."""
    q = 1 - 1 / mean_size
    lam = RATE_AT_30NC * (1 - q) * charge / CHARGE_NC
    if gain is not None:
        lam = lam * gain
    n_per_pulse = rng.poisson(lam)
    pulse0 = np.repeat(np.arange(charge.size), n_per_pulse)
    n_ev = pulse0.size
    k = rng.geometric(1 - q, n_ev) if q > 0 else np.ones(n_ev, dtype=np.int64)
    d = DIRS[rng.integers(0, 4, n_ev)]
    idx = np.repeat(np.arange(n_ev), k)
    step = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
    row = (rng.integers(0, ROWS, n_ev)[idx] + step * d[idx, 0]) % ROWS
    col = (rng.integers(0, COLS, n_ev)[idx] + step * d[idx, 1]) % COLS
    return pulse0[idx], row, col, k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--mean-cluster", type=float, default=1.2)
    ap.add_argument("--layout", default="side_by_side", choices=["side_by_side", "interleaved"])
    ap.add_argument("--chips", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-faults", action="store_true")
    ap.add_argument("--beam-off", action="store_true")
    ap.add_argument("--bunching", type=float, default=0.0,
                    help="true time bunching: the upset rate wanders by this fraction "
                         "(slow random walk, about 1 minute memory)")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    os.makedirs(a.outdir, exist_ok=True)

    n_pulses = int(a.minutes * 60 * PULSE_HZ)
    charge = np.clip(rng.normal(CHARGE_NC, CHARGE_NC * CHARGE_CV, n_pulses), 0, None)
    if a.beam_off:
        charge[:] = 0.0
    chip = Chip(rng, a.layout)                       # same part number, same layout
    n_read = n_pulses // READOUT_EVERY
    sefi = (int(rng.integers(n_read // 4, 3 * n_read // 4)), 0) if not a.no_faults else None
    timeout = (int(rng.integers(0, n_read)), a.chips - 1) if not a.no_faults else None

    gain = None
    if a.bunching > 0:                               # AR(1) over pulses, ~600-pulse memory
        z, phi = np.zeros(n_pulses), 1 - 1 / 600
        e = rng.normal(0, np.sqrt(1 - phi ** 2), n_pulses)
        for t in range(1, n_pulses):
            z[t] = phi * z[t - 1] + e[t]
        gain = np.clip(1 + a.bunching * z, 0, None)
    flip_rows, read_rows, truth_k = {}, [], []
    for c in range(a.chips):
        p, r, col, k = flips_for_chip(rng, charge, a.mean_cluster, gain)
        truth_k.append(k)
        if sefi and c == sefi[1]:                    # SEFI: 400 cells along one row
            sp = sefi[0] * READOUT_EVERY + 3
            r = np.concatenate([r, np.full(400, rng.integers(ROWS))])
            col = np.concatenate([col, rng.choice(COLS, 400, replace=False)])
            p = np.concatenate([p, np.full(400, sp)])
        inside = p < n_read * READOUT_EVERY          # drop pulses after the last full readout
        p, r, col = p[inside], r[inside], col[inside]
        addr, bit = chip.to_logical(r, col)
        ro = p // READOUT_EVERY
        for rd, ad, b in zip(ro, addr, bit):
            key = (int(rd), c, int(ad))
            flip_rows[key] = flip_rows.get(key, 0) ^ (1 << int(b))
        for rd in range(n_read):
            p0, p1 = rd * READOUT_EVERY, rd * READOUT_EVERY + READOUT_EVERY - 1
            status, words = "ok", 1 << ADDR_BITS
            if timeout and (rd, c) == timeout:
                status, words = "timeout", 812345
            t0 = 1795000000 + p0 / PULSE_HZ
            read_rows.append([rd, c, p0, p1, round(float(charge[p0:p1 + 1].sum()), 3),
                              f"{t0 + 0.1:.2f}", f"{t0 + 0.95:.2f}", words, status])

    with open(os.path.join(a.outdir, "readouts.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["readout", "chip", "first_pulse", "last_pulse", "charge_nC",
                    "t_start", "t_end", "words_read", "status"])
        w.writerows(sorted(read_rows))
    with open(os.path.join(a.outdir, "flips.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["readout", "chip", "addr", "expected", "read"])
        for (rd, c, ad), x in sorted(flip_rows.items()):
            if x == 0:                               # two flips of the same bit cancel
                continue
            exp = 0x5555 if ad % 2 == 0 else 0xAAAA
            w.writerow([rd, c, ad, f"{exp:04x}", f"{exp ^ x:04x}"])
    run = dict(run=os.path.basename(os.path.normpath(a.outdir)),
               configuration="FAKE: W 2 cm + 10 cm lead, 90 deg, 30 cm",
               chips=a.chips, addr_bits=ADDR_BITS, word_bits=1 << BIT_BITS,
               fluence_per_nC=24400, pattern="checkerboard", beam=not a.beam_off)
    with open(os.path.join(a.outdir, "run.json"), "w") as f:
        json.dump(run, f, indent=1)
    k = np.concatenate(truth_k)
    truth = dict(layout=a.layout, time_bunching=a.bunching, mean_cluster_injected=float(k.mean()) if k.size else None,
                 multi_cell_fraction_injected=float(np.mean(k > 1)) if k.size else None,
                 flips_injected=int(k.sum()), sefi_readout_chip=sefi, timeout_readout_chip=timeout,
                 row_bit_of_physical_lsb=int(chip.prow[0]) + 9,
                 sel_bit_of_physical_lsb=int(chip.psel[0]),
                 sigma_true_cm2_per_bit=RATE_AT_30NC / (CHARGE_NC * 24400) / (1 << 25))
    with open(os.path.join(a.outdir, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)
    print(json.dumps(truth, indent=1))


if __name__ == "__main__":
    main()
