# Option B: a simple memory board, 20 m from the readout

This is the plan while we wait for CERN to say whether a shielded controller box near the beam is allowed (Option C). The memory board in the beam holds no processor, only simple logic chips. The Nucleo sits about 20 m away and drives the board over differential pairs.

You design the schematic and write the firmware. This note gives the chosen parts, the signal list and a timing budget built from the datasheet numbers (VCC = 3.3 V, −40 to 85 °C, 50 pF load, worst case).

## Block diagram

```
 IN THE BEAM (disposable, build at least 3)              ~20 m           OUTSIDE (Nucleo-F429ZI)
 ┌──────────────────────────────────────────────┐   4 × Cat6 cables   ┌──────────────────────────┐
 │ 2 × SN74LV4040A ripple counter → A0-A20       │◄── ACLK, ARST ───│ GPIO                      │
 │                                                │                   │                          │
 │ SRAM 0 ┐                                       │◄── CE0, CE1 ─────│ GPIO                     │
 │ SRAM 1 ┘ shared bus, UB = LB = low            │◄── OE, WE ───────│ GPIO                     │
 │                                                │                   │                          │
 │ DQ0-15 → 2 × SN74LV165A (read)                │── SDO ──────────►│ SPI MISO (master mode)   │
 │        ← 2 × SN74LV595A, tri-state (write)    │◄── SCLK, PL ─────│ SPI SCK / GPIO           │
 │                                                │◄── SDI, RCLK, DOE│ SPI MOSI / GPIO          │
 │ 3 × AM26LV32E receivers, 1 × AM26LV31E driver │                   │ 3 × AM26LV31E, 1 × AM26LV32E│
 │ DS18B20 temperature (1-Wire, own pair)         │                   │ TPS2553-1 + INA226 per SRAM│
 └──────────────────────────────────────────────┘ + separate power cable └──────────────────┘
```

## Signals over the cable

| # | Signal | Direction | What it does | Idle / cable-unplugged state |
|---|---|---|---|---|
| 1 | ACLK | to board | steps the address counter (falling edge) | high |
| 2 | ARST | to board | clears the address to 0 (active high) | high = held at 0 |
| 3 | CE0 | to board | selects SRAM 0 (active low) | high = off |
| 4 | CE1 | to board | selects SRAM 1 (active low) | high = off |
| 5 | OE | to board | SRAM output enable (active low) | high = off |
| 6 | WE | to board | SRAM write enable (active low) | high = off |
| 7 | PL | to board | loads the 16 data bits into the '165s (active low) | high |
| 8 | SCLK | to board | shift clock for both the '165s and the '595s | — |
| 9 | SDI | to board | serial write data into the '595s | — |
| 10 | RCLK | to board | latches the '595 outputs | — |
| 11 | DOE | to board | '595 output enable onto the data bus (active low) | high = off |
| 12 | SDO | from board | serial read data | — |
| 13 | SDO2 (optional) | from board | second read line, two 8-bit chains | — |
| 14 | 1-Wire | both | DS18B20 temperature, plain pair, not through the transceivers | — |

**The clock echo is dropped.** The timing below shows that a full-period sample works without it, and the analysis is fine with slow sweeps (see below). That frees a pair.

**Failsafe for free.** The AM26LV32E puts its output high when its input is open. Every control above is chosen so that "high" is the safe state: with the cable unplugged, both SRAMs are deselected, nothing writes, and the counter is held at 0.

11 pairs go to the board and 1–2 come back, plus the 1-Wire pair: 13–14 of the 16 pairs in 4 Cat6 cables, with 2–3 spare. Power runs on a separate cable.

## Chosen parts

