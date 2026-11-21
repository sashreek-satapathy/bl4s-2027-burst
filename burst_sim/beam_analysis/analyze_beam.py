"""
Beam-day analysis: one run folder (LOG_FORMAT.md) in, a report out.

Steps
 1. Load and check: drop incomplete readouts; flag SEFI-like readouts (far too many
    flips for the beam charge) and analyse them separately.
 2. Rate: upset cross-section per bit for each chip, with 95% limits from the
    number of independent events (clusters counted once).
 3. Time tests: spread of flips per readout against the beam charge, and two tests
    clusters cannot fake: correlation between neighbouring readouts, and drift.
 4. Space test without the chip layout: repeated address-difference signatures among
    flips from the same readout; rebuild clusters; shuffled-address control.
 5. Codeword layout: learn which address bits are safe from the first half of the
    run, test on the second half against one-word and blind groupings.
 6. Scrub replay: how failures would grow if the memory were rewritten less often.

Run:  ../.venv/bin/python analyze_beam.py RUN_DIR      (writes RUN_DIR/report/)
"""
import argparse
import csv
import itertools
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from burst_sim import poisson_sf_ge, chi2_sf, components, BLUE, ORANGE, AQUA, INK2  # noqa: E402

SEFI_P = 1e-9          # a readout this unlikely given the charge is flagged
SEFI_MIN_FLIPS = 10
FAMILY_ALPHA = 0.01    # chance of learning even one false signature


# ------------------------------------------------------------------ 1. loading
def load(run_dir):
    with open(os.path.join(run_dir, "run.json")) as f:
        run = json.load(f)
    with open(os.path.join(run_dir, "readouts.csv")) as f:
        rd = list(csv.DictReader(f))
    with open(os.path.join(run_dir, "flips.csv")) as f:
        fl = list(csv.DictReader(f))
    R = dict(readout=np.array([int(r["readout"]) for r in rd]),
             chip=np.array([int(r["chip"]) for r in rd]),
             charge=np.array([float(r["charge_nC"]) for r in rd]),
             words=np.array([int(r["words_read"]) for r in rd]),
             status=np.array([r["status"] for r in rd]))
    wl = int(np.log2(run["word_bits"]))
    rows = []
    for r in fl:
        e, x = int(r["expected"], 16), int(r["expected"], 16) ^ int(r["read"], 16)
        for b in range(run["word_bits"]):
            if x >> b & 1:
                rows.append((int(r["readout"]), int(r["chip"]), int(r["addr"]), b, e >> b & 1))
    F = {k: np.array(v, dtype=np.int64) for k, v in
         zip(["readout", "chip", "addr", "bit", "was_one"], zip(*rows))} if rows else \
        {k: np.empty(0, np.int64) for k in ["readout", "chip", "addr", "bit", "was_one"]}
    return run, R, F, wl


def select(F, keep):
    return {k: v[keep] for k, v in F.items()}


def readout_counts(R, F):
    key = R["readout"] * 1000 + R["chip"]
    fk = F["readout"] * 1000 + F["chip"]
    order = np.argsort(key)
    pos = np.searchsorted(key[order], fk)
    n = np.bincount(order[pos], minlength=key.size) if fk.size else np.zeros(key.size, int)
    return n


def quality(run, R, F):
    full = 1 << run["addr_bits"]
    bad = (R["status"] != "ok") | (R["words"] != full)
    n = readout_counts(R, F)
    sefi = np.zeros(R["readout"].size, bool)
    for _ in range(5):                       # iterate: flagged readouts no longer set the rate
        good = ~bad & ~sefi
        for c in np.unique(R["chip"]):
            m = good & (R["chip"] == c)
            rate = n[m].sum() / max(R["charge"][m].sum(), 1e-12)
            mc = (R["chip"] == c) & ~bad
            mu = rate * R["charge"][mc]
            p = np.array([poisson_sf_ge(int(k), float(u)) if k >= SEFI_MIN_FLIPS else 1.0
                          for k, u in zip(n[mc], mu)])
            sefi[np.flatnonzero(mc)[p < SEFI_P]] = True
    return bad, sefi, n


