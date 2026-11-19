# Sashreek's work package

Your part of BURST: the readout system and everything between the memory chip and the analysis. You build it; this is the spec, the order, and how you know each piece is done. Deadline for the proposal: **12 March 2027, 23:59 CET**.

What already exists for you to build against:
- `burst_sim/beam_analysis/LOG_FORMAT.md`: the exact files your system must produce.
- `burst_sim/beam_analysis/analyze_beam.py`: reads those files. If it runs cleanly on your output, your output is right.
- `burst_sim/beam_analysis/fake_beam_log.py`: an example of correct output.

---

## 1. Choose the microcontroller and design the memory board

**Goal:** read 2 chips × 2M words × 16 bits in about 1 second.

- The ISSI IS61WV204816BLL is a parallel asynchronous SRAM: 21 address lines, 16 data lines, plus chip-enable, output-enable and write-enable (and byte enables). That is about 40 signals per chip. Shared address/data bus, separate chip-enables.
- Look for a microcontroller with a hardware external-memory controller (STM32's "FMC/FSMC" handles asynchronous SRAM directly; check which boards expose all the pins). The alternative is driving the bus from GPIO, which is slower and needs more pins.
- Check the chip's package and pinout in the datasheet. You will need an adapter or a small custom board.
- Plan the physical layout: only the memory board sits in the radiation field. The microcontroller stays outside it, behind shielding or several metres away, because it can upset too. Long cables slow the bus; measure, don't guess.

**Done when:** you have a chosen board, a wiring diagram, and a calculation of read time per chip from the datasheet timings.

## 2. Firmware: write, read back, log, rewrite

Loop for each readout:
1. Read every word of each chip, compare with the expected pattern.
2. For every wrong word, send `readout, chip, addr, expected, read`.
3. Rewrite the wrong words (this is the scrub).
4. Send one `readouts.csv` row per chip: readout number, first and last beam pulse, timestamps, words read, status.

Requirements:
- Count beam pulses from a trigger input (CLEAR's timing signal; see section 6). Without it, use timestamps and match pulses offline.
- Report a readout even when it found nothing. Zero-flip readouts are data.
- Detect your own failures: a read that stops early gets status `timeout`; a reboot gets `reset`. A watchdog should restart a hung loop.
- Patterns: support checkerboard, all-zeros and all-ones, chosen at run start.

**Done when:** a laptop script turns the serial stream into `run.json`, `readouts.csv` and `flips.csv` that `analyze_beam.py` reads without errors.

## 3. Protect the chip and know when it misbehaves

- **Supply current monitor** on each chip (a current-sense chip on the 3.3 V line). Log it every readout. Li et al. 2022 saw this chip's current double with dose, and a sudden jump means latch-up.
- **Power cycling:** be able to cut and restore each chip's supply from firmware if the current jumps. Log it as status `power_glitch`.
- **SEFI handling:** if one readout shows hundreds of errors, log them all anyway; the analysis flags them.

**Done when:** you can show current readings in the log, and a forced power cycle is logged and recovered from.

## 4. Bench test with no beam

There is no radiation at your desk, so fake the flips in hardware:
- Add a test mode where the firmware deliberately writes wrong values into chosen words between readouts (single bits, pairs in neighbouring addresses, a burst of hundreds).
- Run for an hour. Run `analyze_beam.py` on the result.
- Check: every planted error is found once, the burst is flagged as SEFI-like, zero-error readouts are present, and the timing is stable.
- Also run with nothing planted for a few hours. Every flip you see there is a real background or a bug.

**Done when:** planted errors in = errors found out, and the clean run shows zero (or explained) flips.

## 5. Your science piece: the learned codeword layout

The simulation says that at CLEAR rates only bursts break error correction, and that a codeword layout learned from the chip's first flips removes them (section 9 of `BURST_preliminary_results.md`). That is your hypothesis to own.
- Understand `burst_sim/decoder_chip.py` and the codes section of `analyze_beam.py` well enough to explain them without notes.
- Stretch goal: run the software error correction live on the microcontroller with the learned layout, and compare with one-word codewords during the run.

**Done when:** you can explain, on a whiteboard, why accumulated flips don't matter at CLEAR rates and how the learned layout is chosen.

## 6. Questions to send (through your coach, once you have one)

To the BL4S / CLEAR team:
1. Is a beam trigger or timing signal available to our electronics?
2. Can we get the charge of every pulse (or every second) as a data file?
3. What is the lowest charge per pulse, and the spot size at the test position?
4. Can we bring our own microcontroller and memory boards, and how long are the cables from the beam area to where we sit?
5. Are the 2027 Beams & Detectors parameters final?

## 7. Proposal sections you write

You write these yourself (BL4S rule): the hypothesis, the readout method, and the readout part of feasibility. Use the numbers from sections 8 and 9 of the results document and your own bench-test results.

---

## Suggested timeline

| By | Milestone |
|---|---|
| 6 Dec 2026 | Board chosen, wiring diagram, read-time calculation (1) |
| 10 Jan 2027 | Firmware reads, logs, rewrites one chip; laptop script writes the CSVs (2) |
| 31 Jan 2027 | Two chips, current monitor, power cycling, watchdog (2, 3) |
| 14 Feb 2027 | Bench test passes: planted errors in = found out (4) |
| 28 Feb 2027 | Your proposal sections drafted, with bench results (5, 7) |
| 12 Mar 2027 | Submission |
