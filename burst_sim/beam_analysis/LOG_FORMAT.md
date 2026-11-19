# Beam-day log format

What the readout microcontroller writes, and what `analyze_beam.py` reads. One folder per run.

## `run.json`, filled in by hand before the run

| Key | Example | Meaning |
|---|---|---|
| `run` | `"pb10_30cm_r1"` | Run name |
| `configuration` | `"W 2 cm + 10 cm lead, 90 deg, 30 cm"` | Setup, free text |
| `chips` | `2` | Number of memory chips read |
| `addr_bits` | `21` | Word address bits (21 = 2M words) |
| `word_bits` | `16` | Bits per word |
| `fluence_per_nC` | `24400` | Particles per cm² at the chip per nC of beam (from simulation or a dosimeter) |
| `pattern` | `"checkerboard"` | Pattern written: `checkerboard`, `zeros`, `ones` |
| `beam` | `true` | `false` for a beam-off control run |

## `readouts.csv`, one row per chip per readout

```
readout,chip,first_pulse,last_pulse,charge_nC,t_start,t_end,words_read,status
0,0,0,9,301.2,1795000000.10,1795000000.95,2097152,ok
```

- `readout`: counts up from 0; the same number for every chip read in that cycle.
- `first_pulse`, `last_pulse`: beam pulses that hit since the previous rewrite of this chip.
- `charge_nC`: summed beam charge over those pulses, from the CLEAR charge monitor.
- `words_read`: should equal 2^addr_bits; anything less means an incomplete read.
- `status`: `ok`, or `timeout`, `reset`, `power_glitch` (the microcontroller's own judgement).

Every readout appears here **even if it found no flips**. Zero-flip readouts are data.

## `flips.csv`, one row per word that read back wrong

```
readout,chip,addr,expected,read
0,1,1234567,5555,5575
```

- `addr`: logical word address, decimal.
- `expected`, `read`: the word written and the word read back, hexadecimal.

A word with several wrong bits is one row; the analysis splits it into bits. After logging, the microcontroller rewrites the word (the rewrite is the scrub).