# --------------------------------------------------------------------- stats
def poisson_ci(k, cl=0.95):
    a = (1 - cl) / 2

    def solve(f):
        lo, hi = 1e-9, 10 * k + 10
        for _ in range(200):
            mid = np.sqrt(lo * hi)
            lo, hi = (mid, hi) if f(mid) else (lo, mid)
        return np.sqrt(lo * hi)
    lower = 0.0 if k == 0 else solve(lambda mu: poisson_sf_ge(k, mu) < a)
    upper = solve(lambda mu: 1 - poisson_sf_ge(k + 1, mu) > a)
    return lower, upper


def same_group_pairs(g):
    order = np.argsort(g, kind="stable")
    gs = g[order]
    a, b, d = [], [], 1
    while d < gs.size:
        same = gs[d:] == gs[:-d]
        if not same.any():
            break
        i = np.flatnonzero(same)
        a.append(order[i])
        b.append(order[i + d])
        d += 1
    if not a:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    return np.concatenate(a), np.concatenate(b)


def signatures(F, wl):
    i, j = same_group_pairs(F["readout"] * 1000 + F["chip"])
    sig = ((F["addr"][i] ^ F["addr"][j]) << wl) | (F["bit"][i] ^ F["bit"][j])
    return i, j, sig


def learn(sig, nsig):
    u, inv, cnt = (np.unique(sig, return_inverse=True, return_counts=True)
                   if sig.size else (sig, sig, sig))
    mu = sig.size / nsig
    kmin = 2
    while poisson_sf_ge(kmin, mu) * nsig > FAMILY_ALPHA:
        kmin += 1
    learned = cnt >= kmin
    return u[learned], cnt[learned], learned[inv] if sig.size else np.zeros(0, bool), kmin


# ----------------------------------------------------------- 5. code layouts
def choose_bits(sigs, cnt, addr_bits, wl):
    """4 address bits least involved in learned same-bit neighbour differences."""
    same_bit = (sigs & ((1 << wl) - 1)) == 0
    a_sig, a_cnt = sigs[same_bit] >> wl, cnt[same_bit]
    score = [int((a_cnt * ((a_sig >> b) & 1)).sum()) for b in range(addr_bits)]
    best = sorted(range(addr_bits), key=lambda b: (score[b], -b))[:4]
    return sum(1 << b for b in best), score


def code_failures(F, wl, scheme, mask=0, window=None):
    win = F["readout"] if window is None else window
    if scheme == "word":
        key = F["addr"]
    else:
        key = ((F["addr"] & ~mask) << wl) | F["bit"]
    full = (win.astype(np.int64) * 64 + F["chip"]) * (1 << 40) + key
    _, cnt = np.unique(full, return_counts=True)
    return int(np.sum(cnt >= 2))


