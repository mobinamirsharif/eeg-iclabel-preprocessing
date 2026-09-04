"""Build an exploratory paired B-versus-D summary from committed BCI results.

The comparison pairs subject/session/run rows only. It does not pair individual
ICA components across the independently fitted B and D conditions.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPOSITORY_ROOT / "results" / "controlled_experiment" / "condition_summary.csv"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "results" / "controlled_experiment"
B_CONDITION = "B_250Hz_4-45Hz"
D_CONDITION = "D_128Hz_4-45Hz"
DIFFERENCE_DIRECTION = "D - B"
UNIT = "percentage points"
EXPECTED_RECORDINGS = 9
BOOTSTRAP_RESAMPLES = 10_000
RANDOM_SEED = 42
CLASSES = (
    "Brain",
    "Muscle",
    "Eye Blink",
    "Heart Beat",
    "Line Noise",
    "Channel Noise",
    "Other",
)
DIFFERENCE_FIELDS = tuple(f"{label} Difference (pp)" for label in CLASSES)
SUBJECT_FIELDS = (
    "Subject",
    "Session",
    "Run",
    "Difference Direction",
    "Unit",
    *DIFFERENCE_FIELDS,
)
SUMMARY_FIELDS = (
    "Analysis",
    "Class",
    "Difference Direction",
    "Unit",
    "Selected Recordings",
    "Bootstrap Resamples",
    "Random Seed",
    "Mean Difference",
    "Median Difference",
    "Exploratory 95% CI Lower",
    "Exploratory 95% CI Upper",
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV header: {path}")
        required = {"Subject", "Session", "Run", "Condition", "Total ICs", *CLASSES}
        missing = sorted(required.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        return list(reader)


def _condition_index(
    rows: list[dict[str, str]], condition: str
) -> dict[str, dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["Condition"] != condition:
            continue
        subject = row["Subject"]
        if subject in selected:
            raise ValueError(f"Duplicate {condition} row for {subject}")
        selected[subject] = row
    return selected


def _validated_counts(row: dict[str, str]) -> tuple[int, dict[str, int]]:
    total = int(row["Total ICs"])
    counts = {label: int(row[label]) for label in CLASSES}
    if total <= 0 or sum(counts.values()) != total:
        raise ValueError(
            f"Seven-class counts do not reconcile for {row['Subject']} / "
            f"{row['Condition']}"
        )
    return total, counts


def build_subject_differences(input_path: Path) -> list[dict[str, object]]:
    """Pair B and D by recording and return D-minus-B class differences."""

    rows = _read_rows(input_path)
    b_rows = _condition_index(rows, B_CONDITION)
    d_rows = _condition_index(rows, D_CONDITION)
    if set(b_rows) != set(d_rows):
        raise ValueError("B and D conditions do not contain the same subjects")
    if len(b_rows) != EXPECTED_RECORDINGS:
        raise ValueError(
            f"Expected {EXPECTED_RECORDINGS} paired recordings, found {len(b_rows)}"
        )

    differences: list[dict[str, object]] = []
    for subject in sorted(b_rows):
        b_row = b_rows[subject]
        d_row = d_rows[subject]
        b_recording = (b_row["Session"], b_row["Run"])
        d_recording = (d_row["Session"], d_row["Run"])
        if b_recording != d_recording:
            raise ValueError(
                f"B and D do not use the same recording for {subject}: "
                f"{b_recording} versus {d_recording}"
            )

        b_total, b_counts = _validated_counts(b_row)
        d_total, d_counts = _validated_counts(d_row)
        output: dict[str, object] = {
            "Subject": subject,
            "Session": b_recording[0],
            "Run": b_recording[1],
            "Difference Direction": DIFFERENCE_DIRECTION,
            "Unit": UNIT,
        }
        for label, field in zip(CLASSES, DIFFERENCE_FIELDS):
            output[field] = (
                d_counts[label] / d_total - b_counts[label] / b_total
            ) * 100.0
        differences.append(output)
    return differences


def build_paired_summary(
    subject_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Summarize paired differences with an exploratory subject bootstrap."""

    if len(subject_rows) != EXPECTED_RECORDINGS:
        raise ValueError(f"Expected {EXPECTED_RECORDINGS} paired subject rows")
    bootstrap_indices = np.random.default_rng(RANDOM_SEED).integers(
        0,
        len(subject_rows),
        size=(BOOTSTRAP_RESAMPLES, len(subject_rows)),
    )

    summary: list[dict[str, object]] = []
    for label, field in zip(CLASSES, DIFFERENCE_FIELDS):
        values = np.asarray([float(row[field]) for row in subject_rows])
        bootstrap_means = values[bootstrap_indices].mean(axis=1)
        lower, upper = np.quantile(bootstrap_means, [0.025, 0.975])
        summary.append(
            {
                "Analysis": "Exploratory paired subject-level bootstrap",
                "Class": label,
                "Difference Direction": DIFFERENCE_DIRECTION,
                "Unit": UNIT,
                "Selected Recordings": len(subject_rows),
                "Bootstrap Resamples": BOOTSTRAP_RESAMPLES,
                "Random Seed": RANDOM_SEED,
                "Mean Difference": float(values.mean()),
                "Median Difference": float(np.median(values)),
                "Exploratory 95% CI Lower": float(lower),
                "Exploratory 95% CI Upper": float(upper),
            }
        )
    return summary


def _formatted_row(row: dict[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    return {
        field: f"{value:.6f}" if isinstance(value, float) else value
        for field, value in ((field, row[field]) for field in fields)
    }


def _write_rows(
    path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_formatted_row(row, fields) for row in rows)


def generate_outputs(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Regenerate both deterministic B-versus-D CSV artifacts."""

    subject_rows = build_subject_differences(input_path)
    summary_rows = build_paired_summary(subject_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    subject_path = output_dir / "b_vs_d_subject_differences.csv"
    summary_path = output_dir / "b_vs_d_paired_summary.csv"
    _write_rows(subject_path, SUBJECT_FIELDS, subject_rows)
    _write_rows(summary_path, SUMMARY_FIELDS, summary_rows)
    return subject_path, summary_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    subject_path, summary_path = generate_outputs(args.input, args.output_dir)
    print(f"Subject differences: {subject_path.resolve()}")
    print(f"Paired summary:      {summary_path.resolve()}")


if __name__ == "__main__":
    main()
