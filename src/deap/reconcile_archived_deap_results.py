"""Reconcile the archived DEAP screening run into publication-safe artifacts.

The archived run used five of the 40 available trials per subject for ICA, but
its aggregate metadata reported all 40 as processed. It also named ICLabel
argmax predictions as confirmed artifacts/removals. This script preserves the
observed predictions while correcting those reporting problems.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FINAL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = FINAL_ROOT / "results" / "deap_screening"

CLASS_COLUMNS = [
    "Brain Predictions",
    "Muscle Predictions",
    "Eye Blink Predictions",
    "Heart Beat Predictions",
    "Line Noise Predictions",
    "Channel Noise Predictions",
    "Other Predictions",
]

LEGACY_TO_CORRECTED = {
    "brain_components": "Brain Predictions",
    "muscle_components": "Muscle Predictions",
    "eye_components": "Eye Blink Predictions",
    "heart_components": "Heart Beat Predictions",
    "line_noise_components": "Line Noise Predictions",
    "channel_noise_components": "Channel Noise Predictions",
    "other_components": "Other Predictions",
}

ARTIFACT_POLICY_COLUMNS = [
    "Muscle Predictions",
    "Eye Blink Predictions",
    "Heart Beat Predictions",
    "Line Noise Predictions",
    "Channel Noise Predictions",
]

COLORS = {
    "Brain Predictions": "#27ae60",
    "Muscle Predictions": "#8e44ad",
    "Eye Blink Predictions": "#e74c3c",
    "Heart Beat Predictions": "#2980b9",
    "Line Noise Predictions": "#e67e22",
    "Channel Noise Predictions": "#7f8c8d",
    "Other Predictions": "#95a5a6",
}


def round_half_up(value: float, digits: int) -> float:
    """Round decimal ties conventionally so published tables stay consistent."""
    quantum = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-summary", type=Path, required=True)
    parser.add_argument("--heart-probe", type=Path)
    parser.add_argument("--trials-used", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def reconcile_summary(legacy: pd.DataFrame, trials_used: int) -> pd.DataFrame:
    required = {
        "subject_id",
        "status",
        "total_trials",
        "ica_components",
        "excluded_components",
        "excluded_percentage",
        "processing_time_sec",
        *LEGACY_TO_CORRECTED.keys(),
    }
    missing = sorted(required.difference(legacy.columns))
    if missing:
        raise ValueError(f"Legacy summary is missing columns: {missing}")
    if trials_used < 1:
        raise ValueError("trials_used must be positive")

    corrected = pd.DataFrame(
        {
            "Subject": legacy["subject_id"].astype(str),
            "Status": legacy["status"].astype(str),
            "Trials Available": legacy["total_trials"].astype(int),
            "Trials Used for ICA": int(trials_used),
            "ICA Components": legacy["ica_components"].astype(int),
            "Artifact-Policy Predictions": legacy["excluded_components"].astype(int),
            "Artifact-Policy Percentage": legacy["excluded_percentage"].astype(float),
            "Runtime (s)": legacy["processing_time_sec"].astype(float),
        }
    )
    for legacy_name, corrected_name in LEGACY_TO_CORRECTED.items():
        corrected[corrected_name] = legacy[legacy_name].astype(int)

    predicted_totals = corrected[CLASS_COLUMNS].sum(axis=1)
    if not predicted_totals.equals(corrected["ICA Components"]):
        raise ValueError("Seven-class predictions do not reconcile to ICA totals")
    policy_totals = corrected[ARTIFACT_POLICY_COLUMNS].sum(axis=1)
    if not policy_totals.equals(corrected["Artifact-Policy Predictions"]):
        raise ValueError("Artifact-policy predictions do not reconcile")
    if (corrected["Trials Used for ICA"] > corrected["Trials Available"]).any():
        raise ValueError("Trials used cannot exceed trials available")
    return corrected


def normalize_heart_probe(path: Path | None, output_dir: Path) -> dict[str, object]:
    if path is None:
        return {
            "total_heart_beat_predictions": None,
            "mean_argmax_probability": None,
            "predictions_below_0.5": None,
            "predictions_at_or_above_0.8": None,
        }

    probe = pd.read_csv(path)
    required = {"subject_id", "component_index", "probability"}
    missing = sorted(required.difference(probe.columns))
    if missing:
        raise ValueError(f"Heart probe is missing columns: {missing}")
    normalized = probe.rename(
        columns={
            "subject_id": "Subject",
            "component_index": "Component Index (within subject ICA only)",
            "probability": "ICLabel Argmax Probability",
        }
    )
    normalized.to_csv(output_dir / "heart_beat_prediction_probabilities.csv", index=False)
    probabilities = normalized["ICLabel Argmax Probability"].astype(float)
    return {
        "total_heart_beat_predictions": int(len(probabilities)),
        "mean_argmax_probability": round(float(probabilities.mean()), 4),
        "predictions_below_0.5": int((probabilities < 0.5).sum()),
        "predictions_at_or_above_0.8": int((probabilities >= 0.8).sum()),
    }


def plot_summary(summary: pd.DataFrame, output_path: Path) -> None:
    subjects = summary["Subject"].str.upper()
    total_components = summary["ICA Components"].to_numpy(dtype=float)
    heart_percent = (
        summary["Heart Beat Predictions"].to_numpy(dtype=float) / total_components * 100.0
    )

    aggregate_counts = summary[CLASS_COLUMNS].sum()
    aggregate_percent = aggregate_counts / aggregate_counts.sum() * 100.0

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=200)

    axes[0].bar(np.arange(len(subjects)), heart_percent, color="#2980b9")
    axes[0].set_xticks(np.arange(len(subjects)), subjects, rotation=90, fontsize=7)
    axes[0].set_ylim(0, 100)
    axes[0].set_xlabel("Subject")
    axes[0].set_ylabel("Heart Beat predictions (% of ICA components)")
    axes[0].set_title("Per-subject ICLabel Heart Beat predictions")
    axes[0].grid(axis="y", linestyle="--", alpha=0.35)

    short_labels = [column.replace(" Predictions", "") for column in CLASS_COLUMNS]
    axes[1].bar(
        np.arange(len(CLASS_COLUMNS)),
        aggregate_percent.to_numpy(dtype=float),
        color=[COLORS[column] for column in CLASS_COLUMNS],
    )
    axes[1].set_xticks(
        np.arange(len(CLASS_COLUMNS)), short_labels, rotation=35, ha="right", fontsize=8
    )
    axes[1].set_ylim(0, 100)
    axes[1].set_ylabel("Aggregate predicted-class proportion (%)")
    axes[1].set_title("All seven ICLabel predicted classes")
    axes[1].grid(axis="y", linestyle="--", alpha=0.35)
    for index, value in enumerate(aggregate_percent.to_numpy(dtype=float)):
        axes[1].text(index, value + 1.2, f"{value:.1f}%", ha="center", fontsize=8)

    fig.suptitle(
        "Archived DEAP screening run — model predictions, not component ground truth",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.01,
        "Five of 40 available trials per subject were used for ICA; no cardiac reference was supplied to ICLabel.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.94])
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    legacy = pd.read_csv(args.legacy_summary)
    corrected = reconcile_summary(legacy, args.trials_used)
    corrected_path = args.output_dir / "deap_subject_screening_summary.csv"
    corrected.to_csv(corrected_path, index=False)

    heart_probe = normalize_heart_probe(args.heart_probe, args.output_dir)
    aggregate_counts = corrected[CLASS_COLUMNS].sum().astype(int)
    total_components = int(corrected["ICA Components"].sum())
    class_distribution = {
        column.replace(" Predictions", "").lower().replace(" ", "_"): {
            "count": int(aggregate_counts[column]),
            "percentage": round_half_up(
                float(aggregate_counts[column]) / total_components * 100.0, 2
            ),
        }
        for column in CLASS_COLUMNS
    }

    metadata = {
        "dataset": "DEAP preprocessed Python package",
        "run_type": "archived screening run; reconciled reporting",
        "subjects_evaluated": int(len(corrected)),
        "successful_subjects": int((corrected["Status"] == "Success").sum()),
        "available_trials_per_subject": sorted(
            corrected["Trials Available"].astype(int).unique().tolist()
        ),
        "trials_used_for_ica_per_subject": int(args.trials_used),
        "total_trials_available": int(corrected["Trials Available"].sum()),
        "total_trials_used_for_ica": int(corrected["Trials Used for ICA"].sum()),
        "eeg_channels_supplied_to_iclabel": 32,
        "peripheral_channels_supplied_to_iclabel": 0,
        "sampling_rate_hz": 128.0,
        "passband_hz": [1.0, 55.0],
        "ica_method": "Extended Infomax",
        "total_ica_components": total_components,
        "artifact_policy": {
            "definition": "argmax prediction in Muscle, Eye Blink, Heart Beat, Line Noise, or Channel Noise",
            "prediction_count": int(corrected["Artifact-Policy Predictions"].sum()),
            "prediction_percentage": round(
                float(corrected["Artifact-Policy Predictions"].sum())
                / total_components
                * 100.0,
                2,
            ),
            "note": "Policy calls are not confirmed artifacts and do not validate automatic removal.",
        },
        "class_distribution": class_distribution,
        "heart_beat_probability_probe": heart_probe,
        "runtime": {
            "execution_device_reported": "CPU",
            "total_subject_runtime_seconds": round(float(corrected["Runtime (s)"].sum()), 4),
            "mean_subject_runtime_seconds": round(float(corrected["Runtime (s)"].mean()), 4),
        },
        "limitations": [
            "ICLabel outputs are model predictions, not component ground truth.",
            "Only five of 40 available trials per subject were used for ICA in this archived run.",
            "The 32 EEG channels were supplied to ICLabel; no ECG or plethysmography reference was supplied.",
            "The source package was already preprocessed before this project received it.",
            "The high Heart Beat prediction proportion is an anomaly requiring validation, not proof of cardiac contamination.",
            "No cleaned EEG files or individual signal traces are redistributed with these aggregate artifacts.",
        ],
    }
    (args.output_dir / "experiment_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    plot_summary(corrected, args.output_dir / "deap_screening_distribution.png")

    print(f"Corrected summary: {corrected_path.resolve()}")
    print(f"Metadata:          {(args.output_dir / 'experiment_metadata.json').resolve()}")


if __name__ == "__main__":
    main()
