"""
What comes out of a converter target when CLEAR's electron beam hits it?

Geant4 simulation (through geant4_pybind). An electron beam hits a tungsten
disc. A thin spherical shell 50 cm away counts every neutron, photon, electron
and positron that reaches it, with its energy and its angle from the beam axis.
An optional shield shell (lead or polyethylene) can be placed in between.

Everything is reported PER BEAM ELECTRON, so results scale with bunch charge.

  one run :  python flux_sim.py run --thick 1.0 --shield none --events 20000 --seed 1 --out x.npz
  full set:  python flux_sim.py all      (runs every configuration on all cores)
  merge   :  python flux_sim.py report   (figures + results_flux.json)

SIMULATION ONLY. Photonuclear yields in Geant4 carry roughly a factor-2 model
uncertainty; treat the numbers as order-of-magnitude until checked against data.
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
RAW = os.path.join(HERE, "flux_raw")
R_SCORE_CM = 50.0                      # radius of the counting shell
PARTICLES = ["neutron", "gamma", "e-", "e+"]
THETA_EDGES = np.arange(0, 181, 10.0)                      # degrees
E_EDGES = np.logspace(-9, np.log10(300.0), 115)            # MeV (1 meV .. 300 MeV)

CONFIGS = [  # (label, converter thickness cm, shield material, shield thickness cm)
    ("W 0.35 cm (1 X0)", 0.35, "none", 0.0),
    ("W 1 cm", 1.0, "none", 0.0),
    ("W 2 cm", 2.0, "none", 0.0),
    ("W 5 cm", 5.0, "none", 0.0),
    ("W 2 cm + 5 cm lead", 2.0, "lead", 5.0),
    ("W 2 cm + 10 cm lead", 2.0, "lead", 10.0),
    ("W 2 cm + 5 cm polyethylene", 2.0, "poly", 5.0),
    ("W 2 cm + 10 cm polyethylene", 2.0, "poly", 10.0),
]


def out_name(thick, shield, sthick, seed):
    return os.path.join(RAW, f"w{thick:g}_{shield}{sthick:g}_s{seed}.npz")


# --------------------------------------------------------------------- one run
def run_one(args):
    import geant4_pybind as g4
    from geant4_pybind import cm, mm, m, MeV, deg

    hist = np.zeros((len(PARTICLES), THETA_EDGES.size - 1, E_EDGES.size - 1))
    pidx = {n: i for i, n in enumerate(PARTICLES)}

    class Shell(g4.G4VSensitiveDetector):
        def ProcessHits(self, step, history):
            pre = step.GetPreStepPoint()
            if pre.GetStepStatus() != g4.G4StepStatus.fGeomBoundary:
                return False
            track = step.GetTrack()
            i = pidx.get(track.GetDefinition().GetParticleName())
            if i is not None:
                pos = pre.GetPosition()
                th = np.degrees(np.arccos(pos.z / pos.mag()))
                e = pre.GetKineticEnergy() / MeV
                it = min(int(th // 10), THETA_EDGES.size - 2)
                ie = np.searchsorted(E_EDGES, e) - 1
                if 0 <= ie < E_EDGES.size - 1:
                    hist[i, it, ie] += 1
            track.SetTrackStatus(g4.G4TrackStatus.fStopAndKill)
            return True

    class Detector(g4.G4VUserDetectorConstruction):
        def Construct(self):
            nist = g4.G4NistManager.Instance()
            air = nist.FindOrBuildMaterial("G4_AIR")
            world_s = g4.G4Box("World", 1 * m, 1 * m, 1 * m)
            self.world_l = g4.G4LogicalVolume(world_s, air, "World")
            world_p = g4.G4PVPlacement(None, g4.G4ThreeVector(), self.world_l,
                                       "World", None, False, 0, True)
            w = nist.FindOrBuildMaterial("G4_W")
            tgt_s = g4.G4Tubs("Target", 0, 2.5 * cm, args.thick / 2 * cm, 0, 360 * deg)
            self.tgt_l = g4.G4LogicalVolume(tgt_s, w, "Target")
            g4.G4PVPlacement(None, g4.G4ThreeVector(), self.tgt_l, "Target",
                             self.world_l, False, 0, True)
            if args.shield != "none":
                mat = nist.FindOrBuildMaterial(
                    {"lead": "G4_Pb", "poly": "G4_POLYETHYLENE"}[args.shield])
                sh_s = g4.G4Sphere("Shield", 20 * cm, (20 + args.sthick) * cm,
                                   0, 360 * deg, 0, 180 * deg)
                self.sh_l = g4.G4LogicalVolume(sh_s, mat, "Shield")
                g4.G4PVPlacement(None, g4.G4ThreeVector(), self.sh_l, "Shield",
                                 self.world_l, False, 0, True)
            sc_s = g4.G4Sphere("Score", R_SCORE_CM * cm, R_SCORE_CM * cm + 1 * mm,
                               0, 360 * deg, 0, 180 * deg)
            self.sc_l = g4.G4LogicalVolume(sc_s, air, "Score")
            g4.G4PVPlacement(None, g4.G4ThreeVector(), self.sc_l, "Score",
                             self.world_l, False, 0, True)
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
            self.gun.SetParticleEnergy(args.energy * MeV)
            self.gun.SetParticleMomentumDirection(g4.G4ThreeVector(0, 0, 1))
            self.gun.SetParticlePosition(g4.G4ThreeVector(0, 0, -10 * cm))

        def GeneratePrimaries(self, event):
            self.gun.GeneratePrimaryVertex(event)

    class Actions(g4.G4VUserActionInitialization):
        def Build(self):
            self.SetUserAction(Gun())

    g4.G4Random.setTheSeed(args.seed)
    rm = g4.G4RunManagerFactory.CreateRunManager(g4.G4RunManagerType.Serial)
    rm.SetUserInitialization(Detector())
    rm.SetUserInitialization(g4.QGSP_BIC_HP())
    rm.SetUserInitialization(Actions())
    rm.Initialize()
    t0 = time.time()
    rm.BeamOn(args.events)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    np.savez_compressed(args.out, hist=hist, events=args.events, thick=args.thick,
                        shield=args.shield, sthick=args.sthick, energy=args.energy,
                        seconds=time.time() - t0)
    print(f"DONE {args.out} {args.events} events in {time.time() - t0:.0f} s", flush=True)


# -------------------------------------------------------------------- full set
def run_all(args):
    os.makedirs(RAW, exist_ok=True)
    jobs = []
    for _, thick, shield, sthick in CONFIGS:
        for seed in range(1, args.seeds + 1):
            out = out_name(thick, shield, sthick, seed)
            if not os.path.exists(out):
                jobs.append([sys.executable, os.path.abspath(__file__), "run",
                             "--thick", str(thick), "--shield", shield,
                             "--sthick", str(sthick), "--events", str(args.events),
                             "--seed", str(seed), "--energy", str(args.energy),
                             "--out", out])
    print(f"{len(jobs)} jobs, {args.workers} at a time", flush=True)
    running, done = [], 0
    while jobs or running:
        while jobs and len(running) < args.workers:
            running.append(subprocess.Popen(jobs.pop(0), stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL))
        time.sleep(2)
        still = [p for p in running if p.poll() is None]
        if len(still) != len(running):
            done += len(running) - len(still)
            print(f"finished {done}, {len(jobs) + len(still)} to go", flush=True)
        running = still
    report(args)


# ---------------------------------------------------------------------- report
def zone_area_cm2():
    c = np.cos(np.radians(THETA_EDGES))
    return 2 * np.pi * R_SCORE_CM**2 * (c[:-1] - c[1:])


def load(thick, shield, sthick):
    files = glob.glob(out_name(thick, shield, sthick, 0).replace("_s0.npz", "_s*.npz"))
    if not files:
        return None, 0
    h, n = 0, 0
    for f in files:
        d = np.load(f)
        h, n = h + d["hist"], n + int(d["events"])
    return h, n


def report(args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from burst_sim import save, BLUE, ORANGE, AQUA, INK2

    area = zone_area_cm2()
    e_mid = np.sqrt(E_EDGES[:-1] * E_EDGES[1:])
    th_mid = (THETA_EDGES[:-1] + THETA_EDGES[1:]) / 2
    res = {"note": "Geant4 simulation, per beam electron, at 50 cm from the target. "
                   "Order-of-magnitude until validated.",
           "beam_energy_MeV": args.energy, "score_radius_cm": R_SCORE_CM, "configs": {}}
    loaded = {}
    for label, thick, shield, sthick in CONFIGS:
        h, n = load(thick, shield, sthick)
        if h is None:
            continue
        loaded[label] = (h, n)
        fl = h / n / area[None, :, None]              # per cm2 per electron
        # rough dose in silicon (Gy per beam electron): charged particles at
        # ~1.7 MeV cm2/g, photons through mass energy-absorption ~0.025 cm2/g
        dose = (fl[2:].sum(axis=(0, 2)) * 1.7
                + (fl[1] * e_mid[None, :]).sum(axis=1) * 0.025) * 1.602e-10
        cfg = {"beam_electrons": n,
               "neutrons_per_electron_total": float(h[0].sum() / n),
               "neutron_mean_energy_MeV": float((h[0].sum(0) * e_mid).sum() / max(h[0].sum(), 1))}
        for name, sl in [("forward_0_10deg", slice(0, 1)), ("side_80_100deg", slice(8, 10)),
                         ("back_120_150deg", slice(12, 15))]:
            a = area[sl].sum()
            nn = h[0, sl].sum(0)
            cfg[name] = {
                "neutron_per_cm2": float(nn.sum() / n / a),
                "neutron_above_1MeV_per_cm2": float(nn[e_mid > 1].sum() / n / a),
                "neutron_above_10MeV_per_cm2": float(nn[e_mid > 10].sum() / n / a),
                "neutrons_counted": int(nn.sum()),
                "photon_per_cm2": float(h[1, sl].sum() / n / a),
                "electron_positron_per_cm2": float(h[2:, sl].sum() / n / a),
                "rough_dose_Gy": float((dose[sl] * area[sl]).sum() / a)}
            d = cfg[name]
            d["neutrons_per_Gy_per_cm2"] = d["neutron_per_cm2"] / d["rough_dose_Gy"] \
                if d["rough_dose_Gy"] > 0 else None
        res["configs"][label] = cfg

    # figure: angular distribution for the bare converter
    key = next((k for k in ["W 2 cm", "W 1 cm"] if k in loaded), None)
    if key:
        h, n = loaded[key]
        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        for i, (nm, colr, mk) in enumerate([("neutrons", BLUE, "o"), ("photons", ORANGE, "s")]):
            ax.plot(th_mid, h[i].sum(1) / n / area, marker=mk, color=colr, label=nm)
        ax.plot(th_mid, h[2:].sum((0, 2)) / n / area, marker="^", color=AQUA,
                label="electrons + positrons")
        ax.set_yscale("log")
        ax.set_xlabel("angle from the beam axis (degrees)")
        ax.set_ylabel("particles per cm² per beam electron, at 50 cm")
        ax.set_title(f"What leaves the converter ({key}, {args.energy:g} MeV beam)")
        ax.legend()
        save(fig, "fig8_flux_vs_angle.png")

        fig, ax = plt.subplots(figsize=(6.4, 3.8))
        sl = slice(8, 10)
        for lab, colr in [(key, BLUE), ("W 2 cm + 10 cm lead", ORANGE),
                          ("W 2 cm + 10 cm polyethylene", AQUA)]:
            if lab in loaded:
                hh, nn = loaded[lab]
                y = hh[0, sl].sum(0) / nn / area[sl].sum() / np.diff(np.log(E_EDGES))
                ax.step(e_mid, y, where="mid", color=colr, label=lab)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("neutron energy (MeV)")
        ax.set_ylabel("neutrons per cm² per electron per unit ln(E)")
        ax.set_title("Neutron spectrum at 90 degrees")
        ax.legend(fontsize=8)
        save(fig, "fig9_neutron_spectrum.png")

    with open(os.path.join(HERE, "results_flux.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run", "all", "report"])
    ap.add_argument("--thick", type=float, default=2.0)
    ap.add_argument("--shield", default="none", choices=["none", "lead", "poly"])
    ap.add_argument("--sthick", type=float, default=0.0)
    ap.add_argument("--energy", type=float, default=200.0)
    ap.add_argument("--events", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="test.npz")
    a = ap.parse_args()
    {"run": run_one, "all": run_all, "report": report}[a.mode](a)
