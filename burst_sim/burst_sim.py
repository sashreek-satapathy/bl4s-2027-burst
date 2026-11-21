"""
BURST fault-injection study (BL4S 2027 preliminary evidence).

Everything here is SIMULATION. No beam data exists yet. We inject bit flips with
a known amount of clustering into a virtual memory, then run the exact analysis
we would run on CLEAR data and check that it recovers what we injected.

Run:  .venv/bin/python burst_sim.py        (writes figures/ and results.json)
"""
import json
import os
from itertools import product

import numpy as np
import math
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# --------------------------------------------- small statistics helpers (no scipy)
def chi2_sf(x, dof):
    """Upper tail of chi-square (Wilson-Hilferty; accurate for dof > 30)."""
    z = ((x / dof) ** (1 / 3) - (1 - 2 / (9 * dof))) / math.sqrt(2 / (9 * dof))
    return 0.5 * math.erfc(z / math.sqrt(2))


def poisson_pmf(k, mu):
    k = np.asarray(k, float)
    lg = np.array([math.lgamma(v + 1) for v in k.ravel()]).reshape(k.shape)
    return np.exp(k * np.log(mu) - mu - lg)


def poisson_sf_ge(k, mu):
    """P(X >= k) for X ~ Poisson(mu), summed exactly in the upper tail."""
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    top = int(max(k, mu) + 12 * math.sqrt(max(k, mu)) + 60)
    return float(min(1.0, poisson_pmf(np.arange(k, top), mu).sum()))


def components(n, a, b):
    """Connected-component label of each of n nodes, given edges a-b."""
    lab = np.arange(n)
    while True:
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        if np.array_equal(new, lab):
            return lab
        lab = new


# ----------------------------------------------------------------- memory model
ROWS, COLS = 1024, 896           # physical bit grid (917,504 bits, about 1 Mbit)
NBITS = ROWS * COLS
WORD = 7                         # Hamming(7,4) codeword length
WORDS_PER_ROW = COLS // WORD     # 128
# Line-shaped clusters: a secondary particle crossing the die at an angle.
DIRS = np.array([(0, 1), (1, 0), (1, 1), (1, -1)])
# Forward half of the 8-neighbourhood (each adjacent pair counted once).
FWD = [(0, 1), (1, -1), (1, 0), (1, 1)]

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)


def make_cluster(rng, r0, c0, k, shape="compact"):
    """Generate a connected cluster and clip it to the physical memory grid."""
    if k <= 0:
        return []

    cells = [(0, 0)]
    occupied = {(0, 0)}

    if shape == "line":
        dr, dc = DIRS[rng.integers(0, len(DIRS))]
        cells = [(i * int(dr), i * int(dc)) for i in range(k)]

    elif shape == "diagonal":
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        dr, dc = directions[rng.integers(0, len(directions))]
        cells = [(i * dr, i * dc) for i in range(k)]

    elif shape == "compact":
        # Grow by adding an unoccupied 8-neighbour of an existing cell.
        neighbours = [
            (dr, dc)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr, dc) != (0, 0)
        ]

        while len(cells) < k:
            base_r, base_c = cells[rng.integers(0, len(cells))]
            dr, dc = neighbours[rng.integers(0, len(neighbours))]
            candidate = (base_r + dr, base_c + dc)

            if candidate not in occupied:
                occupied.add(candidate)
                cells.append(candidate)

    elif shape == "branch":
        # Grow from existing cells in one of the four DIRS directions.
        while len(cells) < k:
            base_r, base_c = cells[rng.integers(0, len(cells))]
            dr, dc = DIRS[rng.integers(0, len(DIRS))]
            candidate = (base_r + int(dr), base_c + int(dc))

            if candidate not in occupied:
                occupied.add(candidate)
                cells.append(candidate)

    else:
        raise ValueError(f"Unknown cluster shape: {shape}")

    # Translate to the seed location and clip at the chip boundary.
    result = []
    for dr, dc in cells:
        row = r0 + dr
        col = c0 + dc

        if 0 <= row < ROWS and 0 <= col < COLS:
            result.append((row, col))

    return result