| Job | Part | Qty (board / Nucleo side) | Key 3.3 V numbers (datasheet) |
|---|---|---|---|
| Address counter, 21 bits | **SN74LV4040A** (12-bit ripple, falling-edge clock, active-high CLR) | 2 / 0 | CLK→QA ≤ 17.5 ns; each further stage +≤ 5 ns (Δtpd); fmax ≥ 50 MHz; CLR pulse ≥ 5 ns; CLR off before CLK↓ ≥ 5 ns (SCES226K, §4.7, 4.10) |
| Read shift register | **SN74LV165A** | 2 / 0 | fmax ≥ 50 MHz; CLK→QH ≤ 16.9 ns; data setup before SH/LD↑ ≥ 8.5 ns; SH/LD low ≥ 9 ns; SH/LD high before CLK↑ ≥ 6 ns (SCLS402R, §6.7, 6.10) |
| Write shift register, tri-state | **SN74LV595A** | 2 / 0 | fmax ≥ 50 MHz; SER setup ≥ 3.5 ns, hold ≥ 1.5 ns; SRCLK↑ before RCLK↑ ≥ 8.5 ns; OE→Q enable ≤ 17 ns (SCLS414T, §6.7, 6.10) |
| Differential driver (RS-422) | **AM26LV31E** (quad) | 1 / 3 | 3.0–3.6 V; delay 4–12 ns; up to 32 MHz (SLLS848C, §5.6) |
| Differential receiver (RS-422) | **AM26LV32E** (quad, open-input failsafe) | 3 / 1 | 3.0–3.6 V; delay 8–26 ns; ±200 mV threshold; up to 32 MHz; ≤ 17 mA supply each (SLLS849E, §6.3, 6.6) |
| SRAM power switch, latch-up cut-off | **TPS2553-1** (latch-off version) | 0 / 2 | current limit 75–1700 mA set by one resistor; responds to a short in about 2 µs; 2.5–6.5 V in (SLVS841) |
| SRAM current logging | **INA226** | 0 / 2 | 0–36 V bus; conversion 140 µs fastest; ALERT pin trips on a shunt-voltage limit without the MCU polling |
| Temperature | **DS18B20** (1-Wire) | 1 / 0 | to check: datasheet did not download; long-line guidance is Maxim app note 148 |

Why RS-422 drivers and receivers rather than RS-485 transceivers: every signal goes one way only, so one-direction quad parts save chips and enable pins. The THVD1450 (RS-485, 50 Mbit/s) also works, but its receiver delay is up to 40 ns and it is one channel per chip.

Termination: 100 Ω across each pair at the receiving end (Cat6 is 100 Ω). Each terminated, driven pair draws about 26 mA (2.6 V across 100 Ω) from its driver's supply.

## Timing budget (datasheet worst case)

**Cable path, one way:** driver 4–12 ns + 20 m of cable 90–105 ns + receiver 8–26 ns = **102–143 ns**. Any two signals can arrive up to **41 ns** apart.

**Address settle after an ACLK edge reaches the board:** A11 at 17.5 + 11 × 5 = 72.5 ns. The second counter is clocked by A11 falling, so A20 settles at 72.5 + 17.5 + 8 × 5 = **130 ns**.

**When to send PL after ACLK** (Nucleo time, both travel the same path): 130 ns counter + 10 ns SRAM access (-10 grade, to check) + 8.5 ns '165 setup + 41 ns skew = **≥ 190 ns**.

**Reading the bits back without a clock echo.** The Nucleo runs SPI as master and samples SDO on the *rising* edge, the same edge on which the '165 shifts. Each bit then has a full clock period to travel down and back:

- round trip SCLK → board → '165 → SDO → Nucleo: **205–303 ns**
- the period must exceed 303 ns plus the STM32 input setup (a few ns)
- the 16 samples read H (present right after the load), then G, F, … A of each '165 in turn

| SPI clock (STM32F429, 45 MHz APB1) | Period | Setup margin | Per word | One chip (2M words) | Both chips |
|---|---|---|---|---|---|
| 45 / 16 = **2.81 MHz** | 356 ns | 48 ns | ~6.8 µs | ~14 s | **~28 s** |
| 45 / 32 = 1.41 MHz (fallback) | 711 ns | 403 ns | ~12.5 µs | ~26 s | ~52 s |

"Per word" includes about 0.7 µs of firmware overhead for the ACLK and PL pulses; measure it.

