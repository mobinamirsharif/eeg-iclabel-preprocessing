"""Generate a reconciled ICLabel cohort dashboard.

The chart accounts for all seven ICLabel classes. Percentages use the reported
``Total ICs`` column as the denominator and the script refuses to plot rows whose
class counts do not reconcile to that total.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FINAL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = FINAL_ROOT / "results" / "summary_tables" / "cohort_iclabel_summary.csv"
DEFAULT_OUTPUT_DIR = FINAL_ROOT / "figures"

CLASS_COLUMNS = [
    "Brain",
    "Muscle",
    "Eye Blink",
    "Heart Beat",
    "Line Noise",
    "Channel Noise",
    "Other",
]
ARTIFACT_COLUMNS = [
    "Muscle",
    "Eye Blink",
    "Heart Beat",
    "Line Noise",
    "Channel Noise",
]
COLORS = {
    "Brain": "#27ae60",
    "Muscle": "#8e44ad",
    "Eye Blink": "#e74c3c",
    "Heart Beat": "#2980b9",
    "Line Noise": "#e67e22",
    "Channel Noise": "#7f8c8d",
    "Other": "#95a5a6",
}


def load_and_validate(csv_path: Path) -> pd.DataFrame:
    """Load a cohort table and verify that all component counts reconcile."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Summary CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    required = {
        "Subject",
        "Total ICs",
        "Artifacts Removed",
        "Runtime (s)",
        *CLASS_COLUMNS,
    }
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(
            "Summary CSV is missing required columns: " + ", ".join(missing)
        )

    numeric_columns = [
        "Total ICs",
        "Artifacts Removed",
        "Runtime (s)",
        *CLASS_COLUMNS,
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="raise")

    class_totals = df[CLASS_COLUMNS].sum(axis=1)
    bad_class_rows = df.loc[class_totals != df["Total ICs"], "Subject"].tolist()
    if bad_class_rows:
        raise ValueError(
            "Seven-class totals do not match Total ICs for: "
            + ", ".join(map(str, bad_class_rows))
        )

    artifact_totals = df[ARTIFACT_COLUMNS].sum(axis=1)
    bad_artifact_rows = df.loc[
        artifact_totals != df["Artifacts Removed"], "Subject"
    ].tolist()
    if bad_artifact_rows:
        raise ValueError(
            "Artifact-class totals do not match Artifacts Removed for: "
            + ", ".join(map(str, bad_artifact_rows))
        )

    return df


def build_x_labels(df: pd.DataFrame) -> list[str]:
    """Use recording identifiers only when a subject occurs more than once."""
    duplicate_subjects = df["Subject"].duplicated(keep=False)
    if "Recording" not in df.columns or not duplicate_subjects.any():
        return df["Subject"].astype(str).tolist()
    labels: list[str] = []
    for _, row in df.iterrows():
        labels.append(f"{row['Subject']}\n{row['Recording']}")
    return labels


def aggregate_metrics(df: pd.DataFrame) -> dict[str, float | int]:
    total_ics = int(df["Total ICs"].sum())
    total_brain = int(df["Brain"].sum())
    total_artifacts = int(df["Artifacts Removed"].sum())
    total_other = int(df["Other"].sum())
    return {
        "subjects": int(df["Subject"].nunique()),
        "recordings": int(len(df)),
        "total_ics": total_ics,
        "brain": total_brain,
        "brain_percent": round(100.0 * total_brain / total_ics, 2),
        "artifacts": total_artifacts,
        "artifacts_percent": round(100.0 * total_artifacts / total_ics, 2),
        "other": total_other,
        "other_percent": round(100.0 * total_other / total_ics, 2),
        "mean_runtime_seconds": round(float(df["Runtime (s)"].mean()), 3),
    }


