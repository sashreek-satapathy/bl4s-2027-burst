"""
Validation: rebuild the CERN aluminium-target test (Lerner et al. 2023, IEEE TNS 70(8)
1572, doi:10.1109/TNS.2023.3252808) in Geant4, fold with our ISSI cross-section, and
compare with the SEU rates CERN measured in the same chip (IS61WV204816BLL-10TLI).

Their setup (paper p. 1574-1576):
  - ~205 MeV electrons, results scaled to 30 nC per train at 10 Hz = 6.75e15 e-/h
  - Al-6082 cylinder, 15 cm long; radius 5 cm (Run 1) or 2.5 cm (Runs 2, 3)
  - SRAMs on two panels 10 cm from the beam axis: lateral (ISSI1) and top (ISSI2)
  - Run 3: 5 cm lead between the target and the lateral panel
Our assumptions (not given in the paper): lead slab 5 cm thick at x = 4-9 cm, 20 cm
wide, z = -5..20 cm; SRAM position along the panel unknown, so the rate is reported
for z = 0..15 cm (target length) with the spread across z as a range; no hall,
concrete or support structure (they neglect thermal neutrons too).

Scoring: a 1 mm thick cylindrical shell at r = 10 cm, from z = -10 to +30 cm.
Neutron fluence = track length in the shell / shell volume, binned in z (2.5 cm),
azimuth (lateral = around +x, top = around +y, 90 deg wide) and energy.
Surface crossings are also counted, for comparison with flux_sim.py's method.

  one run : python validate_l23.py run --run 2 --events 20000 --seed 1
  all     : python validate_l23.py all --events 20000 --seeds 4 --workers 10
  report  : python validate_l23.py report
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "flux_raw_l23")
E_EDGES = np.logspace(-9, np.log10(300.0), 115)     # MeV, same as flux_sim.py
Z_EDGES = np.arange(-10.0, 30.01, 2.5)               # cm
R_SCORE, DR = 10.0, 0.1                              # cm
RUNS = {1: dict(radius=5.0, lead=False), 2: dict(radius=2.5, lead=False),
        3: dict(radius=2.5, lead=True)}
LEAD = dict(x0=4.0, x1=9.0, half_y=10.0, z0=-5.0, z1=20.0)   # assumed, cm
TARGET_LEN = 15.0
E_PER_HOUR = 6.75e15
BEAM_MEV = 205.0

# Fig. 8 of the paper, read off the plot by eye (x 10^3 SEU/h, +-0.1 reading error)
CERN_FIG8 = {  # run: (ISSI1 data, ISSI1 FLUKA, ISSI2 data, ISSI2 FLUKA)
    1: (3.0, 2.35, 3.15, 2.4),
    2: (4.3, 2.55, 3.85, 2.6),
    3: (2.6, 2.15, 4.1, 2.95),
}


def out_name(run, seed):
    return os.path.join(RAW, f"run{run}_s{seed}.npz")


def run_one(a):
    import geant4_pybind as g4
    from geant4_pybind import cm, mm, m, MeV, deg

    cfg = RUNS[a.run]
    nz, ne = Z_EDGES.size - 1, E_EDGES.size - 1
    track = np.zeros((2, nz, ne))       # [lateral, top] neutron track length, cm
    cross = np.zeros((2, nz, ne))       # surface crossings inward-or-outward

    def side(x, y):
        phi = np.degrees(np.arctan2(y, x)) % 360
        if phi < 45 or phi >= 315:
            return 0                      # lateral, +x
        if 45 <= phi < 135:
            return 1                      # top, +y
        return None

    class Shell(g4.G4VSensitiveDetector):
        def ProcessHits(self, step, history):
            tr = step.GetTrack()
            if tr.GetDefinition().GetParticleName() != "neutron":
                return False
            pre = step.GetPreStepPoint()
            p = pre.GetPosition()
            s = side(p.x, p.y)
            if s is None:
                return False
            iz = int((p.z / cm - Z_EDGES[0]) // 2.5)
            ie = np.searchsorted(E_EDGES, pre.GetKineticEnergy() / MeV) - 1
            if 0 <= iz < nz and 0 <= ie < ne:
                track[s, iz, ie] += step.GetStepLength() / cm
                if pre.GetStepStatus() == g4.G4StepStatus.fGeomBoundary:
                    cross[s, iz, ie] += 1
            return True

    class Detector(g4.G4VUserDetectorConstruction):
        def Construct(self):
            nist = g4.G4NistManager.Instance()
            air = nist.FindOrBuildMaterial("G4_AIR")
            world_l = g4.G4LogicalVolume(g4.G4Box("World", 1 * m, 1 * m, 1 * m), air, "World")
            world_p = g4.G4PVPlacement(None, g4.G4ThreeVector(), world_l, "World",
                                       None, False, 0, True)
            al = nist.FindOrBuildMaterial("G4_Al")
            tgt = g4.G4Tubs("Target", 0, cfg["radius"] * cm, TARGET_LEN / 2 * cm, 0, 360 * deg)
            self.tgt_l = g4.G4LogicalVolume(tgt, al, "Target")
            g4.G4PVPlacement(None, g4.G4ThreeVector(0, 0, TARGET_LEN / 2 * cm), self.tgt_l,
                             "Target", world_l, False, 0, True)
            if cfg["lead"]:
                L = LEAD
                box = g4.G4Box("Lead", (L["x1"] - L["x0"]) / 2 * cm, L["half_y"] * cm,
                               (L["z1"] - L["z0"]) / 2 * cm)
                self.pb_l = g4.G4LogicalVolume(box, nist.FindOrBuildMaterial("G4_Pb"), "Lead")
                g4.G4PVPlacement(None, g4.G4ThreeVector((L["x0"] + L["x1"]) / 2 * cm, 0,
                                                        (L["z0"] + L["z1"]) / 2 * cm),
                                 self.pb_l, "Lead", world_l, False, 0, True)
            sh = g4.G4Tubs("Score", R_SCORE * cm, (R_SCORE + DR) * cm,
                           (Z_EDGES[-1] - Z_EDGES[0]) / 2 * cm, 0, 360 * deg)
            self.sc_l = g4.G4LogicalVolume(sh, air, "Score")
            g4.G4PVPlacement(None, g4.G4ThreeVector(0, 0, (Z_EDGES[-1] + Z_EDGES[0]) / 2 * cm),
                             self.sc_l, "Score", world_l, False, 0, True)
            return world_p

        def ConstructSDandField(self):
            self.sd = Shell("Shell")
            g4.G4SDManager.GetSDMpointer().AddNewDetector(self.sd)
            self.sc_l.SetSensitiveDetector(self.sd)

    class Gun(g4.G4VUserPrimaryGeneratorAction):
        def __init__(self):
            super().__init__()
            self.gun = g4.G4ParticleGun(1)
            self.gun.SetParticleDefinition(
                g4.G4ParticleTable.GetParticleTable().FindParticle("e-"))
            self.gun.SetParticleEnergy(BEAM_MEV * MeV)
            self.gun.SetParticleMomentumDirection(g4.G4ThreeVector(0, 0, 1))
            self.gun.SetParticlePosition(g4.G4ThreeVector(0, 0, -20 * cm))

        def GeneratePrimaries(self, event):
            self.gun.GeneratePrimaryVertex(event)

    class Actions(g4.G4VUserActionInitialization):
        def Build(self):
            self.SetUserAction(Gun())

    g4.G4Random.setTheSeed(a.seed)
    rm = g4.G4RunManagerFactory.CreateRunManager(g4.G4RunManagerType.Serial)
    rm.SetUserInitialization(Detector())
    rm.SetUserInitialization(g4.QGSP_BIC_HP())
    rm.SetUserInitialization(Actions())
    rm.Initialize()
    t0 = time.time()
    rm.BeamOn(a.events)
    os.makedirs(RAW, exist_ok=True)
    out = a.out or out_name(a.run, a.seed)
    np.savez_compressed(out, track=track, cross=cross, events=a.events, run=a.run,
                        seconds=time.time() - t0)
    print(f"DONE {out} {a.events} events in {time.time() - t0:.0f} s", flush=True)


def run_all(a):
    os.makedirs(RAW, exist_ok=True)
    jobs = [[sys.executable, os.path.abspath(__file__), "run", "--run", str(r),
             "--events", str(a.events), "--seed", str(s)]
            for s in range(1, a.seeds + 1) for r in a.runs
            if not os.path.exists(out_name(r, s))]
    print(f"{len(jobs)} jobs, {a.workers} at a time", flush=True)
    running, done = [], 0
    while jobs or running:
        while jobs and len(running) < a.workers:
            running.append(subprocess.Popen(jobs.pop(0), stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL))
        time.sleep(2)
        still = [p for p in running if p.poll() is None]
        if len(still) != len(running):
            done += len(running) - len(still)
            print(f"finished {done}, {len(jobs) + len(still)} to go", flush=True)
        running = still


def load(run):
    files = sorted(glob.glob(os.path.join(RAW, f"run{run}_s*.npz")))
    if not files:
        return None
    d = [np.load(f) for f in files]
    return dict(track=[x["track"] for x in d], cross=[x["cross"] for x in d],
                events=[int(x["events"]) for x in d])


def report(a):
    from rate_calc import weibull, thermal, CHIP_BITS
    e_mid = np.sqrt(E_EDGES[:-1] * E_EDGES[1:])
    sig = weibull(e_mid) + thermal(e_mid)          # cm2/bit per energy bin
    vol = np.pi / 4 * ((R_SCORE + DR) ** 2 - R_SCORE ** 2) * 2.5   # quarter annulus (90 deg) x 2.5 cm, cm3
    area = np.pi / 2 * R_SCORE * 2.5                                 # cm2
    inz = (Z_EDGES[:-1] >= 0) & (Z_EDGES[1:] <= TARGET_LEN)
    res = dict(note="Geant4 rebuild of Lerner et al. 2023 (CERN, Al target), folded with "
                    "the ISSI Weibull + thermal cross-section. SEU/h per chip at 30 nC, 10 Hz.",
               assumptions=dict(lead_slab_cm=LEAD, sram_z_range_cm=[0, TARGET_LEN],
                                no_hall_or_concrete=True, beam_MeV=BEAM_MEV),
               runs={})
    lines = []
    for run in RUNS:
        d = load(run)
        if d is None:
            continue
        n = sum(d["events"])
        per_seed = []
        for t, ev in zip(d["track"], d["events"]):
            flu = t / vol / ev                                 # n/cm2 per electron per bin
            per_seed.append((flu * sig).sum(-1) * CHIP_BITS * E_PER_HOUR)   # [side, z]
        per_seed = np.array(per_seed)                          # seed, side, z
        rate_z = per_seed.mean(0)
        err_z = per_seed.std(0, ddof=1) / np.sqrt(len(per_seed)) if len(per_seed) > 1 else 0 * rate_z
        tr = sum(d["track"]) / vol / n
        cr = sum(d["cross"]) / area / n
        out = {}
        for s, name, ci, fi in ((0, "lateral (ISSI1)", 0, 1), (1, "top (ISSI2)", 2, 3)):
            r = rate_z[s, inz]
            mean = float(r.mean())
            stat = float(np.sqrt((err_z[s, inz] ** 2).sum()) / inz.sum())
            cr_rate = float(((cr[s, inz] * sig).sum(-1) * CHIP_BITS * E_PER_HOUR).mean())
            fl = tr[s, inz].sum(-1).mean()
            fast = tr[s, inz][:, e_mid > 1].sum(-1).mean()
            data, fluka = CERN_FIG8[run][ci], CERN_FIG8[run][fi]
            out[name] = dict(
                ours_seu_per_h=mean, ours_stat_err=stat,
                ours_range_over_z=[float(r.min()), float(r.max())],
                ours_using_crossings=cr_rate,
                neutron_fluence_per_e_cm2=float(fl), fraction_above_1MeV=float(fast / fl),
                cern_measured_seu_per_h=data * 1e3, cern_fluka_seu_per_h=fluka * 1e3,
                ours_over_measured=mean / (data * 1e3), ours_over_fluka=mean / (fluka * 1e3))
            lines.append(f"Run {run} {name:16s} ours {mean:7.0f} +- {stat:4.0f} "
                         f"(z range {r.min():.0f}-{r.max():.0f}, crossings {cr_rate:.0f})  "
                         f"CERN data {data * 1e3:.0f}  FLUKA {fluka * 1e3:.0f}  "
                         f"ours/data {mean / (data * 1e3):.2f}  ours/FLUKA {mean / (fluka * 1e3):.2f}")
        res["runs"][str(run)] = dict(events=n, seeds=len(d["events"]), **out)
    with open(os.path.join(HERE, "results_validation_l23.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("\n".join(lines))
    figure(res)


def figure(res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from burst_sim import save, BLUE, ORANGE, INK2

    labels, ours, lo, hi, data, fluka = [], [], [], [], [], []
    for run, v in res["runs"].items():
        for name, short in (("lateral (ISSI1)", "lateral"), ("top (ISSI2)", "top")):
            x = v[name]
            labels.append(f"Run {run}\n{short}")
            ours.append(x["ours_seu_per_h"] / 1e3)
            lo.append(x["ours_range_over_z"][0] / 1e3)
            hi.append(x["ours_range_over_z"][1] / 1e3)
            data.append(x["cern_measured_seu_per_h"] / 1e3)
            fluka.append(x["cern_fluka_seu_per_h"] / 1e3)
    xs = np.arange(len(labels))
    ours, lo, hi = map(np.array, (ours, lo, hi))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.errorbar(xs - 0.15, ours, yerr=[ours - lo, hi - ours], fmt="o", color=BLUE,
                capsize=3, label="Our Geant4 + σ(E) fold (bar: chip position along target)")
    ax.plot(xs + 0.15, data, "s", color=ORANGE, label="CERN measured (Fig. 8, read off plot)")
    ax.plot(xs + 0.15, fluka, "^", color=INK2, mfc="none", label="CERN FLUKA prediction")
    ax.set_xticks(xs, labels)
    ax.set_ylabel("SEU per hour per chip (×10³)")
    ax.set_ylim(0, None)
    ax.set_title("ISSI SRAM at CLEAR, aluminium target (Lerner et al. 2023)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=1, frameon=False)
    save(fig, "fig12_validation_l23.png")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--run", type=int, choices=list(RUNS), required=True)
    r.add_argument("--events", type=int, default=20000)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", default=None)
    al = sub.add_parser("all")
    al.add_argument("--events", type=int, default=20000)
    al.add_argument("--seeds", type=int, default=4)
    al.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    al.add_argument("--runs", type=int, nargs="+", default=list(RUNS))
    sub.add_parser("report")
    a = ap.parse_args()
    {"run": run_one, "all": run_all, "report": report}[a.cmd](a)


if __name__ == "__main__":
    main()
