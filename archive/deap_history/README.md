# Historical DEAP development archive

This directory preserves the five DEAP pipeline stages that preceded the corrected, publication-oriented workflow. The scripts are byte-for-byte copies of the original local files. Their aggregate summaries, processing-time tables, and 32 per-subject ICLabel JSON reports are included for auditability.

The archive is evidence of the troubleshooting process, not the recommended analysis entry point. Some original comments and report fields describe ICLabel argmax predictions as confirmed artifacts or removals. Those terms are superseded. Use `src/deap/run_deap_screening_pipeline.py` for the non-destructive current workflow.

| Stage | Archived script | Main change | Heart Beat predictions |
|---|---|---|---:|
| Baseline | `00_baseline/script/run_deap_iclabel_batch.py` | Original channel mapping; actual ICA call used 10 components despite a 15-component constant | 219/320 (68.44%) |
| V1 | `01_channel_order/script/ICLabel_DEAP_corrected.py` | Corrected DEAP/BioSemi channel order | 234/320 (73.13%) |
| V2 | `02_filter_confidence/script/ICLabel_DEAP_corrected_v2.py` | Downstream 1-55 Hz filter request and confidence probe | 233/320 (72.81%) |
| V3 | `03_crossfade_visual/script/ICLabel_DEAP_corrected_v3.py` | 0.5-second crossfade, 15 components, visual-review outputs | 372/480 (77.50%) |
| V4 | `04_rank_aware/script/ICLabel_DEAP_final.py` | Rank-minus-one selection; every report recorded rank 31 and 30 components | 775/960 (80.73%) |

All five stages used five of the 40 available trials per subject for ICA. Their old cohort metadata summed the 40 available trials and sometimes labeled that value as processed. The corrected comparison reports 1,280 trials available and 160 trials used for ICA in each stage.

## Interpretation limits

- ICLabel outputs are model predictions, not component ground truth.
- The sequence is not a controlled one-factor ablation: multiple settings changed between stages, ICA was refitted, and component indices are not paired.
- High argmax probabilities do not by themselves prove that a prediction is correct or incorrect.
- Visual review can support suspected misclassification but does not establish that a component is "100% brain."
- Increasing a downstream cutoff to 55 Hz cannot restore frequencies absent from the preprocessed DEAP package.
- The historical series does not establish sampling rate, passband, montage, trial crossfade, rank, or component count as the sole cause of the unusual distribution.

## Deliberately excluded

Licensed DEAP `.dat`/`.bdf` data, reconstructed `.fif` files, individual raw-versus-reconstructed traces, participant topographies, and compressed result archives are not versioned here. `archive/EXCLUDED_DATA_MANIFEST.csv` fingerprints all 361 omitted historical artifacts, while `archive/SOURCE_MANIFEST.csv` maps the supplied scripts and reports to their repository copies.

Rebuild the excluded-data manifest when the original local folders are available:

```powershell
& $python .\src\deap\build_excluded_data_manifest.py `
  --source-root '<PATH_TO_ORIGINAL_PROJECT_ROOT>'
```
