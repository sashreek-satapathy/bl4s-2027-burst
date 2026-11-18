# BURST: do beam-induced memory errors come in bursts?

Working repo for our entry to CERN's [Beamline for Schools 2027](https://beamlineforschools.cern/) competition.

**The question.** When memory chips are irradiated at CERN's CLEAR electron accelerator, are the bit flips independent, or do they cluster in space and time? How much does clustering hurt a standard error-correcting code, and what fixes it?

**Status.** Proposal in preparation. Deadline: 12 March 2027, 23:59 CET. No beam data exists yet; everything numerical here is simulation.

## Start here

| File | What it is |
|---|---|
| [BURST_preliminary_results.md](BURST_preliminary_results.md) | Results of the fault-injection simulation, what they change in the proposal, open problems, team roles |
| [radiation_estimates.md](radiation_estimates.md) | Upset rates and memory needed for a real chip, from published cross-sections (Logan) |
| [Idea.docx](Idea.docx) | The proposal plan and outline |
| [Reading and Learning.docx](Reading%20and%20Learning.docx) | Reading list, in suggested order |
| [SUGGESTED UPGRADES.docx](SUGGESTED%20UPGRADES.docx) | Proposed upgrades to the base idea |
| [burst_sim/](burst_sim/) | Simulation code, figures and raw numbers |
| [Light_guided_lattice.pdf](Light_guided_lattice.pdf) | LUMEN, an earlier idea for the T9 beamline. Shelved: T9 is not available in 2027 |

## Main findings so far (simulated)

- The planned analysis recovers injected clusters, and a shuffled control shows no false signal.
- Pulse-to-pulse charge jitter fakes a clustering signal unless each pulse is normalised to its measured charge.
- Even 2% of flips arriving as adjacent pairs raises Hamming(7,4) failures about 65-fold when a word's bits are physical neighbours. Interleaving the bits removes the effect.
- A spatial test needs a few hundred flips to detect clustering; a time-only test needs thousands to tens of thousands.
- Clusters can be detected and sized from logical addresses alone, without the chip's physical layout, at a cost of 2 to 4 times more data.
- Geant4: a 2 cm tungsten converter gives about 0.04 neutrons per 200 MeV electron, at about 1 MeV, evenly in all directions. At 90 degrees, 10 cm of lead removes 99% of the photons and none of the neutrons.
- With a real 40 nm SRAM and published cross-sections, one 4 MiB chip gets about 0.004 to 0.014 neutron-induced flips per pulse at 30 nC. A few chips and an hour or two of beam give 2,000 flips.
- Adaptive scrubbing cuts failures from accumulated flips by about 40% but does almost nothing against bursts.

![Decoder result](burst_sim/figures/fig3_decoder.png)

## Run the simulation

```bash
cd burst_sim
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python burst_sim.py
.venv/bin/python blind_bitmap.py
.venv/bin/python rate_calc.py      # uses the committed Geant4 output in flux_raw/
```

These two take under 30 seconds together and rewrite `figures/` and the results JSON files. The random seed is fixed, so results reproduce exactly.

The beam simulation needs Geant4 (`pip install geant4-pybind`, plus a 2 GB data download on first use): `.venv/bin/python flux_sim.py all --events 10000`, about 10 minutes on a laptop.

## Biggest open questions

1. The chip's neutron cross-section below 1.2 MeV. It is measured at 1.2 MeV only, and most simulated neutrons are softer, so the rate is uncertain by a factor of about 3.
2. Which memory devices to use, and whether their address scrambling is the simple kind our layout-blind method assumes.
3. CLEAR beam parameters and whether teams may bring their own electronics.

## Competition rules that matter

At least five team members, all enrolled in secondary or high school in 2026/27. Up to 1000 words, plus an optional 200-word outreach section. The students write the proposal; the coach advises.
