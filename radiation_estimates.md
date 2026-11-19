# Radiation physics: preliminary SEU-rate and memory-size estimates

**Author:** Logan Piñeiro. First version 2026-11-18, update 2026-11-19. Copied here unchanged apart from formatting; review notes are at the end and are not part of Logan's text.

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

## Update 2026-11-19 (Logan)

### 1. Neutron cross-sections

I found the measured neutron upset cross-sections for our ISSI SRAM in Cecchetto et al. (2021), Table III. The measurements cover three different neutron energies, which should help us get a more accurate upset rate using the Geant4 neutron spectrum.

| Neutron energy | Upset cross-section (cm²/bit) |
|---|---|
| 0.144 MeV | 3.68 × 10⁻¹⁶ |
| 1.2 MeV | 1.61 × 10⁻¹⁵ |
| 17 MeV | 1.91 × 10⁻¹⁴ |

The paper also provides a fitted neutron-response function, which we can use to estimate the cross-section between measured energies.

| Weibull parameter | Value |
|---|---|
| Saturation cross-section | 1.40 × 10⁻¹⁴ cm²/bit |
| Threshold energy | 0.01 MeV |
| Width | 14.05 MeV |
| Shape | 0.82 |

Since only around 35% of our simulated neutrons are above 1 MeV, I agree that using the 1.2 MeV cross-section for the entire neutron population could overestimate the upset rate. The remaining neutrons still contribute, but their cross-sections are generally smaller. The next step is integrating this energy-dependent response over the Geant4 spectrum rather than treating every neutron as having the same energy.

