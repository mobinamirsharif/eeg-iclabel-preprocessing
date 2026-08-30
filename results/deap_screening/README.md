# Reconciled DEAP screening artifacts

These files preserve the aggregate outputs of the archived `ICLabel_DEAP_final.py` screening run while correcting its reporting terminology and trial accounting.

- `deap_subject_screening_summary.csv`: subject-level counts for all seven ICLabel predicted classes.
- `heart_beat_prediction_probabilities.csv`: argmax probabilities for components predicted as Heart Beat.
- `experiment_metadata.json`: corrected design, aggregate counts, and limitations.
- `deap_screening_distribution.png`: cohort-level visualization labeled as model predictions rather than confirmed artifacts.

The archived run had 40 trials available per subject but used five trials per subject for ICA. It supplied only the first 32 EEG channels to ICLabel and did not supply ECG or plethysmography. The files in this directory therefore do not establish cardiac ground truth or validate automatic component removal.

Raw DEAP files, reconstructed FIF files, individual signal traces, and participant topographies are intentionally excluded from this repository.
