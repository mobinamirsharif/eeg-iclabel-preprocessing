# Reconciled DEAP version history

`version_comparison.csv` and `version_comparison.png` summarize the five archived development stages from all seven ICLabel classes. `version_history_metadata.json` records configuration, source hashes, and interpretation limits.

Reproduce these files from the archived aggregate outputs:

```powershell
& $python .\src\deap\build_version_history.py
```

The series is descriptive rather than causal. Each stage refitted ICA, and several settings changed across stages. The results cannot support direct pairing of component indices or a universal claim about sampling rate, passband, montage, rank, or component count.
