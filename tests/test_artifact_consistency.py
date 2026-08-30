from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DISPLAY_CLASS_COLUMNS = (
    "Brain",
    "Muscle",
    "Eye Blink",
    "Heart Beat",
    "Line Noise",
    "Channel Noise",
    "Other",
)
DEAP_CLASS_COLUMNS = tuple(f"{name} Predictions" for name in DISPLAY_CLASS_COLUMNS)
ARCHIVED_CLASS_COLUMNS = (
    "brain_components",
    "muscle_components",
    "eye_components",
    "heart_components",
    "line_noise_components",
    "channel_noise_components",
    "other_components",
)
ARCHIVED_COLUMN_TO_LABEL = {
    "brain_components": "brain",
    "muscle_components": "muscle artifact",
    "eye_components": "eye blink",
    "heart_components": "heart beat",
    "line_noise_components": "line noise",
    "channel_noise_components": "channel noise",
    "other_components": "other",
}
LABEL_TO_DISPLAY = {
    "brain": "Brain",
    "muscle artifact": "Muscle",
    "eye blink": "Eye Blink",
    "heart beat": "Heart Beat",
    "line noise": "Line Noise",
    "channel noise": "Channel Noise",
    "other": "Other",
}
STAGE_DIRECTORIES = {
    "Baseline": "00_baseline",
    "V1": "01_channel_order",
    "V2": "02_filter_confidence",
    "V3": "03_crossfade_visual",
    "V4": "04_rank_aware",
}


def read_csv(relative_path: str) -> list[dict[str, str]]:
    with (REPOSITORY_ROOT / relative_path).open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        return list(csv.DictReader(handle))


