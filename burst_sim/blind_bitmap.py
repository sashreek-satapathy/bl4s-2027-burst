"""
Can we detect clustered bit flips WITHOUT knowing the chip's physical layout?

A real memory hides its layout: the logical address we read (word address, bit
number) is scrambled before it reaches a physical row and column. This script
injects physical clusters, hides them behind an unknown scramble, and gives the
analysis only what the microcontroller would log: pulse number, word address,
bit number.

SIMULATION ONLY. No beam data.

Run:  .venv/bin/python blind_bitmap.py     (writes figures/ and results_blind.json)
"""
import json
import os

import numpy as np
import matplotlib.pyplot as plt

from burst_sim import (poisson_sf_ge, components, save, HERE,
                       BLUE, ORANGE, AQUA, INK2)

ROW_BITS, SEL_BITS, BIT_BITS = 10, 7, 3      # 1024 rows, 128 words/row, 8-bit words
ROWS, NSEL, WBITS = 1 << ROW_BITS, 1 << SEL_BITS, 1 << BIT_BITS
COLS = NSEL * WBITS                          # 1024 physical columns
NBITS = ROWS * COLS                          # 1,048,576 bits
NSIG = NBITS - 1                             # possible non-zero pair signatures
DIRS = np.array([(0, 1), (1, 0), (1, 1), (1, -1)])


# ------------------------------------------------------------ hidden chip layout
class Chip:
    """Logical <-> physical mapping that the analysis is NOT allowed to see.

    Row and column-select address bits are permuted and inverted (a common
    kind of address scrambling). 'interleaved' places the 8 bits of a word 128
    columns apart; 'side_by_side' places them next to each other.
    """

    def __init__(self, rng, layout):
        self.layout = layout
        self.prow, self.psel = rng.permutation(ROW_BITS), rng.permutation(SEL_BITS)
        self.mrow, self.msel = rng.integers(0, ROWS), rng.integers(0, NSEL)

    @staticmethod
    def _unpermute(x, perm):
        out = np.zeros_like(x)
        for i, p in enumerate(perm):         # physical bit i came from logical bit p
            out |= ((x >> i) & 1) << p
        return out

    def to_logical(self, row, col):
        if self.layout == "interleaved":
            bit, sel = col // NSEL, col % NSEL
        else:
            sel, bit = col // WBITS, col % WBITS
        a_row = self._unpermute(row ^ self.mrow, self.prow)
        a_sel = self._unpermute(sel ^ self.msel, self.psel)
        return (a_row << SEL_BITS) | a_sel, bit      # word address, bit number


def inject(rng, n_pulses, rate, q):
    """Physical flips in line-shaped clusters; mean cluster size 1/(1-q)."""
    n_ev = rng.poisson(rate * (1 - q) * n_pulses)
    pulse = np.sort(rng.integers(0, n_pulses, n_ev))
    k = rng.geometric(1 - q, n_ev) if q > 0 else np.ones(n_ev, dtype=np.int64)
    d = DIRS[rng.integers(0, 4, n_ev)]
    idx = np.repeat(np.arange(n_ev), k)
    step = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
    row = (rng.integers(0, ROWS, n_ev)[idx] + step * d[idx, 0]) % ROWS
    col = (rng.integers(0, COLS, n_ev)[idx] + step * d[idx, 1]) % COLS
    return pulse[idx], row, col, k


def same_pulse_pairs(pulse):
    """All index pairs (i, j) of flips in the same pulse. pulse must be sorted."""
    a, b = [], []
    d = 1
    while True:
        same = pulse[d:] == pulse[:-d]
        if not same.any():
            break
        i = np.flatnonzero(same)
        a.append(i)
        b.append(i + d)
        d += 1
    if not a:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    return np.concatenate(a), np.concatenate(b)