def generate(rng, n_pulses, rate, q=0.0, charge_cv=0.0,
             shape_probs=None):
    """Inject flips. Returns (pulse, row, col, true_cluster_sizes, charge).

    rate       : mean flipped bits per pulse at nominal charge
    q          : burst strength. Cluster size k has P(k) = (1-q) q^(k-1)
    charge_cv  : pulse-to-pulse relative jitter of the bunch charge
    shape_probs: optional dictionary of cluster shape probabilities.
                 Defaults to compact clusters only.
    """
    if not 0 <= q < 1:
        raise ValueError("q must satisfy 0 <= q < 1")

    charge = np.ones(n_pulses)
    if charge_cv > 0:
        shape = 1.0 / charge_cv**2
        charge = rng.gamma(shape, 1.0 / shape, n_pulses)

    mean_k = 1.0 / (1.0 - q)
    n_events = rng.poisson(rate / mean_k * charge)
    ev_pulse = np.repeat(np.arange(n_pulses), n_events)
    n_ev = ev_pulse.size

    target_sizes = (
        rng.geometric(1.0 - q, n_ev)
        if q > 0
        else np.ones(n_ev, dtype=int)
    )

    if shape_probs is None:
        shape_names = ["compact"]
        probabilities = np.array([1.0])
    else:
        if not shape_probs:
            raise ValueError("shape_probs cannot be empty")

        shape_names = list(shape_probs.keys())
        probabilities = np.asarray(
            list(shape_probs.values()), dtype=float
        )

        if (
            np.any(probabilities < 0)
            or not np.all(np.isfinite(probabilities))
            or not np.isclose(probabilities.sum(), 1.0)
        ):
            raise ValueError("shape_probs must be non-negative and sum to 1")

    all_pulses = []
    all_rows = []
    all_cols = []
    actual_sizes = []

    for event in range(n_ev):
        r0 = int(rng.integers(0, ROWS))
        c0 = int(rng.integers(0, COLS))

        shape_index = rng.choice(len(shape_names), p=probabilities)
        cluster_shape = shape_names[shape_index]

        cells = make_cluster(
            rng, r0, c0, int(target_sizes[event]), cluster_shape
        )

        actual_sizes.append(len(cells))

        for row, col in cells:
            all_pulses.append(ev_pulse[event])
            all_rows.append(row)
            all_cols.append(col)

    return (
        np.asarray(all_pulses, dtype=int),
        np.asarray(all_rows, dtype=int),
        np.asarray(all_cols, dtype=int),
        np.asarray(actual_sizes, dtype=int),
        charge,
    )


def shuffle_control(rng, pulse):
    """Same number of flips in every pulse, addresses redrawn at random."""
    n = pulse.size
    return pulse, rng.integers(0, ROWS, n), rng.integers(0, COLS, n)


def cell_key(pulse, row, col):
    return (pulse.astype(np.int64) * ROWS + row) * COLS + col


# ------------------------------------------------------------------- analysis 1
def fano_test(counts, charge=None):
    """Dispersion index of flips per pulse, tested against Poisson.

    If the per-pulse charge is given, the Poisson mean is allowed to scale with
    it (this is what the beam charge monitor is for).
    """
    counts = np.asarray(counts, float)
    n = counts.size
    if charge is None:
        mu = np.full(n, counts.mean())
    else:
        mu = counts.sum() * charge / charge.sum()
    chi2 = np.sum((counts - mu) ** 2 / mu)
    return chi2 / (n - 1), chi2_sf(chi2, n - 1)


# ------------------------------------------------------------------- analysis 2
def adjacent_pairs(pulse, row, col):
    """Index pairs of flips that are 8-neighbours within the same pulse."""
    key = cell_key(pulse, row, col)
    order = np.argsort(key)
    skey = key[order]
    a_all, b_all = [], []
    for dr, dc in FWD:
        r2, c2 = row + dr, col + dc
        ok = (r2 < ROWS) & (c2 >= 0) & (c2 < COLS)
        k2 = cell_key(pulse[ok], r2[ok], c2[ok])
        pos = np.searchsorted(skey, k2)
        pos[pos == skey.size] = 0
        hit = skey[pos] == k2
        a_all.append(np.flatnonzero(ok)[hit])
        b_all.append(order[pos[hit]])
    return np.concatenate(a_all), np.concatenate(b_all)


