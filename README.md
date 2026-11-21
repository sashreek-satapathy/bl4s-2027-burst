# BURST: do beam-induced memory errors come in bursts?

Working repo for our entry to CERN's [Beamline for Schools 2027](https://beamlineforschools.cern/) competition.

**The question.** When memory chips are irradiated at CERN's CLEAR electron accelerator, are the bit flips independent, or do they cluster in space and time? How much does clustering hurt a standard error-correcting code, and what fixes it?

**Status.** Proposal in preparation. Deadline: 12 March 2027, 23:59 CET. No beam data exists yet; everything numerical here is simulation.

## Project tracker

Everything left until submission, with due dates and a live progress meter: see the pinned **BURST tracker** issue in this repo's Issues tab. Nobody is assigned; pick an open task, say so in the team chat, tick it when done.

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
- With a real 40 nm SRAM and published cross-sections, one 4 MiB chip gets about 0.011 neutron-induced flips per pulse at 30 nC behind lead (0.031 at 30 cm). Two chips and one hour of beam give 2,000 flips. Behind polyethylene, thermal neutrons cause most of the upsets.
- On the real chip at CLEAR rates, accumulated flips never break the code; only bursts do. Learning which address bits to spread a codeword over from the chip's first 1,000 flips brings burst failures down to chance level, without the layout.
- **Validated against CERN data:** our Geant4 + cross-section chain reproduces CERN's measured upset rates in the same chip at CLEAR (Lerner et al. 2023, aluminium target) within 26% at all six positions (`burst_sim/validate_l23.py`, section 10 of the results).
- The readout can be slow: sweeps of 8 s or even 46 s give the same analysis results as 1 s, so the memory board can sit 20 m away on a simple serial link (`hardware/OPTION_B.md`).
- Adaptive scrubbing cuts failures from accumulated flips by about 40% but does almost nothing against bursts, and at CLEAR rates there is no accumulation for it to fix.

**Cluster boundary note:** Clusters generated near the edge of the simulated memory array may be truncated by the chip boundary. Their actual sizes can therefore be smaller than their requested target sizes.

![Decoder result](burst_sim/figures/fig3_decoder.png)

## Run the simulation

```bash
cd burst_sim
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python burst_sim.py
.venv/bin/python blind_bitmap.py
.venv/bin/python rate_calc.py      # uses the committed Geant4 output in flux_raw/
.venv/bin/python decoder_chip.py   # about 10 seconds
```

These two take under 30 seconds together and rewrite `figures/` and the results JSON files. The random seed is fixed, so results reproduce exactly.

CERN validation: `.venv/bin/python validate_l23.py all --events 500000 --seeds 8` (about 30 minutes on a 10-core laptop), then `validate_l23.py report`.

The beam simulation needs Geant4 (`pip install geant4-pybind`, plus a 2 GB data download on first use): `.venv/bin/python flux_sim.py all --events 10000`, about 10 minutes on a laptop.

## Biggest open questions

1. Thermal neutrons scattered back from the hall walls. They are not simulated, and the reference chip is about as sensitive to them as to fast neutrons.
2. Which memory devices to use, and whether their address scrambling is the simple kind our layout-blind method assumes.
3. CLEAR beam parameters and whether teams may bring their own electronics.

## Competition rules that matter

At least five team members, all enrolled in secondary or high school in 2026/27. Up to 1000 words, plus an optional 200-word outreach section. The students write the proposal; the coach advises.
