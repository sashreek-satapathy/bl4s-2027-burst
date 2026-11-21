"""
Error correction on the real reference chip, at the rates we expect at CLEAR.

Chip: ISSI IS61WV204816BLL, 2M words x 16 bits (32 Mbit), no on-chip ECC, so the
error-correcting code is ours: the microcontroller decides which memory bits form
one codeword. A single-error-correcting code fails when 2+ flips land in one
codeword between two scrubs (rewrites).

Questions:
 1. Do failures from ACCUMULATED independent flips matter at CLEAR rates?
 2. How do burst (multi-cell) failures depend on how we group bits into codewords?
 3. Can the chip's own first ~1,000 flips tell us a safe grouping, without its layout?

Model: physical array 4096 rows x 8192 columns. Logical address = 12 row bits + 9
column-select bits, scrambled by a hidden bit permutation and inversion. The 16 bits
of a word sit either 512 columns apart ("interleaved") or next to each other
("side_by_side"). Clusters are line-shaped with geometric sizes (an assumption).

Codeword groupings compared (all 16 bits, all software-defined):
 - word      : the 16 bits of one memory word
 - stride    : the same bit position in 16 words whose addresses differ in 4 chosen
               address bits (a cheap interleave); "random" = the 4 bits picked blind
 - learned   : the 4 address bits picked to avoid the address differences that the
               first 1,000 flips show to be physical neighbours

SIMULATION ONLY.  Run: .venv/bin/python decoder_chip.py
"""
import itertools
import json
import os

import numpy as np
import matplotlib.pyplot as plt

from burst_sim import HERE, BLUE, ORANGE, AQUA, INK2

ROW_BITS, SEL_BITS, BIT_BITS = 12, 9, 4
ROWS, NSEL, WBITS = 1 << ROW_BITS, 1 << SEL_BITS, 1 << BIT_BITS
COLS = NSEL * WBITS
ADDR_BITS = ROW_BITS + SEL_BITS                 # 21 -> 2M words
NWORDS = 1 << ADDR_BITS
DIRS = np.array([(0, 1), (1, 0), (1, 1), (1, -1)])

RATE = 0.031          # flips per pulse per chip: folded sigma(E), 30 cm behind lead, 30 nC
N_CHIPS = 2
READOUT_EVERY = 10    # pulses between read-and-rewrite (1 s at 10 Hz)
TRAIN_FLIPS = 1000    # flips used to learn the chip's neighbour signatures
TEST_FLIPS = 40000    # flips used to measure failure rates (simulation statistics only)
MEANS = [1.0, 1.02, 1.05, 1.1, 1.2, 1.5]
CHIPS_PER_POINT = 12  # independent hidden scrambles averaged per point
LABELS = {"word": "codeword = one memory word",
          "stride, random bits": "16 words, address bits picked blind",
          "stride, learned bits": "16 words, address bits learned from data"}
ALL_MASKS = [sum(1 << b for b in c) for c in itertools.combinations(range(ADDR_BITS), 4)]


class Chip:
    def __init__(self, rng, layout):
        self.layout = layout
        self.prow, self.psel = rng.permutation(ROW_BITS), rng.permutation(SEL_BITS)
        self.mrow, self.msel = rng.integers(0, ROWS), rng.integers(0, NSEL)

    @staticmethod
    def _unpermute(x, perm):
        out = np.zeros_like(x)
        for i, p in enumerate(perm):
            out |= ((x >> i) & 1) << p
        return out

    def to_logical(self, row, col):
        if self.layout == "interleaved":
            bit, sel = col // NSEL, col % NSEL
        else:
            sel, bit = col // WBITS, col % WBITS
        a_row = self._unpermute(row ^ self.mrow, self.prow)
        a_sel = self._unpermute(sel ^ self.msel, self.psel)
        return (a_row << SEL_BITS) | a_sel, bit


def inject(rng, n_pulses, rate, mean_size):
    q = 1 - 1 / mean_size
    n_ev = rng.poisson(rate * (1 - q) * n_pulses)
    pulse = rng.integers(0, n_pulses, n_ev)
    k = rng.geometric(1 - q, n_ev) if q > 0 else np.ones(n_ev, dtype=np.int64)
    d = DIRS[rng.integers(0, 4, n_ev)]
    idx = np.repeat(np.arange(n_ev), k)
    step = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
    row = (rng.integers(0, ROWS, n_ev)[idx] + step * d[idx, 0]) % ROWS
    col = (rng.integers(0, COLS, n_ev)[idx] + step * d[idx, 1]) % COLS
    return pulse[idx], row, col