def time_tests(R, n, n_ev, n_perm=500, seed=3):
    """Within-readout spread (mixes clusters with bunching), then two tests that
    clusters cannot fake, because a cluster never spans two readouts:
    correlation between neighbouring readouts, and drift over the run.
    p-values by shuffling the readout order."""
    rng = np.random.default_rng(seed)
    out = {}
    for name, cnts in [("flips", n), ("events", n_ev)]:
        disp, dof = 0.0, 0
        for c in np.unique(R["chip"]):
            m = R["chip"] == c
            if R["charge"][m].sum() <= 0 or cnts[m].sum() == 0:
                continue
            mu = cnts[m].sum() * R["charge"][m] / R["charge"][m].sum()
            ok = mu > 0
            disp += float(np.sum((cnts[m][ok] - mu[ok]) ** 2 / mu[ok]))
            dof += int(ok.sum()) - 1
        out[f"spread_of_{name}_per_readout"] = dict(
            dispersion_index=disp / dof if dof > 0 else None,
            p_value=chi2_sf(disp, dof) if dof > 0 else None)
    BLOCKS = [1, 10, 60]                       # readouts per block: 1 s, 10 s, 1 min at 10 Hz
    series = []
    for c in np.unique(R["chip"]):
        m = (R["chip"] == c) & (R["charge"] > 0)
        order = np.argsort(R["readout"][m])
        q, k = R["charge"][m][order], n[m][order].astype(float)
        if k.sum() > 0:
            series.append((q, k))

    def residuals(z, blk):
        out_r = []
        for q, k in z:
            nb = q.size // blk
            if nb < 3:
                continue
            qb = q[:nb * blk].reshape(nb, blk).sum(1)
            kb = k[:nb * blk].reshape(nb, blk).sum(1)
            mu = kb.sum() * qb / qb.sum()
            out_r.append((kb - mu) / np.sqrt(mu))
        return out_r

    def lag1(rs):
        return float(np.mean([np.mean(r[1:] * r[:-1]) for r in rs]))

    def drift(rs):
        return float(np.mean([np.corrcoef(np.arange(r.size), r)[0, 1] for r in rs]))

    if series:
        scales, p_min = {}, 1.0
        perms = [[(q[idx], k[idx]) for (q, k), idx in
                  zip(series, [rng.permutation(q.size) for q, _ in series])] for _ in range(n_perm)]
        for blk in BLOCKS:
            rs = residuals(series, blk)
            if not rs:
                continue
            obs = lag1(rs)
            null = np.array([lag1(residuals(z, blk)) for z in perms])
            p = float((1 + np.sum(null >= obs)) / (1 + n_perm))
            scales[f"{blk} readouts"] = dict(lag1_correlation=obs, p_value=p)
            p_min = min(p_min, p)
        rs = residuals(series, 60) or residuals(series, 1)
        obs_d = drift(rs)
        null_d = np.array([drift(residuals(z, 60) or residuals(z, 1)) for z in perms])
        out["neighbouring_readouts"] = dict(
            by_block_size=scales, p_value=min(1.0, p_min * len(scales)),
            note="Smallest p over block sizes, times the number of block sizes (Bonferroni).")
        out["drift_over_run"] = dict(
            correlation_with_time=obs_d,
            p_value=float((1 + np.sum(np.abs(null_d) >= abs(obs_d))) / (1 + n_perm)))
    out["note"] = ("Spread per readout is inflated by clusters, so it cannot by itself show "
                   "time bunching. Neighbouring-readout correlation and drift can. Bunching "
                   "inside one readout (10 pulses) is invisible to all of these.")
    return out


