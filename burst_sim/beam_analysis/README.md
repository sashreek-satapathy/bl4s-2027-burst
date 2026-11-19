# Beam-day analysis tool

Turns one run's flip log into a report. The log format is in [LOG_FORMAT.md](LOG_FORMAT.md).

```bash
cd burst_sim/beam_analysis
../.venv/bin/python fake_beam_log.py /tmp/run1            # a fake run with known truth
../.venv/bin/python analyze_beam.py /tmp/run1             # writes /tmp/run1/report/
```

The report (`report.md`, `report.json`, `summary.png`) covers:

1. **Data quality:** drops incomplete readouts, and flags SEFI-like readouts (far more flips than the beam charge explains, p < 1e-9) for separate study.
2. **Cross-section per bit** for each chip. The 95% range comes from independent events (clusters counted once), because flips in one cluster are not independent.
3. **Time:** spread of flips per readout, plus two tests that spatial clusters cannot fake: correlation between neighbouring readouts (at 1, 10 and 60 readouts per block) and drift over the run.
4. **Space, without the chip layout:** repeated address-difference signatures, rebuilt clusters, shuffled-address control.
5. **Codeword layout:** learns safe address bits on the first half of the run, tests on the second half against one-word and blind groupings.
6. **Scrub replay:** failures if the memory had been rewritten less often.

`fake_beam_log.py` options: `--mean-cluster`, `--layout side_by_side|interleaved`, `--minutes`, `--bunching` (real time bunching), `--beam-off`, `--no-faults` (no planted SEFI or timeout).

## Validation on fake runs (60 minutes, 2 chips, ~2,300 flips each)

| Check | Result |
|---|---|
| Planted SEFI and incomplete readout caught | 48 of 48 runs |
| True cross-section inside the 95% range | 96% (25 runs × 2 chips, per cluster size) |
| Mean cluster size, rebuilt vs injected | 1.043 vs 1.047; 1.192 vs 1.202 |
| Signatures learned on shuffled addresses | 0 in every run |
| Learned codeword layout avoids the neighbour address bits | every clustered run; 0 failures on the test half |
| Time test false alarms at 5%, no real bunching | 0–8% at cluster sizes 1.0, 1.2, 1.5 |
| Real bunching detected (rate wandering ±10 / 20 / 30%) | 8% / 72% / 100% |

Limits: bunching within one readout (10 pulses) is invisible; the fake chip uses the simple address scramble and line-shaped clusters assumed in `decoder_chip.py`.
