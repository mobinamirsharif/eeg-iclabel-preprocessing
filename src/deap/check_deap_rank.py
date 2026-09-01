"""Check the V3 DEAP ICA request against the estimated EEG rank.

This diagnostic reproduces only the preprocessing needed for the rank check. It
does not fit ICA, run ICLabel, download DEAP, or write participant-level output.
Users must provide an authorized copy of the DEAP ``data_preprocessed_python``
package, either with ``--data-dir`` or the ``DEAP_DATA_DIR`` environment
variable. If neither is supplied, the script also checks the current directory
and an existing standard KaggleHub cache without initiating a download.
"""

from __future__ import annotations

import argparse
import os
import pickle
import re
from pathlib import Path

import mne
import numpy as np


SAMPLING_RATE_HZ = 128.0
LOW_CUTOFF_HZ = 1.0
HIGH_CUTOFF_HZ = 55.0
TRIALS_USED = 5
CROSSFADE_SECONDS = 0.5
REQUESTED_ICA_COMPONENTS = 15

DEAP_32_CHANNELS = [
    "Fp1",
    "AF3",
    "F3",
    "F7",
    "FC5",
    "FC1",
    "C3",
    "T7",
    "CP5",
    "CP1",
    "P3",
    "P7",
    "PO3",
    "O1",
    "Oz",
    "Pz",
    "Fp2",
    "AF4",
    "Fz",
    "F4",
    "F8",
    "FC6",
    "FC2",
    "Cz",
    "C4",
    "T8",
    "CP6",
    "CP2",
    "P4",
    "P8",
    "PO4",
    "O2",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Authorized directory containing DEAP sXX.dat files.",
    )
    parser.add_argument(
        "--subject",
        default="s01",
        help="Subject identifier to check (default: s01).",
    )
    return parser.parse_args()


def normalize_subject(value: str) -> str:
    subject = value.strip().lower()
    if subject.isdigit():
        subject = f"s{int(subject):02d}"
    if not re.fullmatch(r"s(?:0[1-9]|[12][0-9]|3[0-2])", subject):
        raise ValueError("Subject must be between s01 and s32.")
    return subject


def candidate_roots(data_dir: Path | None) -> list[Path]:
    roots: list[Path] = []
    if data_dir is not None:
        roots.append(data_dir.expanduser())

    environment_dir = os.environ.get("DEAP_DATA_DIR")
    if environment_dir:
        roots.append(Path(environment_dir).expanduser())

    roots.extend(
        [
            Path.cwd(),
            Path.cwd() / "data_preprocessed_python",
            Path.home()
            / ".cache"
            / "kagglehub"
            / "datasets"
            / "manh123df"
            / "deap-dataset",
        ]
    )
    return roots


def locate_subject_file(data_dir: Path | None, subject: str) -> Path:
    filename = f"{subject}.dat"
    checked: list[Path] = []

    for root in candidate_roots(data_dir):
        root = root.resolve()
        direct_candidates = [root / filename, root / "data_preprocessed_python" / filename]
        for candidate in direct_candidates:
            checked.append(candidate)
            if candidate.is_file():
                return candidate

        if root.is_dir() and root.name == "deap-dataset":
            matches = sorted(root.glob(f"versions/*/deap-dataset/data_preprocessed_python/{filename}"))
            if matches:
                return matches[-1]

    checked_text = "\n  - ".join(str(path) for path in checked)
    raise FileNotFoundError(
        f"Could not locate {filename}. Provide the authorized DEAP directory with "
        f"--data-dir or DEAP_DATA_DIR. Checked:\n  - {checked_text}"
    )


def load_eeg_trials(subject_file: Path) -> tuple[tuple[int, ...], np.ndarray]:
    with subject_file.open("rb") as handle:
        payload = pickle.load(handle, encoding="latin1")

    if "data" not in payload:
        raise KeyError(f"Missing 'data' array in {subject_file}")

    matrix = np.asarray(payload["data"], dtype=np.float64)
    if matrix.ndim != 3:
        raise ValueError(f"Expected a 3D trial-by-channel-by-sample array, got {matrix.shape}")
    if matrix.shape[0] < TRIALS_USED or matrix.shape[1] < len(DEAP_32_CHANNELS):
        raise ValueError(
            f"Expected at least {TRIALS_USED} trials and 32 channels, got {matrix.shape}"
        )

    eeg_trials = matrix[:TRIALS_USED, : len(DEAP_32_CHANNELS), :]
    return matrix.shape, eeg_trials


