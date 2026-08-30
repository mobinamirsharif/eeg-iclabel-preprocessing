# Methodology

## Study objective

This project evaluates the robustness of ICLabel predictions under different EEG preprocessing conditions. It is not a new ICLabel model, a clinical validation, or a diagnostic system.

## ICLabel-compatible baseline

The BCI pipeline uses:

- EEG channels only;
- strict standard 10–20 montage matching;
- 1–100 Hz filtering for the 250 Hz baseline;
- common-average reference;
- extended Infomax ICA;
- a fixed random seed;
- 15 requested ICA components; and
- all seven ICLabel output classes.

MNE-ICALabel documents these preprocessing choices as the design context for ICLabel. It also cautions that the model can be run outside those specifications and that the effects of those deviations were not established by the original ICLabel study. Therefore this project treats preprocessing mismatch as a hypothesis to test, not a universal failure rule.

## Existing BCI run

Dataset 2a provides two sessions with six runs per session for each subject. The archived BCI code selected one run per subject by taking the first session and first run returned by MOABB. Nine subjects and 15 components per selected run yield 135 ICs. The corrected reconciliation is derived from the nine existing per-subject JSON reports; it does not rerun or relabel components.

The corrected table enforces two invariants per row:

1. the seven class counts sum to `Total ICs`; and
2. Muscle + Eye Blink + Heart Beat + Line Noise + Channel Noise equals `Artifacts Removed` under the archived argmax exclusion policy.

## Artifact-removal terminology

The pipeline’s default behavior reproduces the archived policy: any IC whose top predicted class is one of the five artifact classes is excluded. This is described as an “artifact-policy exclusion,” not a confirmed artifact. The corrected pipeline also exposes `--artifact-threshold` so a future run can require a minimum predicted-class probability.

`Other` is retained. It is a catch-all class and is not automatically treated as Brain or artifact.

## Four-condition comparison

For each subject, one explicitly recorded session/run is loaded once and reused as the source for all conditions:

- A: 250 Hz, 1–100 Hz;
- B: 250 Hz, 4–45 Hz;
- C: 128 Hz, 1–63 Hz; and
- D: 128 Hz, 4–45 Hz.

Every condition uses the same channel handling, common-average reference, extended Infomax ICA, random seed, and requested component count. ICA is refit in every condition because filtering and resampling change the data matrix.

### Permitted comparisons

- A vs B estimates the observed effect of the passband/preprocessing change at 250 Hz.
- B vs D estimates the observed sampling-rate effect with a shared 4–45 Hz passband.
- C vs D estimates the observed passband change at 128 Hz.
- A vs C is descriptive only, because the feasible upper bandwidth changes along with sampling rate.

These comparisons do not establish a universal causal requirement for ICLabel.

## Why component indices are not paired

ICA decomposition is refit for each condition. Component order, sign, and content can change between fits. The analysis therefore does not zip or directly compare identically numbered components across conditions. It reports class counts, class proportions, mean/median predicted-class probability, EEG rank, and runtime at subject/condition level.

## Dataset terminology

BCI Competition IV Dataset 2a contains nine subjects, 22 EEG channels, three EOG channels, and a sampling rate of 250 Hz. The project uses “subject,” “participant,” or “آزمودنی,” not “patient.” BNCI2014_001 is MOABB’s dataset identifier; the original competition was BCI Competition IV (2008).

## DEAP constraints

The existing DEAP scripts operate on a preprocessed package at 128 Hz. In the archived initial batch script, only five of the 40 available trials per subject were concatenated for ICA fitting, and the actual ICA call used 10 components despite a separate `N_COMPONENTS = 15` constant. These are reporting and implementation inconsistencies, not new biological findings.

Increasing a downstream filter cutoff from 45 to 55 Hz cannot restore spectral content removed by upstream preprocessing. V2 is therefore treated as a software-cutoff/confidence probe, not restoration of a 45–55 Hz band.

The later archived `ICLabel_DEAP_final.py` run used a corrected 32-channel order and 30 ICA components per subject, but still used five trials per subject for ICA. Its old aggregate metadata summed the 40 available trials per subject and called 1,280 trials “processed.” The reconciled metadata separates 1,280 available trials from 160 trials actually supplied to ICA.

Across 960 ICA components, that screening run produced 775 Heart Beat predictions (80.73%). This is reported as an anomalous model-output distribution. The pipeline supplied only 32 EEG channels to ICLabel and did not supply ECG or plethysmography, so these calls cannot be verified as cardiac artifacts from the available ICLabel output alone.

`src/deap/run_deap_screening_pipeline.py` preserves the explicit five-trial screening configuration by default, records available and used trials separately, reports all seven classes, and performs no automatic component removal. The reconciled aggregate artifacts exclude FIF files, raw/cleaned signal traces, and individual participant topographies.

## Data and reproducibility policy

Raw/licensed EEG data are not distributed in this repository. Scripts obtain BNCI2014_001 through MOABB and users must obtain DEAP under the official EULA. Only aggregate DEAP prediction tables, probabilities, metadata, and a cohort figure are versioned; reconstructed FIF files and individual signal traces are excluded.
