# Troubleshooting timeline

## 1. Initial DEAP batch evaluation

The first batch evaluation found a high proportion of Heart Beat predictions. An early physiological explanation linked this pattern to emotional video stimuli. That explanation is retained only as a rejected initial hypothesis.

The initial script also contained two concrete implementation/reporting inconsistencies:

- five trials per subject were concatenated for ICA even though 40 trials were available; and
- `N_COMPONENTS = 15` was declared, while the ICA call used `n_components=10`.

## 2. Channel-order correction

A real channel-mapping error was corrected. Because the Heart Beat pattern persisted, channel order was not sufficient to explain the anomaly.

## 3. V2 passband and confidence probe

The downstream high cutoff was raised to 55 Hz and prediction confidence was examined. This was useful as a software-configuration and confidence probe. It did not restore frequencies already absent from the preprocessed DEAP package, so it is not evidence that 45–55 Hz content was added back.

## 4. V3 visual review

PSD and topography review found patterns compatible with possible misclassification for some components. This is supporting visual evidence, not ground-truth proof that every Heart Beat prediction was Brain.

## 5. ICA component-count comparison

The observed Heart Beat proportion changed when the requested number of ICA components changed. Each setting creates a different decomposition, so the trend is descriptive and not a direct causal relationship between component count and error.

## 6. Independent 250 Hz BCI comparison

The unusual DEAP Heart Beat pattern was absent in the nine selected BCI recordings. This strengthens the case that the DEAP result is data/preprocessing dependent, but it does not isolate sampling rate from bandwidth, task, acquisition, upstream artifact processing, or other dataset differences.

## 7. Class-accounting correction

The BCI subject reports contained all seven ICLabel classes, but the cohort CSV and donut chart omitted Channel Noise and Other. Thirteen Other components disappeared from the chart denominator. Reconciliation restored the full total of 135 ICs and changed the Brain percentage from 72.1% to 65.2%.

## 8. Controlled comparison prepared

The final script defines four conditions and compares distributions at subject/condition level. It explicitly avoids direct pairing of component indices across separate ICA fits and records failures rather than silently dropping them.
