# Radiation physics: preliminary SEU-rate and memory-size estimates

**Author:** Logan Piñeiro. First version, 2026-11-18. Copied here unchanged apart from formatting; review notes are at the end and are not part of Logan's text.

**Status:** feasibility estimates, not beam measurements. Calculations use the team's Geant4 neutron yield, published single-event upset (SEU) cross-sections, and explicitly assumed CLEAR operating parameters. The goal is ~1,000 expected upsets per configuration.

**Summary.** For the neutron configuration I predict approximately 0.0142 flips per pulse, requiring 46.85 MiB of exposed memory to collect 1,000 flips over 6,000 pulses. For the direct electron configuration I got 0.00993 flips per pulse, requiring 67.16 MiB of exposed memory to collect 1,000 flips over 6,000 pulses.

## Device and calculation method

Use one reference device in both configurations: ISSI IS61WV204816BLL-10TLI (40 nm SRAM, 32 Mibit = 33,554,432 bits = 4 MiB). The device identity is specified in [2, Table I]; electron response is reported in [3]. Chip selection and physical bit-address mapping are not yet finalized.

For a uniform per-bit exposure:

- Expected upsets per pulse = B σ Φ
- Expected upsets in a run = B σ Φ P
- Exposed bits needed for 1,000 upsets = 1000 / (σ Φ P)

Here B is the number of effectively irradiated memory bits; σ is the measured per-bit SEU cross-section (cm²/bit); Φ is fluence at the chip (particles/cm²/pulse); and P is the number of pulses. In both examples P = 6,000 (an assumed 10-minute run at 10 Hz). One MiB corresponds to 8,388,608 bits.

## Configuration 1: off-axis neutron exposure

Geometry from Geant4 [1]: 200 MeV electron beam → 2 cm tungsten converter → 10 cm lead shielding; detector at 80°–100°, 50 cm from the converter. This is the simulation's angular scoring region, not a validated final experimental arrangement.

| Input | Value | Basis |
|---|---|---|
| Geant4 neutron fluence per incident electron | 1.40688397 × 10⁻⁶ neutrons/cm²/electron | [1], W 2 cm + 10 cm lead, side_80_100deg |
| Beam charge | 30 nC/pulse | Assumed planning setting |
| Neutron SEU cross-section | 1.61 × 10⁻¹⁵ cm²/bit, measured at 1.2 MeV | [2, Table III] |
| Exposed SRAM capacity | 33,554,432 bits (one 4-MiB chip) | Device nominal capacity; full exposure assumed |

Using the elementary charge e = 1.602176634 × 10⁻¹⁹ C [4]:

- Electrons per nC: 10⁻⁹ C / e = 6.241509 × 10⁹ electrons/nC.
- Neutron fluence per nC: (1.40688397 × 10⁻⁶) × (6.241509 × 10⁹) = 8,781.08 neutrons/cm²/nC, consistent with Sashreek's rounded 8,800.
- Neutron fluence per pulse: 8,781.08 × 30 = 263,432 neutrons/cm²/pulse.
- Expected upsets per pulse, one chip: (33,554,432 bits) × (1.61 × 10⁻¹⁵ cm²/bit) × (263,432 neutrons/cm²) = 0.01423 upsets/pulse.
- Expected upsets over 6,000 pulses, one chip: 0.0142313 × 6,000 = 85.39 upsets.
- Required exposed capacity for 1,000 expected upsets: 1,000 / [(1.61 × 10⁻¹⁵) × 263,432 × 6,000] = 392,964,873 bits ≈ 46.85 MiB (equivalent to 12 nominal 4-MiB chips, only if their full arrays receive equivalent fluence).

**Energy qualification:** The simulated field contains a broad neutron spectrum. Treating its entire fluence as if it had the measured 1.2 MeV cross-section is a provisional approximation, not an energy-resolved prediction. A final estimate requires the spectrum-weighted response B P ∫ σₙ(E) dΦₙ(E).

## Configuration 2: direct-electron exposure

Planning scenario: direct 200 MeV electrons; 0.01 nC/pulse and a uniform 1 cm² beam area at the chip. The beam footprint, array coverage, and pulse structure are not confirmed.

| Input | Value | Basis |
|---|---|---|
| Beam charge | 0.01 nC/pulse | Assumed low-charge setting |
| Beam area on the chip | 1 cm², uniform | Assumed placeholder; must verify with CLEAR |
| Electron SEU cross-section | (4.74 ± 2.20) × 10⁻¹⁸ cm²/bit, at 200 MeV | [3], ISSI measurement |
| Exposed SRAM capacity | 33,554,432 bits (one 4-MiB chip) | Full exposure assumed |

