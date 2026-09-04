from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.controlled_experiment.summarize_b_vs_d import (
    DIFFERENCE_DIRECTION,
    EXPECTED_RECORDINGS,
    SUBJECT_FIELDS,
    SUMMARY_FIELDS,
    build_paired_summary,
    build_subject_differences,
    generate_outputs,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    REPOSITORY_ROOT / "results" / "controlled_experiment" / "condition_summary.csv"
)
RESULT_DIRECTORY = REPOSITORY_ROOT / "results" / "controlled_experiment"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_subject_rows_pair_the_same_nine_recordings_and_use_d_minus_b() -> None:
    rows = build_subject_differences(INPUT_PATH)

    assert len(rows) == EXPECTED_RECORDINGS == 9
    assert {row["Subject"] for row in rows} == {
        f"sub-{subject:02d}" for subject in range(1, 10)
    }
    assert all(row["Session"] == "0train" and row["Run"] == "0" for row in rows)
    assert all(row["Difference Direction"] == DIFFERENCE_DIRECTION for row in rows)

    subject_02 = next(row for row in rows if row["Subject"] == "sub-02")
    assert subject_02["Brain Difference (pp)"] == pytest.approx(13.3333333333)
    assert subject_02["Heart Beat Difference (pp)"] == pytest.approx(-20.0)


def test_mismatched_session_or_run_is_rejected(tmp_path: Path) -> None:
    rows = read_csv(INPUT_PATH)
    for row in rows:
        if row["Subject"] == "sub-01" and row["Condition"] == "D_128Hz_4-45Hz":
            row["Session"] = "different-session"
            break
    modified_input = tmp_path / "condition_summary.csv"
    with modified_input.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="do not use the same recording"):
        build_subject_differences(modified_input)


def test_paired_summary_has_deterministic_exploratory_values() -> None:
    summary = {
        row["Class"]: row
        for row in build_paired_summary(build_subject_differences(INPUT_PATH))
    }

    assert summary["Brain"]["Mean Difference"] == pytest.approx(-0.7407407407)
    assert summary["Brain"]["Median Difference"] == pytest.approx(0.0)
    assert summary["Brain"]["Exploratory 95% CI Lower"] == pytest.approx(
        -4.4444444444
    )
    assert summary["Brain"]["Exploratory 95% CI Upper"] == pytest.approx(
        3.7037037037
    )
    assert summary["Heart Beat"]["Mean Difference"] == pytest.approx(
        -2.9629629630
    )
    assert summary["Heart Beat"]["Exploratory 95% CI Lower"] == pytest.approx(
        -7.4074074074
    )
    assert summary["Heart Beat"]["Exploratory 95% CI Upper"] == pytest.approx(0.0)


def test_regeneration_matches_committed_csv_schema_and_bytes(tmp_path: Path) -> None:
    generated_subjects, generated_summary = generate_outputs(INPUT_PATH, tmp_path)
    committed_subjects = RESULT_DIRECTORY / "b_vs_d_subject_differences.csv"
    committed_summary = RESULT_DIRECTORY / "b_vs_d_paired_summary.csv"

    assert generated_subjects.read_bytes() == committed_subjects.read_bytes()
    assert generated_summary.read_bytes() == committed_summary.read_bytes()
    assert tuple(read_csv(generated_subjects)[0]) == SUBJECT_FIELDS
    assert tuple(read_csv(generated_summary)[0]) == SUMMARY_FIELDS
    assert not any("p-value" in field.casefold() for field in SUMMARY_FIELDS)