def generate_dashboard(csv_path: Path, output_dir: Path) -> tuple[Path, Path]:
    df = load_and_validate(csv_path)
    metrics = aggregate_metrics(df)
    output_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#333333"
    plt.rcParams["axes.linewidth"] = 0.8

    fig, axs = plt.subplots(2, 2, figsize=(15, 10), dpi=300)
    sampling_rates = sorted(
        pd.to_numeric(df.get("Fs (Hz)", pd.Series(dtype=float)), errors="coerce")
        .dropna()
        .unique()
        .tolist()
    )
    sampling_text = ", ".join(f"{rate:g}" for rate in sampling_rates) or "not recorded"
    fig.suptitle(
        "BCI Competition IV 2a - ICLabel Evaluation Dashboard\n"
        f"{metrics['subjects']} subjects, {metrics['recordings']} selected recordings | "
        f"Sampling rate(s): {sampling_text} Hz",
        fontsize=13,
        fontweight="bold",
        y=0.985,
    )

    x_labels = build_x_labels(df)
    x_indices = np.arange(len(df))

    # A. All seven ICLabel classes per recording.
    ax1 = axs[0, 0]
    bottoms = np.zeros(len(df))
    for column in CLASS_COLUMNS:
        values = df[column].to_numpy(dtype=float)
        ax1.bar(
            x_indices,
            values,
            bottom=bottoms,
            label=column,
            color=COLORS[column],
            edgecolor="black",
            linewidth=0.4,
            alpha=0.9,
        )
        bottoms += values
    ax1.set_title("A. Seven-class ICLabel predictions per recording", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Subject / recording")
    ax1.set_ylabel("Independent-component count")
    ax1.set_xticks(x_indices)
    ax1.set_xticklabels(x_labels, fontsize=8)
    ax1.set_ylim(0, max(float(df["Total ICs"].max()) + 2.0, 3.0))
    ax1.legend(loc="upper right", frameon=True, fontsize=7, ncols=2)
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

    # B. Aggregate distribution with the true total as denominator.
    ax2 = axs[0, 1]
    class_counts = {column: int(df[column].sum()) for column in CLASS_COLUMNS}
    nonzero_classes = [column for column in CLASS_COLUMNS if class_counts[column] > 0]
    class_sizes = [class_counts[column] for column in nonzero_classes]
    class_labels = [f"{column} ({class_counts[column]})" for column in nonzero_classes]
    wedges, _, autotexts = ax2.pie(
        class_sizes,
        labels=class_labels,
        colors=[COLORS[column] for column in nonzero_classes],
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.75,
        wedgeprops={"width": 0.45, "edgecolor": "black", "linewidth": 0.8},
        textprops={"fontsize": 8, "fontweight": "bold"},
    )
    del wedges
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(8)
    ax2.set_title(
        f"B. Aggregate model predictions (Total ICs = {metrics['total_ics']})",
        fontsize=11,
        fontweight="bold",
    )

    # C. Keep model predictions distinct from ground truth terminology.
    ax3 = axs[1, 0]
    width = 0.25
    brain = df["Brain"].to_numpy(dtype=float)
    artifacts = df["Artifacts Removed"].to_numpy(dtype=float)
    other = df["Other"].to_numpy(dtype=float)
    ax3.bar(x_indices - width, brain, width=width, label="Brain prediction", color=COLORS["Brain"], edgecolor="black")
    ax3.bar(x_indices, artifacts, width=width, label="Artifact-policy exclusions", color="#c0392b", edgecolor="black")
    ax3.bar(x_indices + width, other, width=width, label="Other (retained)", color=COLORS["Other"], edgecolor="black")
    ax3.set_title("C. Brain, excluded-artifact, and Other counts", fontsize=11, fontweight="bold")
    ax3.set_xlabel("Subject / recording")
    ax3.set_ylabel("Independent-component count")
    ax3.set_xticks(x_indices)
    ax3.set_xticklabels(x_labels, fontsize=8)
    ax3.set_ylim(0, max(float(df["Total ICs"].max()) + 2.0, 3.0))
    ax3.legend(loc="upper right", frameon=True, fontsize=8)
    ax3.grid(axis="y", linestyle="--", alpha=0.4)

    # D. Runtime is explicitly a system-default benchmark.
    ax4 = axs[1, 1]
    runtimes = df["Runtime (s)"].to_numpy(dtype=float)
    average_runtime = float(np.mean(runtimes))
    runtime_bars = ax4.bar(x_indices, runtimes, color="#34495e", edgecolor="black", linewidth=0.6, alpha=0.85)
    ax4.axhline(average_runtime, color="#e74c3c", linestyle="--", linewidth=1.5, label=f"Mean ({average_runtime:.2f} s)")
    for bar, value in zip(runtime_bars, runtimes):
        ax4.text(bar.get_x() + bar.get_width() / 2.0, value + 0.4, f"{value:.1f}s", ha="center", va="bottom", fontsize=8)
    ax4.set_title("D. Recorded pipeline runtime (no explicit GPU selection)", fontsize=11, fontweight="bold")
    ax4.set_xlabel("Subject / recording")
    ax4.set_ylabel("Execution time (seconds)")
    ax4.set_xticks(x_indices)
    ax4.set_xticklabels(x_labels, fontsize=8)
    ax4.set_ylim(0, max(runtimes) + 6.0)
    ax4.legend(loc="upper right", frameon=True, fontsize=8)
    ax4.grid(axis="y", linestyle="--", alpha=0.4)

    fig.text(
        0.5,
        0.012,
        "ICLabel outputs are model predictions, not manually verified component ground truth.",
        ha="center",
        fontsize=9,
        color="#555555",
    )
    plt.tight_layout(rect=[0, 0.035, 1, 0.95])

    figure_path = output_dir / "cohort_iclabel_summary_dashboard.png"
    metrics_path = output_dir / "cohort_iclabel_aggregate_metrics.json"
    fig.savefig(figure_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return figure_path, metrics_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    figure_path, metrics_path = generate_dashboard(args.csv, args.output_dir)
    print(f"Dashboard: {figure_path.resolve()}")
    print(f"Metrics:   {metrics_path.resolve()}")


if __name__ == "__main__":
    main()