def concatenate_with_crossfade(trials: np.ndarray) -> np.ndarray:
    ramp_samples = int(round(CROSSFADE_SECONDS * SAMPLING_RATE_HZ))
    if ramp_samples <= 0:
        return np.concatenate(list(trials), axis=1)
    if trials.shape[-1] <= ramp_samples:
        raise ValueError("Crossfade duration must be shorter than one trial.")

    continuous = trials[0].copy()
    fade_out = np.linspace(1.0, 0.0, ramp_samples, dtype=np.float64)[None, :]
    fade_in = np.linspace(0.0, 1.0, ramp_samples, dtype=np.float64)[None, :]

    for next_trial in trials[1:]:
        blend = continuous[:, -ramp_samples:] * fade_out + next_trial[:, :ramp_samples] * fade_in
        continuous = np.concatenate(
            [continuous[:, :-ramp_samples], blend, next_trial[:, ramp_samples:]],
            axis=1,
        )
    return continuous


def estimate_ranks(continuous_microvolts: np.ndarray) -> tuple[int, int]:
    info = mne.create_info(DEAP_32_CHANNELS, SAMPLING_RATE_HZ, ch_types="eeg")
    raw = mne.io.RawArray(continuous_microvolts * 1e-6, info, verbose=False)
    raw.set_montage("standard_1020", on_missing="raise", verbose=False)
    raw.filter(LOW_CUTOFF_HZ, HIGH_CUTOFF_HZ, verbose=False)

    rank_before_car = int(mne.compute_rank(raw, tol="auto", verbose=False)["eeg"])
    raw.set_eeg_reference("average", projection=False, verbose=False)
    rank_after_car = int(mne.compute_rank(raw, tol="auto", verbose=False)["eeg"])
    return rank_before_car, rank_after_car


def main() -> None:
    args = parse_args()
    subject = normalize_subject(args.subject)
    subject_file = locate_subject_file(args.data_dir, subject)
    original_shape, eeg_trials = load_eeg_trials(subject_file)
    continuous = concatenate_with_crossfade(eeg_trials)
    rank_before_car, rank_after_car = estimate_ranks(continuous)
    overflow = REQUESTED_ICA_COMPONENTS > rank_after_car

    print("DEAP V3 ICA-RANK DIAGNOSTIC")
    print(f"Subject: {subject}")
    print(f"Source shape: {original_shape}")
    print(f"EEG input: first 32 channels, first {TRIALS_USED} trials")
    print(f"Continuous EEG shape: {continuous.shape}")
    print(
        "Configuration: "
        f"{SAMPLING_RATE_HZ:g} Hz, {LOW_CUTOFF_HZ:g}-{HIGH_CUTOFF_HZ:g} Hz, "
        f"{CROSSFADE_SECONDS:g} s crossfade, average reference"
    )
    print(f"Estimated EEG rank before average reference: {rank_before_car}")
    print(f"Estimated EEG rank after average reference: {rank_after_car}")
    print(f"Requested ICA components: {REQUESTED_ICA_COMPONENTS}")
    print(f"ICA-rank overflow: {'YES' if overflow else 'NO'}")

    if overflow:
        print(
            "The requested ICA component count exceeds the estimated post-reference EEG rank "
            "for this diagnostic."
        )
    else:
        print(
            "The requested ICA component count does not exceed the estimated post-reference "
            "EEG rank. This test therefore does not support ICA-rank overflow as the cause of "
            "the V3 Heart Beat-dominant output."
        )
        print(
            "Scope: this result does not claim that the 32-channel data are full rank in every "
            "possible sense; it only compares the V3 request with this rank estimate."
        )


if __name__ == "__main__":
    main()