- Electrons per pulse: 0.01 × (6.241509 × 10⁹ electrons/nC) = 62,415,091 electrons/pulse.
- Electron fluence per pulse: 62,415,091 / 1 cm² = 6.241509 × 10⁷ electrons/cm²/pulse.
- Expected upsets per pulse, one chip: (33,554,432 bits) × (4.74 × 10⁻¹⁸ cm²/bit) × (6.241509 × 10⁷ electrons/cm²) = 0.009927 upsets/pulse.
- Expected upsets over 6,000 pulses, one chip: 0.009927 × 6,000 = 59.56 upsets.
- Required exposed capacity for 1,000 expected upsets: 1,000 / [(4.74 × 10⁻¹⁸) × (6.241509 × 10⁷) × 6,000] = 563,353,247 bits ≈ 67.16 MiB (equivalent to 17 nominal 4-MiB chips, only if their full arrays receive equivalent fluence).

**Geometry qualification:** Increasing the number of physical chips does not necessarily increase the total effectively exposed capacity at fixed beam charge. A real beam has a spatial profile, and the irradiation geometry must be checked before treating 67.16 MiB as practical.

## Comparison and feasibility implications

| Quantity | Configuration 1: neutrons | Configuration 2: electrons |
|---|---|---|
| Assumed beam charge | 30 nC/pulse | 0.01 nC/pulse |
| Per-bit cross-section used | 1.61 × 10⁻¹⁵ cm²/bit (1.2 MeV n) | 4.74 × 10⁻¹⁸ cm²/bit (200 MeV e⁻) |
| Fluence at device per pulse | 263,432 n/cm² | 62,415,091 e⁻/cm² |
| Expected upsets/pulse, one 4-MiB chip | 0.01423 | 0.00993 |
| Expected upsets/6,000 pulses, one chip | 85.39 | 59.56 |
| Exposed memory needed for 1,000 expected upsets over 6,000 pulses | 46.85 MiB | 67.16 MiB |
| Pulses for 1,000 expected upsets using only one 4-MiB chip | 70,268 | 100,736 |
| Corresponding time at an assumed continuous 10 Hz | 117.1 min | 167.9 min |

**Interpretation:** Under these example settings, a single 4-MiB device would not be expected to produce ~1,000 upsets in 6,000 pulses. The required MiB values are irradiated-capacity equivalents, not a verified physical memory-board design. Experimental counts are stochastic; all values are expectations.

**Remaining checks:** Confirm the beam charge, bunch/train structure, usable repetition rate and time allocation; validate the Geant4 spectrum and detector geometry; fold the neutron energy distribution with σ(E); obtain the direct-electron spot size and beam profile at the chip; and settle the actual device, address mapping and readout approach. The large published uncertainty on the electron cross-section also affects the inferred memory requirement.

## References

1. BURST team Geant4 results. `burst_sim/results_flux.json`. Input model: 200 MeV electron primaries, 2 cm W, 10 cm Pb, 50 cm score sphere, 80°–100° side region. Simulated, not measured.
2. Cecchetto, M., et al. (2021). "0.1–10 MeV Neutron Soft Error Rate in Accelerator and Atmospheric Environments." IEEE Transactions on Nuclear Science, 68. [DOI: 10.1109/TNS.2021.3064666](https://doi.org/10.1109/TNS.2021.3064666). Table I identifies ISSI IS61WV204816BLL-10TLI; Table III gives σₙ(1.2 MeV) = 1.61 × 10⁻¹⁵ cm²/bit.
3. Coronetti, A., et al. (2020). "SEU Characterization of Commercial and Custom-Designed SRAMs Based on 90 nm Technology and Below." IEEE Radiation Effects Data Workshop. [DOI: 10.1109/REDW51883.2020.9325822](https://doi.org/10.1109/REDW51883.2020.9325822). ISSI 200 MeV electron SEU cross-section: (4.74 ± 2.20) × 10⁻¹⁸ cm²/bit.
4. NIST CODATA. Elementary charge, exactly 1.602176634 × 10⁻¹⁹ C. [Reference](https://physics.nist.gov/cgi-bin/cuu/Value?e).

---

## Review notes (not part of Logan's text)

All arithmetic above was reproduced independently by `burst_sim/rate_calc.py`. Open points sent back to Logan:

1. **Neutron energy.** Behind 10 cm of lead the simulated neutrons have a mean energy of 0.87 MeV; about 30% are above 1 MeV and 66% above 0.5 MeV. Using σ(1.2 MeV) for all of them is likely an overestimate. `rate_calc.py` gives the range under two bounding assumptions (σ = 0 below 0.5 MeV, and below 1 MeV) until the full σ(E) from [2, Table III] is folded with the spectrum. The rate drops by up to 3.3×.
2. **Direct-electron geometry.** In a ~1 cm² beam, extra chips side by side are outside the beam. More memory means stacking boards along the beam, which needs simulating.
3. **Dose.** 0.01 nC/pulse on 1 cm² is ~0.017 Gy(Si) per pulse: ~100 Gy per 6,000 pulses, ~1.7 kGy for 1,000 flips on one chip. The device's dose tolerance needs checking.
4. **Run length and flip target.** The layout-blind cluster test needs ~2,000 flips for the weakest clustering simulated. Results are tabulated as chips needed against beam time, for 1,000 and 2,000 flips.