# ---------------------------------------------------------------------- main
def analyse(run_dir):
    run, R, F, wl = load(run_dir)
    out_dir = os.path.join(run_dir, "report")
    os.makedirs(out_dir, exist_ok=True)
    nbits_chip = (1 << run["addr_bits"]) * run["word_bits"]
    rep = {"run": run["run"], "configuration": run["configuration"]}

    # ---- 1. quality ----
    orphan = ~np.isin(F["readout"] * 1000 + F["chip"], R["readout"] * 1000 + R["chip"])
    n_orphan = int(orphan.sum())          # flips naming a readout missing from readouts.csv
    if n_orphan:
        print(f"WARNING: {n_orphan} flips belong to readouts missing from readouts.csv; ignored")
        F = select(F, ~orphan)
    bad, sefi, n_all = quality(run, R, F)
    rkey = R["readout"] * 1000 + R["chip"]
    fkey = F["readout"] * 1000 + F["chip"]
    keep = ~np.isin(fkey, rkey[bad | sefi])
    rep["quality"] = dict(
        readouts=int(rkey.size), incomplete_or_failed=int(bad.sum()),
        incomplete_list=[(int(r), int(c)) for r, c in zip(R["readout"][bad], R["chip"][bad])],
        sefi_like=int(sefi.sum()),
        sefi_list=[dict(readout=int(r), chip=int(c), flips=int(k)) for r, c, k in
                   zip(R["readout"][sefi], R["chip"][sefi], n_all[sefi])],
        flips_total=int(F["addr"].size) + n_orphan, flips_excluded=int((~keep).sum()),
        flips_without_readout=n_orphan)
    F = select(F, keep)
    good = ~bad & ~sefi
    R = {k: v[good] for k, v in R.items()}
    n = readout_counts(R, F)

    w1 = F["was_one"].sum()
    rep["direction"] = dict(one_to_zero=int(w1), zero_to_one=int(F["was_one"].size - w1),
                            note="Unequal counts suggest data-pattern dependence.")

    # ---- 4. space test (needed before the event-level time test) ----
    nsig = (1 << (run["addr_bits"] + wl)) - 1
    i, j, sig = signatures(F, wl)
    _, cnt = np.unique(sig, return_counts=True) if sig.size else (sig, sig)
    coll = int(np.sum(cnt * (cnt - 1) // 2))
    lam0 = sig.size * (sig.size - 1) / 2 / nsig
    sigs, scnt, edge, kmin = learn(sig, nsig)
    lab = components(F["addr"].size, i[edge], j[edge])
    sizes = np.bincount(lab)
    sizes = sizes[sizes > 0]
    rng = np.random.default_rng(0)
    Fs = dict(F, addr=rng.integers(0, 1 << run["addr_bits"], F["addr"].size),
              bit=rng.integers(0, run["word_bits"], F["addr"].size))
    _, _, ssig = signatures(Fs, wl)
    s_learned = learn(ssig, nsig)[0].size
    multi_word = int(np.sum(np.unique(fkey[keep] * (1 << 22) + F["addr"],
                                      return_counts=True)[1] >= 2)) if F["addr"].size else 0
    rep["space"] = dict(
        same_readout_pairs=int(sig.size), signature_collisions=coll, expected_by_chance=lam0,
        p_value=poisson_sf_ge(coll, lam0) if sig.size else 1.0,
        signatures_learned=int(sigs.size), min_repeats=kmin,
        shuffled_control_signatures_learned=int(s_learned),
        mean_cluster_size=float(sizes.mean()) if sizes.size else None,
        multi_cell_fraction=float(np.mean(sizes > 1)) if sizes.size else None,
        cluster_size_counts={int(s): int(np.sum(sizes == s)) for s in np.unique(sizes)},
        words_with_2plus_flips=multi_word)

    # ---- 3. time test: flips, then events (clusters counted once) ----
    ev_first = np.zeros(F["addr"].size, bool)
    if F["addr"].size:
        _, first = np.unique(lab, return_index=True)
        ev_first[first] = True
    n_ev = readout_counts(R, select(F, ev_first))
    # ---- 2. rate per chip ----
    rep["rate"] = {}
    for c in np.unique(R["chip"]):
        m = R["chip"] == c
        k, q = int(n[m].sum()), float(R["charge"][m].sum())
        expo = q * run["fluence_per_nC"] * nbits_chip
        ke = int(n_ev[m].sum())                  # clusters are not independent flips:
        lo, hi = poisson_ci(ke)                  # count events, scale by flips per event
        lo, hi = lo * k / max(ke, 1), hi * k / max(ke, 1) if ke else hi
        rep["rate"][int(c)] = dict(flips=k, events=ke, charge_nC=q, flips_per_nC=k / q if q else None,
                                   sigma_cm2_per_bit=k / expo if expo else None,
                                   sigma_95=[lo / expo, hi / expo] if expo else None)
    rep["time"] = time_tests(R, n, n_ev)

    # ---- 5. code layout: learn on first half, test on second ----
    if F["addr"].size:
        half = np.median(R["readout"])
        tr, te = select(F, F["readout"] <= half), select(F, F["readout"] > half)
        _, _, tsig = signatures(tr, wl)
        lsig, lcnt, _, _ = learn(tsig, nsig)
        mask, score = choose_bits(lsig, lcnt, run["addr_bits"], wl)
        all_masks = [sum(1 << b for b in c) for c in itertools.combinations(range(run["addr_bits"]), 4)]
        sample = [all_masks[k] for k in np.random.default_rng(1).choice(len(all_masks), 200, replace=False)]
        blind = np.array([code_failures(te, wl, "stride", mk) for mk in sample])
        te_shuf = dict(te, addr=rng.integers(0, 1 << run["addr_bits"], te["addr"].size))
        nte = te["addr"].size
        rep["codes"] = dict(
            test_flips=int(nte), learned_address_bits=[b for b in range(run["addr_bits"]) if mask >> b & 1],
            failures=dict(one_word=code_failures(te, wl, "word"),
                          blind_bits_mean=float(blind.mean()),
                          blind_bits_worst=int(blind.max()),
                          blind_bits_fraction_worse_than_learned=None,
                          learned_bits=code_failures(te, wl, "stride", mask),
                          chance_level_shuffled=code_failures(te_shuf, wl, "stride", mask)))
        rep["codes"]["failures"]["blind_bits_fraction_worse_than_learned"] = float(
            np.mean(blind > rep["codes"]["failures"]["learned_bits"]))
        # ---- 6. scrub replay ----
        rep["scrub_replay"] = {}
        for k in [1, 10, 100, 1000, 10 ** 9]:
            w = F["readout"] // k
            rep["scrub_replay"]["never" if k == 10 ** 9 else f"every {k} readouts"] = dict(
                one_word=code_failures(F, wl, "word", window=w),
                learned_bits=code_failures(F, wl, "stride", mask, window=w))

    # ---- figures ----
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for c, colr in zip(np.unique(R["chip"]), [BLUE, ORANGE, AQUA, INK2]):
        m = R["chip"] == c
        axes[0].plot(np.cumsum(R["charge"][m]) / 1000, np.cumsum(n[m]), color=colr, label=f"chip {c}")
    axes[0].set_xlabel("cumulative beam charge (µC)")
    axes[0].set_ylabel("cumulative flips")
    axes[0].set_title("Flips follow the beam charge")
    axes[0].legend()
    if sig.size:
        axes[1].plot(np.sort(cnt)[::-1][:300], color=ORANGE, label="data")
        if ssig.size:
            axes[1].plot(np.sort(np.unique(ssig, return_counts=True)[1])[::-1][:300], color=AQUA,
                         label="shuffled addresses")
        axes[1].axhline(kmin, color=INK2, ls="--", lw=1)
        axes[1].set_xscale("log")
        axes[1].set_yscale("log")
        axes[1].legend()
    axes[1].set_xlabel("address-difference signature, ranked")
    axes[1].set_ylabel("same-readout pairs")
    axes[1].set_title("Repeated signatures mean neighbours")
    if sizes.size:
        s_u = np.unique(sizes)
        axes[2].bar(s_u, [np.sum(sizes == s) for s in s_u], color=BLUE)
        axes[2].set_yscale("log")
    axes[2].set_xlabel("rebuilt cluster size (cells)")
    axes[2].set_ylabel("clusters")
    axes[2].set_title("Cluster sizes, layout unknown")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "summary.png"), dpi=150)
    plt.close(fig)

    truth_f = os.path.join(run_dir, "truth.json")
    if os.path.exists(truth_f):
        with open(truth_f) as f:
            rep["truth_for_validation"] = json.load(f)
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(rep, f, indent=1, default=float)
    write_markdown(rep, out_dir)
    return rep


