"""
Upset rates and memory needed, built on Logan's estimate (radiation_estimates.md).

1. Reproduces Logan's numbers exactly, as a check.
2. Brackets the neutron rate using the simulated energy spectrum behind lead,
   because the cross-section is only known here at 1.2 MeV.
3. Tabulates chips needed against beam time, for 1,000 and 2,000 flips.
4. Dose per pulse for the direct-electron arm.

SIMULATION + PUBLISHED CROSS-SECTIONS + ASSUMED BEAM SETTINGS. No beam data.

Run:  .venv/bin/python rate_calc.py   (needs flux_raw/; writes results_rate.json, fig10)
"""
import json
import os

import numpy as np
import matplotlib.pyplot as plt

from burst_sim import save, HERE, BLUE, ORANGE, AQUA, INK2
from flux_sim import load, zone_area_cm2, E_EDGES

E_CHARGE = 1.602176634e-19
E_PER_NC = 1e-9 / E_CHARGE
CHIP_BITS = 33_554_432               # ISSI IS61WV204816BLL, 32 Mibit
MIB = 8_388_608
RATE_HZ = 10.0

# Logan's inputs
SIGMA_N_1P2 = 1.61e-15               # cm2/bit at 1.2 MeV, Cecchetto 2021 Table III
SIGMA_E, SIGMA_E_ERR = 4.74e-18, 2.20e-18   # cm2/bit at 200 MeV, Coronetti 2020
Q_NEUTRON_NC = 30.0                  # nC per pulse, assumed
Q_ELECTRON_NC = 0.01                 # nC per pulse, assumed
BEAM_AREA_CM2 = 1.0                  # assumed, uniform
S_SI = 1.7                           # MeV cm2/g, electron energy loss in silicon (approx.)

TIMES_MIN = [10, 30, 60, 120, 240]
TARGETS = [1000, 2000]


def neutron_spectrum():
    """Neutron fluence per electron per cm2 at 80-100 deg, 50 cm, behind W 2 cm + 10 cm lead."""
    h, n = load(2.0, "lead", 10.0)
    area = zone_area_cm2()[8:10].sum()
    return h[0, 8:10].sum(0) / n / area, int(h[0, 8:10].sum())


def chips_needed(flips_per_chip_per_pulse, target, minutes):
    return int(np.ceil(target / (flips_per_chip_per_pulse * minutes * 60 * RATE_HZ)))


def main():
    res = {"note": "Built on Logan's estimate. Geant4 flux, published cross-sections, "
                   "assumed beam settings. Expectations, not measurements."}

    # ---- 1. reproduce Logan ----
    spec, counted = neutron_spectrum()
    phi_e = spec.sum()                                   # n/cm2 per electron
    phi_pulse = phi_e * E_PER_NC * Q_NEUTRON_NC
    n_rate_flat = CHIP_BITS * SIGMA_N_1P2 * phi_pulse
    e_fluence = E_PER_NC * Q_ELECTRON_NC / BEAM_AREA_CM2
    e_rate = CHIP_BITS * SIGMA_E * e_fluence
    res["logan_check"] = dict(
        neutron_fluence_per_electron=phi_e, neutrons_counted_in_geant4=counted,
        geant4_stat_error=1 / np.sqrt(counted),
        neutron_fluence_per_pulse=phi_pulse, neutron_upsets_per_pulse_per_chip=n_rate_flat,
        neutron_MiB_for_1000_in_6000_pulses=1000 / (SIGMA_N_1P2 * phi_pulse * 6000) / MIB,
        electron_upsets_per_pulse_per_chip=e_rate,
        electron_MiB_for_1000_in_6000_pulses=1000 / (SIGMA_E * e_fluence * 6000) / MIB)

    # ---- 2. bracket the neutron rate with the spectrum ----
    def above(t):   # the bin containing t is split in proportion to log-energy
        lo, hi = np.log(E_EDGES[:-1]), np.log(E_EDGES[1:])
        w = np.clip((hi - np.log(t)) / (hi - lo), 0, 1)
        return float((spec * w).sum() / phi_e)
    frac = {f"above_{t}_MeV": above(t) for t in [0.1, 0.5, 1.0]}
    e_mid = np.sqrt(E_EDGES[:-1] * E_EDGES[1:])
    res["neutron_spectrum_behind_10cm_lead"] = dict(
        mean_energy_MeV=float((spec * e_mid).sum() / phi_e), fraction=frac)
    # bounding models for sigma(E): same 1.2 MeV value everywhere above a threshold, 0 below
    models = {"flat (Logan)": 1.0,
              "zero below 0.5 MeV": frac["above_0.5_MeV"],
              "zero below 1 MeV": frac["above_1.0_MeV"]}
    res["neutron_models"] = {}
    for name, f in models.items():
        for dist in [50, 30]:
            r = n_rate_flat * f * (50 / dist) ** 2
            res["neutron_models"][f"{name}, {dist} cm"] = dict(
                upsets_per_pulse_per_chip=r,
                minutes_one_chip_for_1000=1000 / r / RATE_HZ / 60,
                chips_needed={str(t): {str(m): chips_needed(r, t, m) for m in TIMES_MIN}
                              for t in TARGETS})

    # ---- 3. direct electrons: per chip, uncertainty, dose ----
    dose_per_pulse = e_fluence * S_SI * 1.602e-10        # Gy(Si)
    res["direct_electron"] = dict(
        upsets_per_pulse_per_chip=e_rate,
        upsets_per_pulse_range_1sigma=[CHIP_BITS * (SIGMA_E - SIGMA_E_ERR) * e_fluence,
                                       CHIP_BITS * (SIGMA_E + SIGMA_E_ERR) * e_fluence],
        dose_Gy_per_pulse=dose_per_pulse,
        dose_Gy_per_6000_pulses=dose_per_pulse * 6000,
        dose_Gy_for_1000_flips_one_chip=dose_per_pulse * 1000 / e_rate,
        minutes_one_chip_for_1000=1000 / e_rate / RATE_HZ / 60,
        note="Only chips inside the ~1 cm2 beam count. Adding memory means stacking boards "
             "along the beam; not simulated. Dose per flip is fixed by sigma, not by charge.")

    # ---- figure: chips needed vs beam time, 2,000 flips ----
    t = np.linspace(10, 240, 200)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for (name, f), colr in zip(models.items(), [BLUE, AQUA, ORANGE]):
        for dist, ls in [(50, "-"), (30, "--")]:
            r = n_rate_flat * f * (50 / dist) ** 2
            ax.plot(t, np.ceil(2000 / (r * t * 60 * RATE_HZ)), color=colr, ls=ls,
                    label=f"{name}, {dist} cm")
    ax.set_yscale("log")
    ax.set_yticks([1, 2, 5, 10, 20, 50])
    ax.yaxis.set_major_formatter(plt.ScalarFormatter())
    ax.set_xlabel("beam time per configuration (minutes, 10 Hz, 30 nC per pulse)")
    ax.set_ylabel("4 MiB chips needed")
    ax.set_title("Chips needed for 2,000 neutron-induced flips")
    ax.legend(fontsize=8)
    ax.grid(True, which="both", color=INK2, alpha=0.15)
    save(fig, "fig10_chips_vs_time.png")

    with open(os.path.join(HERE, "results_rate.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
