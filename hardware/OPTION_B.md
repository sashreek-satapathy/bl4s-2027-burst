# Option B: a simple memory board, 20 m from the readout

This is the plan to use while we wait for CERN to say whether a shielded controller box near the beam is allowed (Option C). The memory board in the beam holds no processor, only simple logic chips. The Nucleo sits about 20 m away and sends about a dozen signals over differential twisted pairs.

You design the schematic and write the firmware yourself. This note gives the architecture, the signal list and a first timing budget for you to check against the datasheets.

## Block diagram

```
 IN THE BEAM (disposable, build at least 3)              ~20 m           OUTSIDE (Nucleo-F429ZI)
 ┌──────────────────────────────────────────────┐   4 × Cat6 cables   ┌──────────────────────────┐
 │ address counter (2 × 12-bit, cascaded) → A0-A20 │◄── ACLK, ARST ───│ timer / GPIO              │
 │                                                │                   │                          │
 │ SRAM 0 ┐                                       │◄── CE0, CE1 ─────│ GPIO                     │
 │ SRAM 1 ┘ shared bus, UB = LB = low            │◄── OE, WE ───────│ GPIO                     │
 │                                                │                   │                          │
 │ DQ0-15 → 2 × PISO shift register (read)       │── SDO ──────────►│ SPI (receive)            │
 │        ← 2 × SIPO shift register, tri-state    │◄── SCLK, PL ─────│ SPI clock                │
 │          (write)                                │◄── SDI, RCLK, DOE│ SPI MOSI / GPIO          │
 │                                                │── SCLK echo ────►│ clock for the receive SPI│
 │ RS-485/LVDS transceivers, temperature sensor  │                   │ current sense, load switch│
 └──────────────────────────────────────────────┘ + separate 3.3 V supply pair per chip └─────┘
```

## Signals over the cable

| # | Signal | Direction | What it does |
|---|---|---|---|
| 1 | ACLK | to board | steps the address counter by one |
| 2 | ARST | to board | resets the address to 0 |
| 3 | CE0 | to board | selects SRAM 0 |
| 4 | CE1 | to board | selects SRAM 1 |
| 5 | OE | to board | SRAM output enable (read) |
| 6 | WE | to board | SRAM write enable |
| 7 | PL | to board | loads the 16 data bits into the read shift registers |
| 8 | SCLK | to board | shift clock (read and write) |
| 9 | SDI | to board | serial data for writing |
| 10 | RCLK | to board | latches the write shift registers |
| 11 | DOE | to board | turns on the write shift registers' outputs onto the data bus (off while reading) |
| 12 | SDO | from board | serial read data |
| 13 | SCLK echo | from board | the shift clock sent back next to SDO (see timing) |
| 14 | SDO2 (optional) | from board | second read line: two 8-bit chains instead of one 16-bit chain, twice as fast |

That's 13–14 pairs, so 4 Cat6 cables (16 pairs) with spares. Power runs on a separate cable, so the current sensors and load switches stay on the Nucleo side.

Avoid driving the bus from both ends at once: DOE must be off whenever OE is on.

## Part candidates (check the 3.3 V speed in each datasheet)

| Job | Candidate families |
|---|---|
| 21-bit address counter | 2 × 74HC4040 (12-bit ripple counter) or a 74LV/74LVC equivalent |
| Read shift register | 2 × 74HC165 / SN74LV165A |
| Write shift register (tri-state outputs) | 2 × 74HC595 / SN74LV595A |
| Line drivers over 20 m | RS-485 transceivers rated ≥ 20 Mbit/s, or LVDS drivers and receivers |
| Temperature | any I²C or 1-wire sensor, read through the same cable or a spare pair |

A ripple counter's high bits settle late. Budget the worst-case ripple time from the datasheet, at 3.3 V, after each ACLK.

## Timing (first estimate, check every number)

Cable delay is about 5 ns/m, so 100 ns each way. With transceivers, a bit sent back on SDO arrives about 240 ns after the clock edge that sent it.

| Design | Shift clock | Per word | Sweep of one chip (2M words) | Both chips |
|---|---|---|---|---|
| No clock echo: sample SDO on the Nucleo's own clock | ≤ about 1.5 MHz (half a period must cover about 240 ns) | ~11 µs | ~23 s | ~46 s |
| **Clock echo** (the board sends SCLK back next to SDO; the Nucleo receives with that clock) | 10 MHz | ~2.2 µs (16 shifts + about 0.6 µs counter settle and load) | ~4.6 s | **~9 s** |
| Clock echo + two read lines (8 bits each) | 10 MHz | ~1.4 µs | ~2.9 s | ~6 s |

Recommended: clock echo, one read line to start, room on the board for the second.

**The analysis still works with slower readouts.** I reran the fake run with readouts every 8 s (80 pulses) instead of 1 s. Cross-section, mean cluster size, learned signatures, the learned codeword layout (0 failures), and the SEFI and timeout flags all came out the same. At about 0.3 flips per second per chip, an 8-second readout sees about 2.5 flips per chip.

## Two firmware rules that Option B needs

1. **Make the pattern depend on the address.** If the address counter skips a step (an upset in the counter, or a lost ACLK edge), a plain checkerboard can look perfect, because every second word holds the same value. Use something like `expected = (addr & 0xFFFF) ^ 0x5555`. Then a counter fault shows as a whole run of wrong words, and the analysis flags it as SEFI-like. Write the pattern name into `run.json`; `flips.csv` already stores `expected` per word, so the analysis needs no change.
2. **Re-read every mismatch.** The shift registers and transceivers sit in the beam too. A flip in a shift register disappears on the next read; a flip in the SRAM stays until you rewrite it. If the word is correct on re-read, log it as a transfer error (count it, but don't put it in `flips.csv`). That count is itself a result: an upset rate for the logic chips.

## Bench tests to add (section 4 of the work package)

- Pull ACLK low for one step mid-sweep, to simulate a lost edge. Check it shows as a SEFI-like readout.
- Inject a wrong bit into SDO with a test switch, to simulate a transfer error. Check that the re-read catches it.
- Run the full 20 m of cable on the bench. Measure the real round-trip delay with a scope and set the clock from that.

## Your next steps

1. Pick the exact parts and confirm their 3.3 V timings in the datasheets.
2. Make the pin map: SRAM pin → board chip → cable pair → Nucleo pin.
3. Redo the timing table with the datasheet numbers.
4. Draw the board schematic in KiCad.