def run_data(rng, chips, n_pulses, mean_size):
    """Flips from all chips: readout window, chip id, logical address, bit number."""
    w, c, a, b = [], [], [], []
    for cid, chip in enumerate(chips):
        p, r, cc = inject(rng, n_pulses, RATE, mean_size)
        addr, bit = chip.to_logical(r, cc)
        w.append(p // READOUT_EVERY)
        c.append(np.full(p.size, cid))
        a.append(addr)
        b.append(bit)
    return [np.concatenate(x) for x in (w, c, a, b)]


def failures(win, cid, addr, bit, scheme, mask=0):
    """Codewords holding 2+ flips within one readout window."""
    if scheme == "word":
        key = addr
    else:                                       # stride: zero the 4 grouping bits
        key = ((addr & ~mask) << BIT_BITS) | bit
    key = (win.astype(np.int64) << 30 | cid.astype(np.int64) << 26) * (1 << 26) + key
    _, cnt = np.unique(key, return_counts=True)
    return int(np.sum(cnt >= 2))


def learned_signatures(win, cid, addr, bit):
    """Address differences (same bit number) seen 2+ times among same-window pairs."""
    order = np.lexsort((cid, win))
    g = (win[order].astype(np.int64) << 8) | cid[order]
    a, b = addr[order], bit[order]
    sigs = []
    d = 1
    while d < g.size:
        same = g[d:] == g[:-d]
        if not same.any():
            break
        i = np.flatnonzero(same)
        s = a[i] ^ a[i + d]
        sigs.append(s[(b[i] == b[i + d]) & (s != 0)])
        d += 1
    if not sigs:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    u, cnt = np.unique(np.concatenate(sigs), return_counts=True)
    return u[cnt >= 2], cnt[cnt >= 2]


def choose_bits(rng, sigs, cnt):
    """Pick the 4 address bits that take part least in the learned neighbour
    differences. Physical neighbours differ in the low physical address bits, so
    these show up in learned signatures; high physical bits never do."""
    score = np.array([(cnt * ((sigs >> b) & 1)).sum() for b in range(ADDR_BITS)], float)
    score += rng.random(ADDR_BITS) * 0.5          # random tie-break
    return sum(1 << int(b) for b in np.argsort(score)[:4])


def main():
    rng = np.random.default_rng(2027)
    res = {"note": "Simulated. Reference chip organisation, Logan's folded rate, "
                   "assumed line-shaped clusters.",
           "rate_flips_per_pulse_per_chip": RATE, "chips": N_CHIPS,
           "readout_every_pulses": READOUT_EVERY}

    # ---- 1. accumulation of independent flips ----
    flips_run = 2000
    per_chip = flips_run / N_CHIPS
    per_window = RATE * READOUT_EVERY
    res["accumulation"] = dict(
        flips_per_chip_per_readout=per_window,
        expected_word_failures_whole_run_with_readout_scrub=
            N_CHIPS * (per_chip / per_window) * per_window ** 2 / 2 / NWORDS,
        expected_word_failures_whole_run_never_scrubbed=N_CHIPS * per_chip ** 2 / 2 / NWORDS,
        note="Two independent flips in one codeword. Effectively zero at CLEAR rates, "
             "so scrubbing has nothing to fix in this experiment.")

    # ---- 2 and 3. burst failures by grouping ----
    test_pulses = int(TEST_FLIPS / RATE / N_CHIPS)
    train_pulses = int(TRAIN_FLIPS / RATE / N_CHIPS)
    out = {}
    for layout in ["interleaved", "side_by_side"]:
        out[layout] = {}
        for m in MEANS:
            acc = {"word": [], "stride, random bits": [], "stride, learned bits": [],
                   "random-bit stride choices that are bad": [], "signatures learned": []}
            for _ in range(CHIPS_PER_POINT):
                chip = Chip(rng, layout)            # same part number = same layout
                chips = [chip] * N_CHIPS
                tr = run_data(rng, chips, train_pulses, m)
                te = run_data(rng, chips, test_pulses, m)
                n_te = te[0].size
                sigs, scnt = learned_signatures(*tr)
                learned = choose_bits(rng, sigs, scnt)
                rand = [ALL_MASKS[i] for i in rng.choice(len(ALL_MASKS), 40, replace=False)]
                f_rand = np.array([failures(*te, "stride", mk) for mk in rand]) / n_te * 1000
                acc["word"].append(failures(*te, "word") / n_te * 1000)
                acc["stride, random bits"].append(f_rand.mean())
                acc["random-bit stride choices that are bad"].append(np.mean(f_rand > 1.0))
                acc["stride, learned bits"].append(failures(*te, "stride", learned) / n_te * 1000)
                acc["signatures learned"].append(sigs.size)
            out[layout][str(m)] = {k: float(np.mean(v)) for k, v in acc.items()}
            print(layout, m, {k: round(v, 3) for k, v in out[layout][str(m)].items()})
    res["failures_per_1000_flips"] = out
    res["train_flips"], res["test_flips_per_point"] = TRAIN_FLIPS, TEST_FLIPS

    # ---- figure ----
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for ax, layout, ttl in zip(axes, ["side_by_side", "interleaved"],
                               ["Word bits side by side", "Word bits 512 columns apart"]):
        for key, colr, mk in [("word", ORANGE, "o"), ("stride, random bits", BLUE, "s"),
                              ("stride, learned bits", AQUA, "^")]:
            ax.plot(MEANS, [out[layout][str(m)][key] for m in MEANS], marker=mk,
                    color=colr, label=LABELS[key])
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_xlabel("mean cluster size")
        ax.set_title(ttl)
        ax.grid(True, color=INK2, alpha=0.15)
    axes[0].set_ylabel("codeword failures per 1,000 flips")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    fig.suptitle("Which bits share a codeword decides whether bursts break it", x=0.06,
                 ha="left", fontweight="bold")
    fig.savefig(os.path.join(HERE, "figures", "fig11_decoder_real_chip.png"), dpi=200)
    plt.close(fig)

    with open(os.path.join(HERE, "results_decoder_chip.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    print(json.dumps(res["accumulation"], indent=1))


if __name__ == "__main__":
    main()