def cluster_sizes(pulse, row, col):
    """Group flips into connected clusters; return the size of each cluster."""
    n = pulse.size
    a, b = adjacent_pairs(pulse, row, col)
    sizes = np.bincount(components(n, a, b), minlength=n)
    return sizes[sizes > 0]


def adjacency_test(pulse, row, col, n_pulses):
    """Observed adjacent pairs vs the number expected from independent flips."""
    a, _ = adjacent_pairs(pulse, row, col)
    n_p = np.bincount(pulse, minlength=n_pulses).astype(float)
    # 4 forward neighbours per cell, each occupied with probability ~N/NBITS
    mu0 = np.sum(n_p * (n_p - 1)) * len(FWD) / NBITS
    return a.size, mu0, poisson_sf_ge(a.size, mu0)


# ------------------------------------------------------------------- analysis 3
def hamming74_fails_iff_two_or_more():
    """Brute-force check: Hamming(7,4) decodes wrongly for every error pattern
    of weight >= 2 and correctly for weight <= 1. So 'word failure' can be
    counted as '>= 2 flipped bits in one codeword'."""
    H = np.array([[(j >> i) & 1 for j in range(1, 8)] for i in range(3)])
    for e in product([0, 1], repeat=7):
        e = np.array(e)
        s = H @ e % 2
        pos = s[0] + 2 * s[1] + 4 * s[2]
        fixed = e.copy()
        if pos:
            fixed[pos - 1] ^= 1
        if fixed.any() != (e.sum() >= 2):
            return False
    return True


def word_failures(pulse, row, col, layout, scrub_id=None):
    """Count Hamming(7,4) words left uncorrectable.

    layout   : 'contiguous'  - the 7 bits of a word are physical neighbours
               'interleaved' - the 7 bits of a word sit 128 columns apart
    scrub_id : scrub interval index of each flip (default: scrub every pulse).
               Flips accumulate inside an interval; a cell hit twice flips back.
    """
    if scrub_id is None:
        scrub_id = pulse
    cell = cell_key(scrub_id, row, col)
    u, cnt = np.unique(cell, return_counts=True)
    u = u[cnt % 2 == 1]
    c = u % COLS
    rest = u // COLS                       # (scrub interval, row)
    w = c // WORD if layout == "contiguous" else c % WORDS_PER_ROW
    _, per_word = np.unique(rest * WORDS_PER_ROW + w, return_counts=True)
    return int(np.sum(per_word >= 2))


