"""Lightweight validation and trial-concatenation helpers for DEAP screening."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np


EXPECTED_DEAP_SHAPE = (40, 40, 8064)
SAMPLING_RATE_HZ = 128.0


class DeapInputError(ValueError):
    """A DEAP payload error that may carry the observed array shape."""

    def __init__(
        self, message: str, observed_shape: tuple[int, ...] | None = None
    ) -> None:
        super().__init__(message)
        self.observed_shape = observed_shape


def validate_screening_parameters(
    *,
    data_dir: Path,
    subjects: Sequence[int],
    max_trials: int,
    n_components: int,
    low_freq: float,
    high_freq: float,
    crossfade_seconds: float,
) -> None:
    """Validate DEAP screening arguments without importing the scientific stack."""

    if not data_dir.is_dir():
        raise FileNotFoundError(f"DEAP data directory not found: {data_dir}")
    if any(subject < 1 or subject > 32 for subject in subjects):
        raise ValueError("DEAP subject IDs must be between 1 and 32")
    if max_trials < 1:
        raise ValueError("max_trials must be positive")
    if n_components < 2:
        raise ValueError("n_components must be at least 2")
    if not 0 <= crossfade_seconds < 2:
        raise ValueError("crossfade_seconds must be in [0, 2)")
    nyquist = SAMPLING_RATE_HZ / 2.0
    if not 0 < low_freq < high_freq < nyquist:
        raise ValueError(
            f"Require 0 < low_freq < high_freq < Nyquist ({nyquist} Hz)"
        )


def validate_deap_payload(
    payload: object, subject_tag: str
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Return the standard DEAP data matrix or fail without reinterpreting axes."""

    if not isinstance(payload, Mapping) or "data" not in payload:
        raise DeapInputError(
            f"DEAP payload for {subject_tag} is missing the required 'data' key"
        )

    try:
        matrix = np.asarray(payload["data"], dtype=float)
    except (TypeError, ValueError) as exc:
        raise DeapInputError(
            f"DEAP payload for {subject_tag} contains a non-numeric 'data' value"
        ) from exc

    observed_shape = tuple(int(value) for value in matrix.shape)
    if matrix.ndim != 3:
        raise DeapInputError(
            f"Invalid DEAP data shape for {subject_tag}: expected "
            f"{EXPECTED_DEAP_SHAPE}, observed {observed_shape}; the data array "
            "must be three-dimensional (trials, channels, samples)",
            observed_shape,
        )
    if matrix.shape[1] < 32:
        raise DeapInputError(
            f"Invalid DEAP data shape for {subject_tag}: expected "
            f"{EXPECTED_DEAP_SHAPE}, observed {observed_shape}; at least 32 EEG "
            "channels are required",
            observed_shape,
        )
    if observed_shape != EXPECTED_DEAP_SHAPE:
        raise DeapInputError(
            f"Unsupported DEAP data shape for {subject_tag}: expected "
            f"{EXPECTED_DEAP_SHAPE}, observed {observed_shape}. This pipeline "
            "supports the standard data_preprocessed_python layout and does not "
            "automatically transpose or reinterpret array axes.",
            observed_shape,
        )
    return matrix, observed_shape


def concatenate_trials_with_crossfade(
    trials: np.ndarray, crossfade_samples: int
) -> np.ndarray:
    """Concatenate trial arrays, optionally blending samples at each boundary."""

    trial_array = np.asarray(trials)
    if trial_array.ndim != 3 or trial_array.shape[0] < 1:
        raise ValueError("trials must have shape (trials, channels, samples)")
    if isinstance(crossfade_samples, bool) or not isinstance(
        crossfade_samples, (int, np.integer)
    ):
        raise TypeError("crossfade_samples must be an integer")
    if crossfade_samples < 0:
        raise ValueError("crossfade_samples must be non-negative")
    if crossfade_samples >= trial_array.shape[2] and crossfade_samples != 0:
        raise ValueError(
            "crossfade_samples must be shorter than an individual trial"
        )

    continuous = trial_array[0].copy()
    for next_trial in trial_array[1:]:
        if crossfade_samples == 0:
            continuous = np.concatenate([continuous, next_trial], axis=1)
            continue
        fade_out = np.linspace(1.0, 0.0, crossfade_samples, endpoint=True)
        fade_in = np.linspace(0.0, 1.0, crossfade_samples, endpoint=True)
        blended = (
            continuous[:, -crossfade_samples:] * fade_out
            + next_trial[:, :crossfade_samples] * fade_in
        )
        continuous = np.concatenate(
            [
                continuous[:, :-crossfade_samples],
                blended,
                next_trial[:, crossfade_samples:],
            ],
            axis=1,
        )
    return continuous