# ------------------------------------------------------- analysis: layout known
def known_test(pulse, row, col):
    i, j = same_pulse_pairs(pulse)
    adj = (np.abs(row[i] - row[j]) <= 1) & (np.abs(col[i] - col[j]) <= 1)
    mu0 = i.size * 8 / NBITS
    return int(adj.sum()), mu0, poisson_sf_ge(int(adj.sum()), mu0), (i[adj], j[adj])


# ----------------------------------------------------- analysis: layout unknown
def signatures(pulse, addr, bit):
    """Signature of a pair = XOR of the two logical addresses (and bit numbers).
    Physical neighbours give the same few signatures again and again; unrelated
    pairs give a signature spread evenly over about a million values."""
    i, j = same_pulse_pairs(pulse)
    sig = ((addr[i] ^ addr[j]) << BIT_BITS) | (bit[i] ^ bit[j])
    keep = sig != 0
    return i[keep], j[keep], sig[keep]


def blind_test(pulse, addr, bit):
    """Count repeated signatures and compare with chance."""
    _, _, sig = signatures(pulse, addr, bit)
    _, cnt = np.unique(sig, return_counts=True)
    collisions = int(np.sum(cnt * (cnt - 1) // 2))
    lam0 = sig.size * (sig.size - 1) / 2 / NSIG
    return collisions, lam0, poisson_sf_ge(collisions, lam0)


def blind_clusters(pulse, addr, bit, family_alpha=0.01):
    """Learn which signatures mean 'physical neighbours', then rebuild clusters."""
    i, j, sig = signatures(pulse, addr, bit)
    u, inv, cnt = np.unique(sig, return_inverse=True, return_counts=True)
    mu = sig.size / NSIG
    kmin = 2
    while poisson_sf_ge(kmin, mu) * NSIG > family_alpha:
        kmin += 1
    learned = cnt >= kmin
    edge = learned[inv]
    lab = components(pulse.size, i[edge], j[edge])
    sizes = np.bincount(lab, minlength=pulse.size)
    return sizes[sizes > 0], int(learned.sum()), kmin, np.sort(cnt)[::-1]


def words_with_multiple_flips(pulse, addr):
    """Needs no layout at all: words holding 2+ flips after a single pulse."""
    _, cnt = np.unique(pulse.astype(np.int64) * (1 << 17) + addr, return_counts=True)
    return int(np.sum(cnt >= 2))


# ------------------------------------------------------------------------- main
def main():
    rng = np.random.default_rng(2027)
    res = {"note": "Simulated. The analysis sees only pulse, word address, bit number.",
           "memory_bits": NBITS}
    chip = Chip(rng, "interleaved")
    RATE, Q = 5.0, 1 / 3

    # ---- 1. Recovery of cluster sizes at three data-set sizes ----
    res["recovery"] = []
    rank_curves = {}
    for n_pulses in [400, 2000, 20000]:
        p, r, c, k = inject(rng, n_pulses, RATE, Q)
        a, b = chip.to_logical(r, c)
        sizes, n_learned, kmin, cnt = blind_clusters(p, a, b)
        _, _, _, (ei, ej) = known_test(p, r, c)
        lab = components(p.size, ei, ej)
        known_sizes = np.bincount(lab, minlength=p.size)
        known_sizes = known_sizes[known_sizes > 0]
        # shuffled control: same pulses, random logical addresses
        sa, sb = rng.integers(0, 1 << 17, p.size), rng.integers(0, WBITS, p.size)
        s_sizes, s_learned, _, s_cnt = blind_clusters(p, sa, sb)
        res["recovery"].append(dict(
            flips=int(p.size), injected_mean_cluster=float(k.mean()),
            layout_known_mean_cluster=float(known_sizes.mean()),
            blind_mean_cluster=float(sizes.mean()),
            blind_multi_cell_fraction=float(np.mean(sizes > 1)),
            injected_multi_cell_fraction=float(np.mean(k > 1)),
            signatures_learned=n_learned, min_repeats_required=kmin,
            shuffled_signatures_learned=s_learned,
            shuffled_blind_mean_cluster=float(s_sizes.mean())))
        rank_curves[int(p.size)] = (cnt[:300], s_cnt[:300])

    flips = max(rank_curves)
    cnt, s_cnt = rank_curves[flips]
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot(np.arange(1, cnt.size + 1), cnt, color=ORANGE, label="bursty data")
    ax.plot(np.arange(1, s_cnt.size + 1), s_cnt, color=AQUA, label="shuffled control")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("address-difference signature, ranked by how often it occurs")
    ax.set_ylabel("same-pulse pairs with that signature")
    ax.set_title("A few address differences repeat thousands of times")
    ax.legend()
    save(fig, "fig6_blind_signatures.png")

    # ---- 2. How many flips does the blind test need? ----
    ALPHA, REPS = 1e-3, 200
    means = [1.02, 1.05, 1.1, 1.2, 1.5]
    budgets = [100, 200, 500, 1000, 2000, 5000, 10000]
    power = {"blind": {}, "known": {}}
    for mk in means:
        q = 1 - 1 / mk
        pb, pk = [], []
        for nf in budgets:
            n_p = max(int(nf / RATE), 20)
            hb = hk = 0
            for _ in range(REPS):
                p, r, c, _ = inject(rng, n_p, RATE, q)
                a, b = chip.to_logical(r, c)
                hb += blind_test(p, a, b)[2] < ALPHA
                hk += known_test(p, r, c)[2] < ALPHA
            pb.append(hb / REPS)
            pk.append(hk / REPS)
        power["blind"][mk], power["known"][mk] = pb, pk

    def needed(pw):
        return next((b for b, v in zip(budgets, pw) if v >= 0.95), None)

    fp = 0
    for _ in range(2000):
        p, r, c, _ = inject(rng, 400, RATE, 0.0)
        a, b = chip.to_logical(r, c)
        fp += blind_test(p, a, b)[2] < 0.05
    res["power"] = dict(
        alpha=ALPHA, target_power=0.95, budgets=budgets,
        flips_needed_blind={str(m): needed(v) for m, v in power["blind"].items()},
        flips_needed_layout_known={str(m): needed(v) for m, v in power["known"].items()},
        blind_false_positive_rate_at_5pct=fp / 2000,
        curves={t: {str(m): v for m, v in d.items()} for t, d in power.items()})

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    shades = ["#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"]
    for ax, (t, ttl) in zip(axes, [("known", "Layout known (adjacent cells)"),
                                   ("blind", "Layout unknown (repeated signatures)")]):
        for mk, colr in zip(means, shades):
            ax.plot(budgets, power[t][mk], marker="o", color=colr, label=f"{mk:.2f}")
        ax.axhline(0.95, color=INK2, lw=1, ls="--")
        ax.set_xscale("log")
        ax.set_xlabel("total flips recorded")
        ax.set_title(ttl)
    axes[0].set_ylabel("chance of detecting the clustering")
    axes[1].legend(title="mean cluster size", loc="center left", bbox_to_anchor=(1.0, 0.5))
    save(fig, "fig7_blind_power.png")

    # ---- 3. Decoder-relevant measurement that needs no layout ----
    res["multi_flip_words"] = {}
    for layout in ["interleaved", "side_by_side"]:
        ch = Chip(rng, layout)
        p, r, c, k = inject(rng, 20000, RATE, Q)
        a, b = ch.to_logical(r, c)
        sa = rng.integers(0, 1 << 17, p.size)
        res["multi_flip_words"][layout] = dict(
            flips=int(p.size), words_with_2plus_flips=words_with_multiple_flips(p, a),
            shuffled_control=words_with_multiple_flips(p, sa))

    with open(os.path.join(HERE, "results_blind.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    out = {k: v for k, v in res.items() if k != "power"}
    out["power"] = {k: v for k, v in res["power"].items() if k != "curves"}
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
