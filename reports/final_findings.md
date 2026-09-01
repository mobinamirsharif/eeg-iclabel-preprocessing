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
9. The archived final DEAP screening run used five of 40 available trials per subject, 32 subjects, and 30 ICA components per subject, yielding 960 predictions in total.
10. That DEAP screening run produced 775 Heart Beat predictions (80.73%), 29 Brain predictions (3.02%), and 156 predictions across the remaining five classes.
11. The standard 40-channel preprocessed package has no dedicated ECG channel but does include a peripheral Plethysmograph/BVP channel. The pipeline supplied only the first 32 EEG channels to ICA and ICLabel, so BVP was not an input and no cardiac reference was used to directly validate the Heart Beat assignments.
12. A retrospective `s01` diagnostic using the V3 settings estimated EEG rank 31 before and after common-average reference. The requested 15 ICA components did not exceed that estimate, so this test does not support ICA-rank overflow as the cause of the V3 Heart Beat-dominant output.
13. The reconciled historical sequence produced 219/320 (68.44%) Baseline, 234/320 (73.13%) V1, 233/320 (72.81%) V2, 372/480 (77.50%) V3, and 775/960 (80.73%) V4 Heart Beat predictions.
14. The historical scripts show that all five stages used five of 40 trials per subject. Their cohort metadata recorded 1,280 available trials, while only 160 trials entered ICA in each stage.

## Corrected BCI statement

> Across one selected recording for each of nine BCI Competition IV Dataset 2a subjects, ICLabel classified 88 of 135 independent components as Brain (65.2%). The pipeline’s argmax-based exclusion policy marked 34 components (25.2%) in five artifact classes, while 13 components (9.6%) were classified as Other and retained.

This statement reports model outputs. It is not a ground-truth estimate of the percentage of pure brain signal or confirmed artifacts.

## Corrected DEAP statement

> In an archived screening run using five of 40 available trials for each of 32 DEAP subjects, ICLabel assigned 775 of 960 ICA components (80.73%) to Heart Beat. Only the first 32 EEG channels were supplied to ICLabel; the package's peripheral BVP channel was excluded, and the package has no dedicated ECG channel. No cardiac reference was therefore used to directly validate the assignments. This does not prove that the predictions were wrong, because cardiac activity can propagate into scalp EEG. The distribution requires validation and is not evidence that 775 components were confirmed cardiac artifacts. The completed controlled BCI comparison does not support sampling rate alone as the explanation.

## Controlled-comparison statement

> Across nine consistently selected BCI recordings, changing sampling rate from 250 Hz to 128 Hz while holding the passband at 4–45 Hz produced very similar aggregate ICLabel class distributions (76.30% vs 75.56% Brain). The larger observed changes followed passband changes, not the clean sampling-rate contrast. This experiment therefore does not support the earlier claim of a general ICLabel “collapse” at 128 Hz.

The result is specific to these recordings and this pipeline. ICA was refitted under every condition, component indices are not paired across fits, and ICLabel predictions are not ground-truth labels.

## Claims removed or downgraded

- “Nyquist collapse was successfully fixed” — not established.
- “The model’s 1–100 Hz range was 100% filled with real signal” — not an appropriate inference from sampling rate alone.
- “ICLabel is invalid below 200 Hz” — not stated by MNE-ICALabel documentation.
- “All 40 DEAP trials per subject were used for ICA” — the initial code used five.
- “1,280 DEAP trials were processed by ICA” — 1,280 were available, while 160 were used in the archived final screening run.
- “805 DEAP components were confirmed artifacts and removed successfully” — these were argmax policy calls, not ground-truth artifact labels.
- “The V1-V4 sequence proves that increasing component count causes Heart Beat collapse” — multiple settings changed and ICA was refitted independently.
- “The visual review proved that every Heart Beat prediction was 100% Brain” — the selected plots support review but do not provide component ground truth.
- “Rank-aware ICA solved the DEAP anomaly” — the archived V4 output contained the highest observed Heart Beat proportion, 80.73%.
- “V3 requested more ICA components than the estimated EEG rank” — the `s01` V3 diagnostic estimated rank 31 before and after CAR, while V3 requested 15 components.
- “ICLabel requires sampling above 200 Hz” — neither the archived outputs nor the controlled comparison establish that threshold.
- “All recordings for all nine BCI subjects were processed” — the archived code selected the first session/run only.
- “GPU benchmark” for the BCI pipeline — no GPU was explicitly selected or measured there.
- “Pure brain signal” and “confirmed noise” — replaced with ICLabel prediction terminology.
- “Clinical validation” and “patients” — the project has neither a patient cohort nor clinical ground truth.

## Completed controlled experiment

The four-condition comparison has now been executed for subjects 1–9 using session index 0 and run index 0. Outputs are stored in `results/controlled_experiment/`: `condition_summary.csv`, `component_predictions.csv`, `experiment_metadata.json`, and `aggregate_condition_distribution.png`. The metadata records the cache, selection rule, random seed, ICA configuration, condition definitions, limitations, and zero failures.

## Reconciled DEAP screening artifacts

The publication-safe DEAP artifacts are stored in `results/deap_screening/`. They include a corrected subject summary, a Heart Beat probability table, metadata, and a cohort distribution figure. The original `.fif` files, individual raw-versus-reconstructed traces, and subject topographies are intentionally not redistributed.

## Preserved development record

The exact historical scripts and their safe numeric outputs are preserved under `archive/deap_history/`. The reconciled version-history artifacts under `results/deap_version_history/` preserve provenance by reconciling all seven classes across Baseline through V4 and recording source hashes. Superseded standalone PDF and HTML reports are excluded from the public repository.

## Publication framing

Recommended title:

> ICLabel EEG Preprocessing Robustness & Troubleshooting Case Study

The strongest contribution is the documented debugging process, class-accounting correction, explicit limitations, and controlled-test design—not a claim of a new ICLabel model or a definitive biological discovery.
