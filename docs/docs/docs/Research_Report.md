# BL4S-2027: Simulation Study of Burst Faults, Spatial Correlations and Error Mitigation

Project status: Preliminary computational study  
Data type: Simulated fault-injection data, not experimental beam data  


Abstract

This project investigates how independent and spatially correlated burst faults affect a simulated memory system. It evaluates statistical methods for identifying correlated errors, compares contiguous and interleaved error-correction arrangements, and explores adaptive scrubbing as a mitigation strategy.

The preliminary simulations show that burst faults produce larger fluctuations in error counts and stronger spatial correlations than independent faults. They also suggest that interleaving can substantially reduce contiguous decoding failures and that adaptive scrubbing can reduce residual errors under the simulated conditions.

These findings are computational results and require further statistical validation and comparison with experimental data.

## 1. Introduction

Radiation-induced faults can affect digital electronics used in particle physics experiments. A fault may occur independently or as part of a burst in which multiple nearby memory cells are affected.

Understanding the difference matters because error-correction systems designed for isolated faults may perform less effectively when errors are spatially correlated.

This project studies three questions:

1. Can statistical measurements distinguish independent faults from burst faults?
2. Can interleaving reduce the impact of spatially correlated errors?
3. Can adaptive scrubbing reduce residual errors compared with fixed-interval scrubbing?

## 2. Simulation methodology

The project uses a computational fault-injection model with a simulated memory size of 917,504 bits.

The model includes:

- Independent and bursty fault injection.
- Statistical analysis using the Fano factor.
- Spatial clustering and adjacent-cell measurements.
- Hamming (7,4) error-correction analysis.
- Comparisons between contiguous, interleaved and shuffled arrangements.
- Fixed and adaptive scrubbing strategies.

The burst model includes an illustrative mean cluster size of 1.5. The simulations are phenomenological: their parameters are assumptions used to explore system behaviour, not measured radiation characteristics.

## 3. Preliminary results

### 3.1 Statistical identification of burst faults

The Fano factor measures the variance of event counts relative to their mean.

| Fault model | Measured Fano factor |
|---|---:|
| Independent faults | 1.0049 |
| Bursty faults, mean cluster 1.5 | 1.9595 |
| Independent faults with 10% charge jitter | 1.1877 |
| Charge-normalised independent faults with jitter | 0.9983 |

The independent model is close to the expected Fano factor of 1. The bursty model is close to the expected value of 2.

Charge normalisation also brings the independent model with charge jitter back close to 1. This suggests that charge variation can influence the raw measurement and should be accounted for during analysis.

### 3.2 Spatial clustering

The spatial analysis produced the following values:

| Measurement | Result |
|---|---:|
| Injected mean cluster size | 1.5034 |
| Recovered mean cluster size | 1.2805 |
| Shuffled mean cluster size | 1.0000 |
| Injected multi-cell fraction | 0.3371 |
| Recovered multi-cell fraction | 0.2004 |
| Observed adjacent pairs | 23,560 |
| Expected adjacent pairs under independence | 2.61 |

The recovered cluster size is lower than the injected cluster size. This indicates that the current recovery method does not identify every injected cluster perfectly.

The large difference between observed and independently expected adjacent pairs is evidence of strong spatial structure in this simulated dataset. The reported numerical p-value of zero should be understood as an extremely small value or numerical underflow, not a literal probability of zero.

### 3.3 Error correction and interleaving

For a mean cluster size of approximately 1.5, the simulation recorded:

| Arrangement | Contiguous failures |
|---|---:|
| Contiguous | 20,285 |
| Interleaved | 23 |
| Shuffled | 19 |

The difference suggests that distributing neighbouring memory locations across different codewords can reduce the concentration of burst errors within individual codewords.

This is a promising result, but a more extensive study should test multiple interleaving patterns, fault rates and cluster sizes.

### 3.4 Adaptive scrubbing

For the independent fault model at a scrubbing interval of 150 pulses:

| Strategy | Residual errors |
|---|---:|
| Fixed scrubbing | 33,582 |
| Adaptive scrubbing | 20,701 |

For the bursty model at the same interval:

| Strategy | Residual errors |
|---|---:|
| Fixed scrubbing | 33,506 |
| Adaptive scrubbing | 20,854 |

Adaptive scrubbing produced fewer residual errors in these comparisons. Both approaches used the same number of scrubs in the reported cases.

This suggests that the timing or placement of scrubbing may matter, not only the total number of scrubs. The result should be validated across additional random seeds and fault conditions.

## 4. Statistical power: Preliminary status

The power analysis explores detection of small increases in the Fano factor, using a significance threshold of 0.001 and a target power of 0.95.

However, the current Fano power curves contain values in increments of 0.2, indicating only five repetitions per setting.

The reported false-positive rates are also based on a preliminary, limited run.

Therefore, the current power curves and estimates of the number of flips required for detection are exploratory. They must not be treated as final statistical conclusions.

A final analysis should use the intended larger repetition counts, report uncertainty intervals, and verify the false-positive rate under independent faults.

## 5. Limitations

The current study has several limitations:

1. The results are generated by a simulation and are not beam-test measurements.
2. Burst sizes and spatial relationships are illustrative model assumptions.
3. The spatial recovery method underestimates the injected mean cluster size.
4. The power analysis has too few repetitions for reliable final estimates.
5. Results should be checked across multiple random seeds.
6. The model should eventually be compared with relevant radiation-effect literature and experimental data.

## 6. Suggested Future work

The next stages of the project should include:

- Re-running the power analysis with the intended repetition counts.
- Adding progress reporting and intermediate checkpoints to long simulations.
- Testing additional burst-size distributions and spatial patterns.
- Improving the recovery of injected spatial clusters.
- Comparing multiple interleaving strategies.
- Testing adaptive scrubbing over a wider range of fault rates.
- Comparing simulation assumptions with published radiation-effect measurements.
- If available, validating the model using beam-test or detector data.

## 7. Conclusion

The preliminary simulations indicate that burst faults can produce substantially different statistical and spatial signatures from independent faults.

The results also suggest that interleaving and adaptive scrubbing can reduce the impact of burst faults under the assumptions of this model.

The project establishes a computational framework for investigating correlated faults in memory systems relevant to radiation environments. Further statistical validation and experimental comparison are necessary before drawing conclusions about real detector or electronics performance.

Research integrity statement: All numerical results in this preliminary report originate from the supplied simulation output. They are not presented as measured beam data or as experimentally validated performance claims.