Source: Cecchetto et al. (2021), [doi:10.1109/TNS.2021.3064666](https://doi.org/10.1109/TNS.2021.3064666).

### 2. Direct-electron dose and chip survival

I found a 2022 study by Li et al. that tested an ISSI IS61WV204816-family 40 nm SRAM under gamma irradiation. The chip remained functional after an accumulated dose of 10 kGy, although its static supply current approximately doubled.

| Beam time | Pulses at 10 Hz | Accumulated dose |
|---|---|---|
| 10 minutes | 6,000 | 102 Gy |
| 30 minutes | 18,000 | 306 Gy |
| 1 hour | 36,000 | 612 Gy |
| 2 hours | 72,000 | 1,224 Gy |
| One chip, 1,000 expected flips | ~100,736 | ~1.71 kGy |
| One chip, 2,000 expected flips | ~201,472 | ~3.43 kGy |

Based on these results, the ISSI SRAM looks promising in terms of total dose tolerance. Even the estimated dose needed for 2,000 flips is below the 10 kGy level tested in the paper. However, the published test used gamma irradiation rather than pulsed high-energy electrons, so we'd still need to verify the chip's response under our actual beam conditions. This also doesn't guarantee that the supporting electronics would survive the same exposure.

Source: Li et al. (2022), "Effects of Total Ionizing Dose on Transient Ionizing Radiation Upset Sensitivity of 40–180 nm SRAMs." [doi:10.1063/5.0081576](https://doi.org/10.1063/5.0081576).

### 3. Revised memory requirements vs. beam time

Still using the 1.2 MeV cross-section. Chips needed:

| Neutrons (30 nC/pulse, 10 Hz, 2 cm W, 10 cm Pb) | 50 cm: 1,000 | 50 cm: 2,000 | 30 cm: 1,000 | 30 cm: 2,000 |
|---|---|---|---|---|
| 10 min | 12 | 24 | 5 | 9 |
| 30 min | 4 | 8 | 2 | 3 |
| 1 hour | 2 | 4 | 1 | 2 |
| 2 hours | 1 | 2 | 1 | 1 |

| Direct electrons (0.01 nC/pulse, 10 Hz, uniform 1 cm²) | 1,000 flips | 2,000 flips |
|---|---|---|
| 10 min | 17 | 34 |
| 30 min | 6 | 12 |
| 1 hour | 3 | 6 |
| 2 hours | 2 | 3 |

The electron numbers are equivalent amounts of exposed memory, not necessarily a practical number of separate chips; adding chips outside the beam wouldn't increase upsets. We'd need to investigate stacking boards along the beam.

### 4. Moving the neutron chips to 30 cm

Moving from 50 cm to 30 cm increases the estimated neutron fluence by approximately 2.7 times (inverse square). We still need to confirm that a chip can be positioned at 30 cm with the proposed shielding: the current Geant4 setup places the outer edge of the 10 cm lead shield at approximately that radius.

### 5. Thermal-neutron sensitivity and polyethylene

The ISSI IS61WV204816BLL-10TLI responds to thermal neutrons. At 3.3 V, the reported thermal-neutron upset cross-section is σ_thermal = (3.16 ± 0.64) × 10⁻¹⁵ cm²/bit.

This matters for the polyethylene configuration because polyethylene moderates neutrons toward thermal energies. One possible mechanism is neutron capture by boron-10, which produces secondary charged particles capable of upsetting memory cells; we'd need more information about the device materials to establish how much comes from boron-10. We shouldn't assume the polyethylene configuration produces fewer upsets simply because the average neutron energy is lower.

---

## Review notes (not part of Logan's text)

All arithmetic above was reproduced independently by `burst_sim/rate_calc.py`. Open points sent back to Logan:

1. **Neutron energy.** Behind 10 cm of lead the simulated neutrons have a mean energy of 0.87 MeV; about 30% are above 1 MeV and 66% above 0.5 MeV. Using σ(1.2 MeV) for all of them is likely an overestimate. `rate_calc.py` gives the range under two bounding assumptions (σ = 0 below 0.5 MeV, and below 1 MeV) until the full σ(E) from [2, Table III] is folded with the spectrum. The rate drops by up to 3.3×.
2. **Direct-electron geometry.** In a ~1 cm² beam, extra chips side by side are outside the beam. More memory means stacking boards along the beam, which needs simulating.
3. **Dose.** 0.01 nC/pulse on 1 cm² is ~0.017 Gy(Si) per pulse: ~100 Gy per 6,000 pulses, ~1.7 kGy for 1,000 flips on one chip. The device's dose tolerance needs checking.
4. **Run length and flip target.** The layout-blind cluster test needs ~2,000 flips for the weakest clustering simulated. Results are tabulated as chips needed against beam time, for 1,000 and 2,000 flips.

### Notes on the 2026-11-19 update

5. **Fold done.** `rate_calc.py` folds the Weibull fit plus the thermal value (assumed 1/v shape) with each Geant4 spectrum. Behind 10 cm of lead the rate is 0.0112 flips per pulse per chip at 50 cm, 21% below the 1.2 MeV estimate, not up to 3.3× lower. See section 8 of `BURST_preliminary_results.md`.
6. **Thermal term confirmed important.** Behind 10 cm of polyethylene, 75% of the upsets come from the thermal term.
7. **Source for σ_thermal found:** Coronetti et al. 2020 ([3] above), Table II: ILL thermal neutrons, 3.3 V, (3.16 ± 0.64) × 10⁻¹⁵ cm²/bit. The same table also confirms the 200 MeV electron value and gives 2.20 × 10⁻¹⁵ at 2.5 MeV and 9.81 × 10⁻¹⁵ at 14.8 MeV (neutrons, ENEA). The Weibull fit gives 3.0 × 10⁻¹⁵ at 2.5 MeV, about 35% above that point, so the folded rate may be slightly high.
8. **Small correction:** the fraction above 1 MeV behind lead is about 30% once the bin straddling 1 MeV is split properly (35% was a coarser count).
9. **Direct-beam charge:** the same paper says VESPER's laser gun could go only as low as 30 pC per pulse, and that the flux was kept at the low end to avoid beam artefacts such as localised SEFIs. Logan's 0.01 nC (10 pC) per pulse may be below what CLEAR can deliver; with a 0.5–3 cm spot the fluence per pulse changes too. Worth asking CLEAR.