# ------------------------------------------------------------------- analysis 4
def scrub_schedule(counts, budget, adaptive, alpha=0.2):
    """Decide after which pulses to scrub the memory.

    fixed    : every T pulses.
    adaptive : an exponentially weighted estimate of the flip rate sets the
               interval, T = gain / rate, so we scrub faster when the beam is
               hotter. The gain is tuned by bisection to spend the same total
               number of scrubs as the fixed schedule (fair comparison).
    Returns the scrub-interval index of every pulse and the scrubs used.
    """
    n = counts.size
    if not adaptive:
        T = n / budget
        sid = (np.arange(n) // T).astype(np.int64)
        return sid, int(sid[-1]) + 1

    def run(gain):
        sid = np.empty(n, np.int64)
        est, cur, since = counts[:20].mean() + 1e-9, 0, 0
        for i in range(n):
            sid[i] = cur
            est = (1 - alpha) * est + alpha * counts[i]
            since += 1
            if since >= max(1.0, gain / max(est, 1e-9)):
                cur, since = cur + 1, 0
        return sid, cur + 1

    lo, hi = 1e-3, 1e7
    for _ in range(60):
        mid = np.sqrt(lo * hi)
        if run(mid)[1] > budget:
            lo = mid
        else:
            hi = mid
    return run(hi)


# ---------------------------------------------------------------------- figures
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "savefig.facecolor": "#fcfcfb", "font.size": 10, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED,
    "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 6,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, name), dpi=200)
    plt.close(fig)


# ------------------------------------------------------------------------- main
def main():
    rng = np.random.default_rng(2027)
    res = {"note": "Simulated fault-injection study. Not beam data.",
           "memory_bits": NBITS}
    assert hamming74_fails_iff_two_or_more()
    res["hamming74_fails_iff_>=2_flips"] = True

    # ---- 1. Time structure: are counts per pulse Poisson? ----
    NP, RATE = 5000, 20.0
    cases = {
        "independent": dict(q=0.0, charge_cv=0.0),
        "bursty (mean cluster 1.5)": dict(q=1 / 3, charge_cv=0.0),
        "independent + 10% charge jitter": dict(q=0.0, charge_cv=0.10),
    }
    res["fano"] = {}
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, (name, kw), colr in zip(axes, cases.items(), [BLUE, ORANGE, AQUA]):
        p, r, c, k, charge = generate(rng, NP, RATE, **kw)
        counts = np.bincount(p, minlength=NP)
        F, pv = fano_test(counts)
        Fc, pvc = fano_test(counts, charge)
        q = kw["q"]
        res["fano"][name] = dict(
            fano=F, p_value=pv, fano_charge_normalised=Fc,
            p_value_charge_normalised=pvc, fano_expected_from_injection=(1 + q) / (1 - q)
            if kw["charge_cv"] == 0 else 1 + RATE * kw["charge_cv"] ** 2)
        bins = np.arange(counts.min(), counts.max() + 2) - 0.5
        ax.hist(counts, bins=bins, density=True, color=colr, alpha=0.85,
                edgecolor="#fcfcfb", linewidth=0.4)
        x = np.arange(0, counts.max() + 1)
        ax.plot(x, poisson_pmf(x, counts.mean()), color=INK, lw=1.5,
                label="Poisson, same mean")
        ax.set_title(name)
        ax.set_xlabel("flipped bits in one pulse")
        ax.text(0.97, 0.80, f"Fano factor = {F:.2f}\n(Poisson gives 1.00)",
                transform=ax.transAxes, ha="right", va="top", color=INK2)
        ax.set_xlim(0, 60)
    axes[0].set_ylabel("fraction of pulses")
    axes[2].legend(loc="lower center", bbox_to_anchor=(0.5, -0.42), fontsize=8)
    fig.suptitle("Simulated data: flips per pulse (5,000 pulses, mean 20 flips)",
                 x=0.01, ha="left", fontsize=10, color=INK2)
    save(fig, "fig1_counts_per_pulse.png")

    # ---- 2. Space structure: do we recover the injected cluster sizes? ----
    NP, RATE, Q = 20000, 5.0, 1 / 3
    p, r, c, k_true, _ = generate(rng, NP, RATE, q=Q)
    found = cluster_sizes(p, r, c)
    ps, rs, cs = shuffle_control(rng, p)
    found_shuf = cluster_sizes(ps, rs, cs)
    obs, mu0, pv = adjacency_test(p, r, c, NP)
    obs_s, mu0_s, pv_s = adjacency_test(ps, rs, cs, NP)
    kmax = 8
    h_true = np.bincount(np.minimum(k_true, kmax), minlength=kmax + 1)[1:]
    h_found = np.bincount(np.minimum(found, kmax), minlength=kmax + 1)[1:]
    h_shuf = np.bincount(np.minimum(found_shuf, kmax), minlength=kmax + 1)[1:]
    res["spatial"] = dict(
        flips=int(p.size), injected_mean_cluster=float(k_true.mean()),
        recovered_mean_cluster=float(found.mean()),
        shuffled_mean_cluster=float(found_shuf.mean()),
        injected_multi_cell_fraction=float(np.mean(k_true > 1)),
        recovered_multi_cell_fraction=float(np.mean(found > 1)),
        adjacent_pairs_observed=int(obs), adjacent_pairs_expected_if_independent=float(mu0),
        adjacency_p_value=float(pv),
        shuffled_adjacent_pairs_observed=int(obs_s),
        shuffled_adjacent_pairs_expected=float(mu0_s), shuffled_p_value=float(pv_s))
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    x = np.arange(1, kmax + 1)
    wdt = 0.27
    ax.bar(x - wdt, h_true, wdt - 0.03, color=BLUE, label="injected (truth)")
    ax.bar(x, h_found, wdt - 0.03, color=ORANGE,
           label="recovered by the analysis")
    ax.bar(x + wdt, h_shuf, wdt - 0.03, color=AQUA,
           label="shuffled control (none above size 2)")
    ax.set_ylim(0.7, None)
    ax.set_yscale("log")
    ax.set_xticks(x, [str(i) for i in x[:-1]] + [f"{kmax}+"])
    ax.set_xlabel("cluster size (adjacent flipped cells in one pulse)")
    ax.set_ylabel("number of clusters")
    ax.set_title("The analysis recovers the injected clusters")
    ax.legend()
    save(fig, "fig2_cluster_sizes.png")

    # ---- 3. What clustering does to an error-correcting code ----
    NP, RATE = 20000, 20.0
    qs = [0.0, 0.02, 0.05, 0.1, 0.2, 1 / 3, 0.5]
    rows = []
    for q in qs:
        p, r, c, k, _ = generate(rng, NP, RATE, q=q)
        ps, rs, cs = shuffle_control(rng, p)
        rows.append(dict(
            mean_cluster=1 / (1 - q), flips=int(p.size),
            contiguous=word_failures(p, r, c, "contiguous"),
            interleaved=word_failures(p, r, c, "interleaved"),
            shuffled=word_failures(ps, rs, cs, "contiguous")))
    pbit = RATE / NBITS
    indep_pred = NP * (NBITS / WORD) * 21 * pbit**2     # C(7,2) p^2 per word
    res["decoder"] = dict(pulses=NP, rate=RATE, rows=rows,
                          independent_model_prediction=indep_pred)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    m = [x["mean_cluster"] for x in rows]
    per = 1e6 / (NP * RATE)                # failures per million flips
    for key, colr, lab, mk in [
            ("contiguous", ORANGE, "word bits side by side", "o"),
            ("interleaved", BLUE, "word bits interleaved", "s"),
            ("shuffled", AQUA, "shuffled control", "^")]:
        y = [max(x[key], 0.5) * per for x in rows]
        ax.plot(m, y, marker=mk, color=colr, label=lab)
    ax.axhline(indep_pred * per, color=INK2, lw=1, ls="--")
    ax.text(m[-1], indep_pred * per * 1.25, "independent-error formula",
            ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_yscale("log")
    ax.set_xlabel("mean cluster size injected")
    ax.set_ylabel("uncorrectable words per million flips")
    ax.set_title("Clustering breaks Hamming(7,4) unless bits are interleaved")
    ax.legend(loc="center right")
    save(fig, "fig3_decoder.png")

    # ---- 4. How many flips do we need? (plans the beam time) ----
    ALPHA, REPS, RATE = 1e-3, 300, 5.0
    means = [1.02, 1.05, 1.1, 1.2, 1.5]
    budgets = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]
    power = {"fano": {}, "adjacency": {}}
    for mk in means:
        q = 1 - 1 / mk
        pf, pa = [], []
        for nflips in budgets:
            n_p = max(int(nflips / RATE), 20)
            hf = ha = 0
            for _ in range(REPS):
                p, r, c, _, _ = generate(rng, n_p, RATE, q=q)
                hf += fano_test(np.bincount(p, minlength=n_p))[1] < ALPHA
                ha += adjacency_test(p, r, c, n_p)[2] < ALPHA
            pf.append(hf / REPS)
            pa.append(ha / REPS)
        power["fano"][mk], power["adjacency"][mk] = pf, pa

    def needed(pw):
        for b, v in zip(budgets, pw):
            if v >= 0.95:
                return b
        return None

    res["power"] = dict(
        alpha=ALPHA, target_power=0.95, rate=RATE, budgets=budgets,
        flips_needed_fano={str(k): needed(v) for k, v in power["fano"].items()},
        flips_needed_adjacency={str(k): needed(v) for k, v in power["adjacency"].items()},
        curves={t: {str(k): v for k, v in d.items()} for t, d in power.items()})
    # false-positive check on independent data
    fp_f = fp_a = 0
    for _ in range(2000):
        p, r, c, _, _ = generate(rng, 400, RATE, q=0.0)
        fp_f += fano_test(np.bincount(p, minlength=400))[1] < 0.05
        fp_a += adjacency_test(p, r, c, 400)[2] < 0.05
    res["power"]["false_positive_rate_at_0.05"] = dict(fano=fp_f / 2000,
                                                      adjacency=fp_a / 2000)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    shades = ["#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"]
    for ax, (test, ttl) in zip(axes, [("adjacency", "Spatial test (adjacent pairs)"),
                                      ("fano", "Time test (Fano factor)")]):
        for mk, colr in zip(means, shades):
            ax.plot(budgets, power[test][mk], marker="o", color=colr,
                    label=f"{mk:.2f}")
        ax.axhline(0.95, color=INK2, lw=1, ls="--")
        ax.set_xscale("log")
        ax.set_xlabel("total flips recorded")
        ax.set_title(ttl)
    axes[0].set_ylabel("chance of detecting the clustering")
    axes[1].legend(title="mean cluster size", loc="center left",
                   bbox_to_anchor=(1.0, 0.5))
    save(fig, "fig4_power.png")

    # ---- 5. Adaptive scrubbing under a changing beam ----
    NP = 6000
    profile = np.where((np.arange(NP) // 1000) % 2 == 1, 10.0, 1.0)  # hot/cold blocks
    base = 30.0
    out = {}
    for name, q in [("independent", 0.0), ("bursty (mean cluster 1.5)", 1 / 3)]:
        ps_, rs_, cs_ = [], [], []
        # generate per block so the rate follows the profile
        p, r, c, _, _ = generate(rng, NP, base * 10, q=q)
        keep = rng.random(p.size) < profile[p] / 10.0     # thin cold pulses
        if q > 0:   # keep or drop whole clusters, not single cells
            ev = np.concatenate([[0], np.cumsum(
                (np.diff(p) != 0) | (np.abs(np.diff(r)) > 1) | (np.abs(np.diff(c)) > 1))])
            keep = (rng.random(ev.max() + 1) < 1.0)[ev] & (
                rng.random(ev.max() + 1)[ev] < profile[p] / 10.0)
        p, r, c = p[keep], r[keep], c[keep]
        counts = np.bincount(p, minlength=NP).astype(float)
        row_ = {}
        for budget in [150, 300, 600, 1200]:
            sf, nf = scrub_schedule(counts, budget, adaptive=False)
            sa, na = scrub_schedule(counts, budget, adaptive=True)
            row_[budget] = dict(
                scrubs_fixed=nf, scrubs_adaptive=na,
                fixed=word_failures(p, r, c, "interleaved", sf[p]),
                adaptive=word_failures(p, r, c, "interleaved", sa[p]),
                fixed_contiguous=word_failures(p, r, c, "contiguous", sf[p]),
                adaptive_contiguous=word_failures(p, r, c, "contiguous", sa[p]))
        out[name] = row_
    res["adaptive_scrub"] = dict(pulses=NP, cold_rate=base, hot_rate=base * 10,
                                 results=out)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, name in zip(axes, out):
        b = sorted(out[name])
        ax.plot(b, [max(out[name][x]["fixed"], 0.5) for x in b], marker="o",
                color=BLUE, label="fixed interval")
        ax.plot(b, [max(out[name][x]["adaptive"], 0.5) for x in b], marker="s",
                color=ORANGE, label="adaptive interval")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks(b, [str(x) for x in b])
        ax.minorticks_off()
        ax.set_xlabel("scrubs allowed in the run")
        ax.set_title(name)
    axes[0].set_ylabel("uncorrectable words (interleaved layout)")
    axes[0].legend()
    save(fig, "fig5_adaptive_scrub.png")

    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
