# Final findings

## What is directly observed

1. The archived DEAP evaluations produced an unusually high proportion of Heart Beat predictions.
2. Correcting the DEAP channel order did not remove that pattern.
3. The archived BCI Competition IV Dataset 2a run did not reproduce the Heart Beat pattern in the nine selected recordings.
4. The BCI subject JSON reports contain 135 predicted IC labels in total: 88 Brain, 34 in the pipeline’s five artifact classes, and 13 Other.
5. The archived dashboard omitted Other and Channel Noise, producing a displayed total of 122 and the incorrect Brain percentage 72.1%.
6. The controlled comparison completed all 36 subject/condition fits and produced 540 ICLabel predictions with no failed conditions.
7. With a shared 4–45 Hz passband, the aggregate distributions at 250 Hz and 128 Hz were similar: Brain was 76.30% and 75.56%, respectively.
8. Changing the passband produced larger aggregate shifts than changing sampling rate in the clean B-vs-D contrast. In particular, Line Noise predictions fell from 17.04% to 2.96% at 250 Hz and from 17.04% to 3.70% at 128 Hz when moving to 4–45 Hz.

## Corrected BCI statement

> Across one selected recording for each of nine BCI Competition IV Dataset 2a subjects, ICLabel classified 88 of 135 independent components as Brain (65.2%). The pipeline’s argmax-based exclusion policy marked 34 components (25.2%) in five artifact classes, while 13 components (9.6%) were classified as Other and retained.

This statement reports model outputs. It is not a ground-truth estimate of the percentage of pure brain signal or confirmed artifacts.

## Corrected DEAP statement

> ICLabel showed an unusual Heart Beat prediction pattern on the preprocessed DEAP package used in this project. The package’s sampling rate and bandwidth differ from ICLabel’s documented design context, and the pattern was absent from the selected 250 Hz BCI recordings. The evidence is consistent with a preprocessing/data mismatch, but it does not isolate sampling rate as the sole cause.

## Controlled-comparison statement

> Across nine consistently selected BCI recordings, changing sampling rate from 250 Hz to 128 Hz while holding the passband at 4–45 Hz produced very similar aggregate ICLabel class distributions (76.30% vs 75.56% Brain). The larger observed changes followed passband changes, not the clean sampling-rate contrast. This experiment therefore does not support the earlier claim of a general ICLabel “collapse” at 128 Hz.

The result is specific to these recordings and this pipeline. ICA was refitted under every condition, component indices are not paired across fits, and ICLabel predictions are not ground-truth labels.

## Claims removed or downgraded

- “Nyquist collapse was successfully fixed” — not established.
- “The model’s 1–100 Hz range was 100% filled with real signal” — not an appropriate inference from sampling rate alone.
- “ICLabel is invalid below 200 Hz” — not stated by MNE-ICALabel documentation.
- “All 40 DEAP trials per subject were used for ICA” — the initial code used five.
- “All recordings for all nine BCI subjects were processed” — the archived code selected the first session/run only.
- “GPU benchmark” for the BCI pipeline — no GPU was explicitly selected or measured there.
- “Pure brain signal” and “confirmed noise” — replaced with ICLabel prediction terminology.
- “Clinical validation” and “patients” — the project has neither a patient cohort nor clinical ground truth.

## Completed controlled experiment

The four-condition comparison has now been executed for subjects 1–9 using session index 0 and run index 0. Outputs are stored in `results/controlled_experiment/`: `condition_summary.csv`, `component_predictions.csv`, `experiment_metadata.json`, and `aggregate_condition_distribution.png`. The metadata records the cache, selection rule, random seed, ICA configuration, condition definitions, limitations, and zero failures.

## Publication framing

Recommended title:

> ICLabel EEG Preprocessing Robustness & Troubleshooting Case Study

The strongest contribution is the documented debugging process, class-accounting correction, explicit limitations, and controlled-test design—not a claim of a new ICLabel model or a definitive biological discovery.