def read_json(relative_path: str) -> object:
    with (REPOSITORY_ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def integer(row: dict[str, str], column: str) -> int:
    return int(float(row[column]))


def assert_row_reconciles(
    row: dict[str, str], class_columns: tuple[str, ...], total_column: str
) -> None:
    assert sum(integer(row, column) for column in class_columns) == integer(
        row, total_column
    )


def aggregate(rows: list[dict[str, str]], columns: tuple[str, ...]) -> dict[str, int]:
    return {
        column: sum(integer(row, column) for row in rows) for column in columns
    }


def test_bci_summary_reconciles_all_seven_classes() -> None:
    rows = read_csv("results/summary_tables/cohort_iclabel_summary.csv")
    assert len(rows) == 9
    for row in rows:
        assert_row_reconciles(row, DISPLAY_CLASS_COLUMNS, "Total ICs")
        assert integer(row, "Artifacts Removed") == sum(
            integer(row, column)
            for column in (
                "Muscle",
                "Eye Blink",
                "Heart Beat",
                "Line Noise",
                "Channel Noise",
            )
        )

    totals = aggregate(rows, DISPLAY_CLASS_COLUMNS)
    metrics = read_json("figures/cohort_iclabel_aggregate_metrics.json")
    assert sum(integer(row, "Total ICs") for row in rows) == 135
    assert sum(totals.values()) == metrics["total_ics"] == 135
    assert totals["Brain"] == metrics["brain"] == 88
    assert totals["Other"] == metrics["other"] == 13
    assert sum(integer(row, "Artifacts Removed") for row in rows) == metrics[
        "artifacts"
    ] == 34


def test_controlled_experiment_has_complete_committed_outputs() -> None:
    summaries = read_csv("results/controlled_experiment/condition_summary.csv")
    components = read_csv("results/controlled_experiment/component_predictions.csv")
    metadata = read_json("results/controlled_experiment/experiment_metadata.json")

    assert len(summaries) == 36
    assert len(components) == 540
    assert metadata["failures"] == []
    assert len({row["Subject"] for row in summaries}) == 9
    assert len({row["Condition"] for row in summaries}) == 4

    component_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in components:
        component_counts[(row["Subject"], row["Condition"])][
            LABEL_TO_DISPLAY[row["Predicted Label"]]
        ] += 1

    for row in summaries:
        assert_row_reconciles(row, DISPLAY_CLASS_COLUMNS, "Total ICs")
        key = (row["Subject"], row["Condition"])
        assert sum(component_counts[key].values()) == integer(row, "Total ICs")
        for column in DISPLAY_CLASS_COLUMNS:
            assert component_counts[key][column] == integer(row, column)

    assert sum(integer(row, "Total ICs") for row in summaries) == 540
    assert set(component_counts) == {
        (row["Subject"], row["Condition"]) for row in summaries
    }


def test_deap_screening_reconciles_counts_and_trial_accounting() -> None:
    rows = read_csv("results/deap_screening/deap_subject_screening_summary.csv")
    metadata = read_json("results/deap_screening/experiment_metadata.json")
    probabilities = read_csv(
        "results/deap_screening/heart_beat_prediction_probabilities.csv"
    )

    assert len(rows) == 32
    assert all(row["Status"] == "Success" for row in rows)
    for row in rows:
        assert_row_reconciles(row, DEAP_CLASS_COLUMNS, "ICA Components")

    totals = aggregate(rows, DEAP_CLASS_COLUMNS)
    metadata_totals = {
        "Brain Predictions": metadata["class_distribution"]["brain"]["count"],
        "Muscle Predictions": metadata["class_distribution"]["muscle"]["count"],
        "Eye Blink Predictions": metadata["class_distribution"]["eye_blink"]["count"],
        "Heart Beat Predictions": metadata["class_distribution"]["heart_beat"]["count"],
        "Line Noise Predictions": metadata["class_distribution"]["line_noise"]["count"],
        "Channel Noise Predictions": metadata["class_distribution"]["channel_noise"]["count"],
        "Other Predictions": metadata["class_distribution"]["other"]["count"],
    }
    assert totals == metadata_totals
    assert sum(totals.values()) == metadata["total_ica_components"] == 960
    assert sum(integer(row, "Trials Used for ICA") for row in rows) == 160
    assert metadata["total_trials_used_for_ica"] == 160
    assert len(probabilities) == totals["Heart Beat Predictions"] == 775


def test_historical_stage_aggregates_match_archived_csv_and_json() -> None:
    comparison_rows = {
        row["Stage"]: row
        for row in read_csv("results/deap_version_history/version_comparison.csv")
    }
    assert set(comparison_rows) == set(STAGE_DIRECTORIES)

    version_columns = tuple(f"{name} Predictions" for name in DISPLAY_CLASS_COLUMNS)
    for stage, directory in STAGE_DIRECTORIES.items():
        archived_rows = read_csv(
            f"archive/deap_history/{directory}/results/summary/"
            "deap_32_subjects_summary.csv"
        )
        assert len(archived_rows) == 32
        for row in archived_rows:
            assert_row_reconciles(row, ARCHIVED_CLASS_COLUMNS, "ica_components")

        archived_totals = aggregate(archived_rows, ARCHIVED_CLASS_COLUMNS)
        expected_totals = dict(zip(version_columns, archived_totals.values()))
        comparison = comparison_rows[stage]
        for column, expected in expected_totals.items():
            assert integer(comparison, column) == expected
        assert integer(comparison, "ICA Components Total") == sum(
            archived_totals.values()
        )
        assert integer(comparison, "Trials Used for ICA") == 160

        report_directory = (
            REPOSITORY_ROOT
            / "archive"
            / "deap_history"
            / directory
            / "results"
            / "iclabel_reports"
        )
        report_paths = sorted(report_directory.glob("*.json"))
        assert len(report_paths) == 32
        report_labels: Counter[str] = Counter()
        for report_path in report_paths:
            with report_path.open(encoding="utf-8") as handle:
                report = json.load(handle)
            details = report["component_details"]
            assert len(details) == report.get(
                "total_ica_components", report.get("ica_components_used")
            )
            report_labels.update(item["predicted_class"] for item in details)

        for archived_column, label in ARCHIVED_COLUMN_TO_LABEL.items():
            assert report_labels[label] == archived_totals[archived_column]
