"""Build a reconciled comparison of the five archived DEAP development runs.

The archived scripts are preserved as historical evidence. They are not the
recommended entry point and some of their comments and report terminology were
superseded by the corrected methodology. This script reads only their aggregate
CSV outputs and reports ICLabel argmax predictions without treating them as
component ground truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = PROJECT_ROOT / "archive" / "deap_history"
OUTPUT_DIR = PROJECT_ROOT / "results" / "deap_version_history"


@dataclass(frozen=True)
class Version:
    stage: str
    archive_directory: str
    script_name: str
    intervention: str
    low_hz: float
    high_hz: float
    components_per_subject: int
    crossfade_seconds: float
    rank_aware: bool


VERSIONS = [
    Version(
        "Baseline",
        "00_baseline",
        "run_deap_iclabel_batch.py",
        "Original channel order; actual ICA call used 10 components despite a 15-component constant",
        1.0,
        45.0,
        10,
        0.0,
        False,
    ),
    Version(
        "V1",
        "01_channel_order",
        "ICLabel_DEAP_corrected.py",
        "Corrected DEAP/BioSemi channel order and strict montage validation",
        1.0,
        45.0,
        10,
        0.0,
        False,
    ),
    Version(
        "V2",
        "02_filter_confidence",
        "ICLabel_DEAP_corrected_v2.py",
        "Raised downstream high cutoff and added a confidence probe",
        1.0,
        55.0,
        10,
        0.0,
        False,
    ),
    Version(
        "V3",
        "03_crossfade_visual",
        "ICLabel_DEAP_corrected_v3.py",
        "Added a 0.5-second trial crossfade, 15 components, and visual review outputs",
        1.0,
        55.0,
        15,
        0.5,
        False,
    ),
    Version(
        "V4",
        "04_rank_aware",
        "ICLabel_DEAP_final.py",
        "Selected rank minus one components; all archived reports recorded rank 31 and 30 components",
        1.0,
        55.0,
        30,
        0.5,
        True,
    ),
]


CLASS_COLUMNS = {
    "Brain Predictions": "brain_components",
    "Muscle Predictions": "muscle_components",
    "Eye Blink Predictions": "eye_components",
    "Heart Beat Predictions": "heart_components",
    "Line Noise Predictions": "line_noise_components",
    "Channel Noise Predictions": "channel_noise_components",
    "Other Predictions": "other_components",
}

COLORS = ["#27ae60", "#8e44ad", "#e74c3c", "#2980b9", "#e67e22", "#7f8c8d", "#95a5a6"]


def round_half_up(value: float, digits: int = 2) -> float:
    quantum = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_version(version: Version) -> tuple[dict[str, object], dict[str, object]]:
    version_root = ARCHIVE_ROOT / version.archive_directory
    summary_path = version_root / "results" / "summary" / "deap_32_subjects_summary.csv"
    script_path = version_root / "script" / version.script_name
    summary = pd.read_csv(summary_path)

    required = {
        "status",
        "total_trials",
        "ica_components",
        "excluded_components",
        *CLASS_COLUMNS.values(),
    }
    missing = sorted(required.difference(summary.columns))
    if missing:
        raise ValueError(f"{version.stage} summary is missing columns: {missing}")
    if len(summary) != 32 or not (summary["status"] == "Success").all():
        raise ValueError(f"{version.stage} does not contain 32 successful subject rows")

    total_components = int(summary["ica_components"].sum())
    class_counts = {
        output_name: int(summary[source_name].sum())
        for output_name, source_name in CLASS_COLUMNS.items()
    }
    if sum(class_counts.values()) != total_components:
        raise ValueError(f"{version.stage} seven-class counts do not reconcile")
    if total_components != len(summary) * version.components_per_subject:
        raise ValueError(f"{version.stage} component total does not match its archived configuration")

    artifact_policy = int(summary["excluded_components"].sum())
    heart_count = class_counts["Heart Beat Predictions"]
    brain_count = class_counts["Brain Predictions"]
    row: dict[str, object] = {
        "Stage": version.stage,
        "Intervention": version.intervention,
        "Sampling Rate (Hz)": 128.0,
        "Filter Low (Hz)": version.low_hz,
        "Filter High (Hz)": version.high_hz,
        "Subjects": int(len(summary)),
        "Trials Available": int(summary["total_trials"].sum()),
        "Trials Used for ICA": int(len(summary) * 5),
        "ICA Components per Subject": version.components_per_subject,
        "ICA Components Total": total_components,
        "Crossfade (s)": version.crossfade_seconds,
        "Rank-Aware": version.rank_aware,
        **class_counts,
        "Artifact-Policy Predictions": artifact_policy,
        "Brain Percentage": round_half_up(brain_count / total_components * 100.0),
        "Heart Beat Percentage": round_half_up(heart_count / total_components * 100.0),
        "Artifact-Policy Percentage": round_half_up(artifact_policy / total_components * 100.0),
    }
    provenance = {
        "stage": version.stage,
        "archive_directory": version.archive_directory,
        "script": version.script_name,
        "script_sha256": sha256(script_path),
        "summary_csv_sha256": sha256(summary_path),
    }
    return row, provenance


def plot_history(frame: pd.DataFrame, output_path: Path) -> None:
    stages = frame["Stage"].tolist()
    class_names = list(CLASS_COLUMNS)
    totals = frame["ICA Components Total"].to_numpy(dtype=float)
    percentages = np.column_stack(
        [frame[class_name].to_numpy(dtype=float) / totals * 100.0 for class_name in class_names]
    )

    fig, axes = plt.subplots(1, 2, figsize=(15, 6), dpi=200)
    bottom = np.zeros(len(frame), dtype=float)
    for index, (class_name, color) in enumerate(zip(class_names, COLORS)):
        values = percentages[:, index]
        axes[0].bar(stages, values, bottom=bottom, label=class_name.replace(" Predictions", ""), color=color)
        bottom += values
    axes[0].set_ylim(0, 100)
    axes[0].set_ylabel("Predicted-class proportion (%)")
    axes[0].set_title("All seven ICLabel predicted classes")
    axes[0].legend(fontsize=7, ncol=2, loc="upper left")
    axes[0].grid(axis="y", linestyle="--", alpha=0.3)

    heart = frame["Heart Beat Percentage"].to_numpy(dtype=float)
    components = frame["ICA Components per Subject"].to_numpy(dtype=int)
    axes[1].plot(stages, heart, marker="o", linewidth=2.5, color="#2980b9")
    axes[1].set_ylim(0, 100)
    axes[1].set_ylabel("Heart Beat predictions (% of all ICs)")
    axes[1].set_title("Observed historical output; not a causal component-count test")
    axes[1].grid(linestyle="--", alpha=0.3)
    for index, (value, count) in enumerate(zip(heart, components)):
        axes[1].annotate(
            f"{value:.2f}%\n{count} ICs/subject",
            (index, value),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=8,
        )

    fig.suptitle(
        "Historical DEAP development runs — ICLabel predictions, not component ground truth",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.01,
        "Each run used five of 40 available trials per subject. Multiple settings changed across stages, so the series is descriptive.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    provenance: list[dict[str, object]] = []
    for version in VERSIONS:
        row, source = summarize_version(version)
        rows.append(row)
        provenance.append(source)

    frame = pd.DataFrame(rows)
    frame.to_csv(OUTPUT_DIR / "version_comparison.csv", index=False)
    plot_history(frame, OUTPUT_DIR / "version_comparison.png")

    metadata = {
        "scope": "historical DEAP development runs",
        "source_type": "archived aggregate outputs",
        "versions": [asdict(version) for version in VERSIONS],
        "provenance": provenance,
        "interpretation_limits": [
            "ICLabel outputs are model predictions, not component ground truth.",
            "The five stages are not a one-factor ablation study because multiple settings changed.",
            "ICA was independently refitted in every run, so component indices are not paired across stages.",
            "All stages used five of 40 available trials per subject for ICA.",
            "The archived downstream 55 Hz cutoff cannot restore frequencies absent from the preprocessed DEAP package.",
            "The series does not establish sampling rate, passband, channel order, crossfade, rank, or component count as a sole cause.",
        ],
    }
    (OUTPUT_DIR / "version_history_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"Comparison: {(OUTPUT_DIR / 'version_comparison.csv').resolve()}")
    print(f"Figure:     {(OUTPUT_DIR / 'version_comparison.png').resolve()}")


if __name__ == "__main__":
    main()
