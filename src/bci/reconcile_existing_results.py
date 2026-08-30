"""Rebuild the corrected BCI cohort CSV from the existing JSON reports.

This utility provides an auditable bridge from the original result package to
the corrected seven-class table. It does not rerun ICA or ICLabel.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


FINAL_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = FINAL_ROOT.parent
DEFAULT_LEGACY_RESULTS = PROJECT_ROOT / "BCI_2a_ICLabel_Cleaned_Results"
DEFAULT_OUTPUT = FINAL_ROOT / "results" / "summary_tables" / "cohort_iclabel_summary.csv"


def reconcile(legacy_results: Path, output_path: Path) -> pd.DataFrame:
    reports_dir = legacy_results / "iclabel_reports"
    legacy_csv = legacy_results / "summary" / "cohort_iclabel_summary.csv"
    if not reports_dir.is_dir():
        raise FileNotFoundError(f"ICLabel report directory not found: {reports_dir}")
    if not legacy_csv.exists():
        raise FileNotFoundError(f"Legacy summary CSV not found: {legacy_csv}")

    legacy = pd.read_csv(legacy_csv).set_index("Subject")
    rows: list[dict[str, object]] = []
    for report_path in sorted(reports_dir.glob("*_report.json")):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        subject = str(report["subject_id"])
        distribution = report["class_distribution"]
        probabilities = np.asarray(
            [component["probability"] for component in report["components"]],
            dtype=float,
        )
        total_components = int(report["total_components"])
        class_total = int(sum(int(value) for value in distribution.values()))
        if class_total != total_components:
            raise ValueError(
                f"Class counts ({class_total}) do not match Total ICs "
                f"({total_components}) for {subject}"
            )

        row = {
            "Subject": subject,
            "Recording": "first available session/run (keys not recorded)",
            "Fs (Hz)": float(report["sampling_rate_hz"]),
            "Nyquist (Hz)": float(report["nyquist_hz"]),
            "Channels": int(report["channels_count"]),
            "Total ICs": total_components,
            "Artifacts Removed": int(report["excluded_artifacts_count"]),
            "Brain": int(distribution["brain"]),
            "Muscle": int(distribution["muscle artifact"]),
            "Eye Blink": int(distribution["eye blink"]),
            "Heart Beat": int(distribution["heart beat"]),
            "Line Noise": int(distribution["line noise"]),
            "Channel Noise": int(distribution["channel noise"]),
            "Other": int(distribution["other"]),
            "Mean Confidence": round(float(np.mean(probabilities)), 4),
            "Median Confidence": round(float(np.median(probabilities)), 4),
            "Runtime (s)": round(float(legacy.loc[subject, "Runtime (s)"]), 2),
            "Processing Device": "System default (no explicit GPU selection)",
        }
        artifact_total = sum(
            row[column]
            for column in [
                "Muscle",
                "Eye Blink",
                "Heart Beat",
                "Line Noise",
                "Channel Noise",
            ]
        )
        if artifact_total != row["Artifacts Removed"]:
            raise ValueError(
                f"Artifact classes ({artifact_total}) do not match the exclusion "
                f"count ({row['Artifacts Removed']}) for {subject}"
            )
        rows.append(row)

    result = pd.DataFrame(rows).sort_values("Subject")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-results", type=Path, default=DEFAULT_LEGACY_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = reconcile(args.legacy_results, args.output)
    print(table.to_string(index=False))
    print(f"Corrected CSV: {args.output.resolve()}")


if __name__ == "__main__":
    main()
