from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.deap.pipeline_helpers import (
    EXPECTED_DEAP_SHAPE,
    DeapInputError,
    concatenate_trials_with_crossfade,
    validate_deap_payload,
    validate_screening_parameters,
)


def valid_parameters(tmp_path: Path) -> dict[str, object]:
    return {
        "data_dir": tmp_path,
        "subjects": [1, 32],
        "max_trials": 5,
        "n_components": 30,
        "low_freq": 1.0,
        "high_freq": 55.0,
        "crossfade_seconds": 0.5,
    }


def test_zero_crossfade_concatenates_without_overlap() -> None:
    trials = np.array([[[1.0, 2.0, 3.0]], [[4.0, 5.0, 6.0]]])

    result = concatenate_trials_with_crossfade(trials, 0)

    np.testing.assert_array_equal(result, [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]])


def test_known_crossfade_values_and_output_length() -> None:
    trials = np.array([[[0.0, 0.0, 0.0, 0.0]], [[10.0, 10.0, 10.0, 10.0]]])

    result = concatenate_trials_with_crossfade(trials, 2)

    assert result.shape == (1, 6)
    np.testing.assert_allclose(result, [[0.0, 0.0, 0.0, 10.0, 10.0, 10.0]])


@pytest.mark.parametrize("crossfade_samples", [4, 5])
def test_crossfade_must_be_shorter_than_a_trial(crossfade_samples: int) -> None:
    trials = np.zeros((2, 1, 4))

    with pytest.raises(ValueError, match="shorter than an individual trial"):
        concatenate_trials_with_crossfade(trials, crossfade_samples)


@pytest.mark.parametrize("subject", [0, 33])
def test_subject_ids_are_bounded(tmp_path: Path, subject: int) -> None:
    parameters = valid_parameters(tmp_path)
    parameters["subjects"] = [subject]

    with pytest.raises(ValueError, match="between 1 and 32"):
        validate_screening_parameters(**parameters)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("max_trials", 0, "max_trials must be positive"),
        ("n_components", 1, "n_components must be at least 2"),
        ("crossfade_seconds", -0.1, "crossfade_seconds must be in"),
        ("crossfade_seconds", 2.0, "crossfade_seconds must be in"),
    ],
)
def test_count_and_crossfade_boundaries(
    tmp_path: Path, field: str, value: float, message: str
) -> None:
    parameters = valid_parameters(tmp_path)
    parameters[field] = value

    with pytest.raises(ValueError, match=message):
        validate_screening_parameters(**parameters)


@pytest.mark.parametrize(
    ("low_freq", "high_freq"),
    [(0.0, 55.0), (55.0, 55.0), (1.0, 64.0), (20.0, 10.0)],
)
def test_frequency_bounds_are_strictly_below_nyquist(
    tmp_path: Path, low_freq: float, high_freq: float
) -> None:
    parameters = valid_parameters(tmp_path)
    parameters["low_freq"] = low_freq
    parameters["high_freq"] = high_freq

    with pytest.raises(ValueError, match="Nyquist"):
        validate_screening_parameters(**parameters)


def test_missing_data_key_fails_clearly() -> None:
    with pytest.raises(DeapInputError, match="missing the required 'data' key"):
        validate_deap_payload({}, "s01")


def test_non_3d_payload_reports_expected_and_observed_shapes() -> None:
    with pytest.raises(DeapInputError) as error:
        validate_deap_payload({"data": np.zeros((40, 40))}, "s01")

    assert str(EXPECTED_DEAP_SHAPE) in str(error.value)
    assert "observed (40, 40)" in str(error.value)
    assert error.value.observed_shape == (40, 40)


def test_payload_with_fewer_than_32_channels_is_rejected() -> None:
    with pytest.raises(DeapInputError, match="at least 32 EEG channels") as error:
        validate_deap_payload({"data": np.zeros((1, 31, 1))}, "s01")

    assert error.value.observed_shape == (1, 31, 1)


def test_nonstandard_layout_is_an_error_without_axis_reinterpretation() -> None:
    observed_shape = (39, 40, 100)

    with pytest.raises(DeapInputError) as error:
        validate_deap_payload({"data": np.zeros(observed_shape)}, "s01")

    message = str(error.value)
    assert str(EXPECTED_DEAP_SHAPE) in message
    assert f"observed {observed_shape}" in message
    assert "does not automatically transpose or reinterpret" in message