Start at 1.41 MHz, measure the real round trip on the bench with all 20 m of cable, then move to 2.81 MHz if it is below about 300 ns. **Both speeds are fast enough.** The pile-up check (derivation #1) gave about 4e-3 false failures per hour even at 46 s sweeps, against about 70 real burst failures per hour. The fake beam run gave the same analysis results at 1 s and 46 s.

**Writing** is not time-critical: SDI and SCLK travel together, so the 41 ns skew needs a half period above 45 ns, which is easy at 2.81 MHz. Then: RCLK, DOE low (≤ 17 ns + skew), then a WE low pulse. The SRAM WE pulse width and data setup are still to be checked in the ISSI datasheet.

## Power and protection

- **Separate supply per SRAM**, switched on the Nucleo side by a TPS2553-1 and logged by an INA226. Two levels of protection:
  - The INA226 ALERT trips at a low threshold (a jump of tens of mA above normal), and the Nucleo turns the switch off and logs a latch-up candidate.
  - The TPS2553-1 cuts off in about 2 µs at its hard limit (set to about 100–150 mA) even if the firmware hangs.
- **Voltage drop.** 24 AWG Cat6 is about 0.084 Ω/m, so a 20 m out-and-back pair is about 3.4 Ω. At 10–30 mA SRAM current the drop is 0.03–0.1 V, which is fine. At latch-up currents the switch trips anyway.
- **Logic supply.** 3 receivers (up to 51 mA) + 1–2 driven return pairs (26 mA each) + logic is about 100–150 mA, which would drop up to 0.5 V over Cat6. Send 5 V on a separate cable with thicker cores (for example 0.5 mm²) and regulate to 3.3 V on the board with an LDO. Keep the SRAM supplies separate from it, so the INA226 sees only SRAM current.
- **SRAM operating current is unknown** until the ISSI datasheet is read. It sets the INA226 baseline and the TPS2553 resistor.

## Two firmware rules that Option B needs

1. **Make the pattern depend on the address.** If the address counter skips a step (an upset in the counter, or a lost ACLK edge), a plain checkerboard can look perfect, because every second word holds the same value. Use something like `expected = (addr & 0xFFFF) ^ 0x5555`. Then a counter fault shows as a whole run of wrong words, and the analysis flags it as SEFI-like. Write the pattern name into `run.json`; `flips.csv` already stores `expected` per word, so the analysis needs no change.
2. **Re-read every mismatch.** The shift registers and transceivers sit in the beam too. A flip in a shift register disappears on the next read; a flip in the SRAM stays until you rewrite it. If the word is correct on re-read, log it as a transfer error (count it, but don't put it in `flips.csv`). That count is itself a result: an upset rate for the logic chips.

A third, from the ripple counter: **never step ACLK while WE is low.** The address passes through intermediate values for up to 130 ns while it ripples, so wait at least 190 ns after an ACLK edge before pulling WE low.

## Bench tests to add (section 4 of the work package)

- Pull ACLK low for one step mid-sweep, to simulate a lost edge. Check it shows as a SEFI-like readout.
- Inject a wrong bit into SDO with a test switch, to simulate a transfer error. Check that the re-read catches it.
- Run the full 20 m of cable on the bench. Measure the real round trip (SCLK out to SDO back) with a scope and pick 1.41 or 2.81 MHz from it.
- Unplug each cable during a sweep. Check the board fails safe (SRAMs deselected, nothing written).
- Short an SRAM supply through a resistor. Check the INA226 alert and the TPS2553 cut-off both fire.

## Still to check

| Item | Why it matters | Where |
|---|---|---|
| ISSI IS61WV204816BLL: tAA, tOE, tWP, tSD, ICC, package | SRAM part of the timing and the current baseline. issi.com blocked automated download | ISSI datasheet, download by hand |
| DS18B20 over 20 m | 1-Wire range with a simple pull-up | DS18B20 datasheet, Maxim app note 148 |
| Cat6 propagation speed | 90–105 ns assumed for 20 m | cable spec (NVP), or measure on the bench |
| STM32F429 SPI input setup time and real GPIO overhead | margin at 2.81 MHz | STM32F429 datasheet, scope on the bench |

## Your next steps

1. Download the ISSI datasheet by hand and fill in the SRAM column of the timing above.
2. Make the pin map: SRAM pin → board chip → cable pair → Nucleo pin.
3. Draw the board schematic in KiCad.