def fmt(x, spec=".2f"):
    return "n/a" if x is None else format(x, spec)


def write_markdown(rep, out_dir):
    q, s, t = rep["quality"], rep["space"], rep["time"]
    L = [f"# Run {rep['run']}", "", f"Configuration: {rep['configuration']}", "",
         "## Data quality", "",
         f"- {q['readouts']} readouts; {q['incomplete_or_failed']} incomplete or failed, dropped.",
         f"- {q['sefi_like']} SEFI-like readouts dropped: " +
         (", ".join(f"readout {x['readout']} chip {x['chip']} ({x['flips']} flips)" for x in q["sefi_list"]) or "none") + ".",
         f"- {q['flips_total']} flipped bits logged, {q['flips_excluded']} excluded with those readouts" +
         (f"; {q['flips_without_readout']} more name a readout missing from readouts.csv (logging bug?)." if q["flips_without_readout"] else "."),
         "", "## Upset cross-section", "", "| Chip | Flips | Charge (nC) | σ per bit (cm²) | 95% range |", "|---|---|---|---|---|"]
    for c, r in rep["rate"].items():
        if not r["sigma_95"]:
            L.append(f"| {c} | {r['flips']} | {r['charge_nC']:.0f} | no beam charge | n/a |")
            continue
        rng = r["sigma_95"]
        L.append(f"| {c} | {r['flips']} | {r['charge_nC']:.0f} | {r['sigma_cm2_per_bit']:.3g} | {rng[0]:.3g} to {rng[1]:.3g} |")
    d = rep["direction"]
    L += ["", f"Direction: {d['one_to_zero']} flips 1→0, {d['zero_to_one']} flips 0→1.", "",
          "## Clustering in space (layout unknown)", "",
          f"- Signature collisions: {s['signature_collisions']} observed, {s['expected_by_chance']:.2f} expected by chance (p = {s['p_value']:.2g}).",
          f"- Signatures learned: {s['signatures_learned']} (shuffled control: {s['shuffled_control_signatures_learned']}).",
          f"- Rebuilt mean cluster size: {s['mean_cluster_size'] or 0:.3f}; multi-cell fraction {100 * (s['multi_cell_fraction'] or 0):.1f}%.",
          f"- Words with 2+ flipped bits in one readout: {s['words_with_2plus_flips']}.",
          "", "## Clustering in time", "",
          f"- Spread of flips per readout: dispersion index {fmt(t['spread_of_flips_per_readout']['dispersion_index'])} (p = {fmt(t['spread_of_flips_per_readout']['p_value'], '.2g')}). Above 1 whenever clusters exist.",
          f"- Spread of events per readout (rebuilt clusters counted once): {fmt(t['spread_of_events_per_readout']['dispersion_index'])} (p = {fmt(t['spread_of_events_per_readout']['p_value'], '.2g')}). Approximate: clusters the method fails to rebuild still inflate it.",
          f"- Neighbouring readouts and blocks of 10 and 60 readouts: p = {fmt(t.get('neighbouring_readouts', {}).get('p_value'), '.2g')} after correcting for three scales. Clusters cannot fake this.",
          f"- Drift over the run: correlation with time {fmt(t.get('drift_over_run', {}).get('correlation_with_time'), '.4f')} (p = {fmt(t.get('drift_over_run', {}).get('p_value'), '.2g')})."]
    if "codes" in rep:
        c = rep["codes"]["failures"]
        L += ["", "## Codeword layout (learned on first half, tested on second half)", "",
              f"Test flips: {rep['codes']['test_flips']}. Learned address bits: {rep['codes']['learned_address_bits']}." +
              ("" if s["signatures_learned"] else " No neighbour signatures were learned, so this choice is uninformed."), "",
              "| Codeword | Failures |", "|---|---|",
              f"| One memory word | {c['one_word']} |",
              f"| 16 words, blind address bits (mean of 200 choices) | {c['blind_bits_mean']:.1f} (worst {c['blind_bits_worst']}) |",
              f"| 16 words, learned address bits | {c['learned_bits']} |",
              f"| Chance level (shuffled addresses) | {c['chance_level_shuffled']} |", "",
              f"{100 * c['blind_bits_fraction_worse_than_learned']:.0f}% of blind choices do worse than the learned one.",
              "", "## Scrub replay (whole run)", "", "| Rewrite | One-word failures | Learned-layout failures |", "|---|---|---|"]
        for k, v in rep["scrub_replay"].items():
            L.append(f"| {k} | {v['one_word']} | {v['learned_bits']} |")
    if "truth_for_validation" in rep and rep["truth_for_validation"].get("mean_cluster_injected"):
        tr = rep["truth_for_validation"]
        L += ["", "## Validation against the fake run's truth", "",
              f"- Injected mean cluster {tr['mean_cluster_injected']:.3f}, multi-cell fraction {100 * tr['multi_cell_fraction_injected']:.1f}%.",
              f"- Injected σ {tr['sigma_true_cm2_per_bit']:.3g} cm² per bit.",
              f"- Planted SEFI {tr['sefi_readout_chip']}, timeout {tr['timeout_readout_chip']}.",
              f"- Address bits that switch between physical neighbours: {tr['row_bit_of_physical_lsb']} (row), {tr['sel_bit_of_physical_lsb']} (column)."]
    L += ["", "![summary](summary.png)", ""]
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    a = ap.parse_args()
    r = analyse(a.run_dir)
    print(open(os.path.join(a.run_dir, "report", "report.md")).read())
