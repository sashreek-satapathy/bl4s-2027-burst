import json
from pathlib import Path

ELEMENTARY_CHARGE_C = 1.602176634e-19

# Preliminary planning assumption, NOT confirmed CLEAR data.
BEAM_CHARGE_NC = 30.0

CONFIGURATION = "W 2 cm + 10 cm lead"

RESULTS_FILE = Path(__file__).with_name("results_flux.json")


def calculate_neutron_yield():

    # Load the existing Geant4 simulation results.
    with RESULTS_FILE.open("r", encoding="utf-8") as file:
        results = json.load(file)

    config = results["configs"][CONFIGURATION]
    side = config["side_80_100deg"]

    # Convert beam charge into incident electrons.
    charge_coulombs = BEAM_CHARGE_NC * 1e-9
    electrons = charge_coulombs / ELEMENTARY_CHARGE_C

    # Scale Geant4 results to one beam pulse.
    total_neutrons = (
        config["neutrons_per_electron_total"] * electrons
    )

    side_fluence = side["neutron_per_cm2"] * electrons

    above_1_mev = (
        side["neutron_above_1MeV_per_cm2"] * electrons
    )

    above_10_mev = (
        side["neutron_above_10MeV_per_cm2"] * electrons
    )
    above_10_mev_relative_error = 1.0  
    # Approx. 100%: based on ~1 simulated neutron
    # Note: rate_calc.py uses neutron fluence to estimate
    # the resulting memory upsets. This script only estimates
    # the neutron yield and fluence.
    print("\nBURST NEUTRON YIELD ESTIMATE")
    print("----------------------------")
    print("Beam energy:", results["beam_energy_MeV"], "MeV")
    print("Scoring distance:", results["score_radius_cm"], "cm")
    print("Configuration:", CONFIGURATION)
    print("Assumed charge:", BEAM_CHARGE_NC, "nC/pulse")
    print(f"Electrons per pulse: {electrons:.4e}")
    print(f"Neutrons crossing scoring sphere: {total_neutrons:.4e}")
    print(f"Side neutron fluence: {side_fluence:.2f} n/cm2")
    print(f"Neutrons above 1 MeV: {above_1_mev:.2f} n/cm2")
    print(f"Neutrons above 10 MeV: {above_10_mev:.2f} n/cm2")
    print("Approx. statistical uncertainty above 10 MeV: 100% (~1 simulated neutron)")
    print("\nNOTE: These estimates use assumed beam parameters.")

if __name__ == "__main__":
    calculate_neutron_yield()