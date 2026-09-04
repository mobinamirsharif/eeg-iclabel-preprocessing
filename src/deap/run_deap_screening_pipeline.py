"""Run a transparent ICLabel screening analysis on local DEAP EEG files.

This pipeline reports ICLabel predictions without treating them as component
ground truth and without automatically reconstructing or publishing "cleaned"
EEG. DEAP access is governed by its own license, so users must supply a local
directory containing the authorized ``s01.dat`` ... ``s32.dat`` files.
"""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd
from mne.preprocessing import ICA
from mne_icalabel import label_components

if __package__:
    from .pipeline_helpers import (
        EXPECTED_DEAP_SHAPE,
        SAMPLING_RATE_HZ,
        concatenate_trials_with_crossfade,
        validate_deap_payload,
        validate_screening_parameters,
    )
else:
    from pipeline_helpers import (
        EXPECTED_DEAP_SHAPE,
        SAMPLING_RATE_HZ,
        concatenate_trials_with_crossfade,
        validate_deap_payload,
        validate_screening_parameters,
    )


FINAL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = FINAL_ROOT / "results" / "deap_screening_run"
RANDOM_SEED = 42
DEFAULT_LOW_FREQ_HZ = 1.0
DEFAULT_HIGH_FREQ_HZ = 55.0
DEFAULT_MAX_TRIALS = 5
DEFAULT_N_COMPONENTS = 30
DEFAULT_CROSSFADE_SECONDS = 0.5

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

ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other",
]

ARTIFACT_POLICY_CLASSES = {
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Authorized local directory containing DEAP sXX.dat files",
    )
    parser.add_argument("--subjects", nargs="+", type=int, default=list(range(1, 33)))
    parser.add_argument(
        "--max-trials",
        type=int,
        default=DEFAULT_MAX_TRIALS,
        help=(
            "Maximum trials per subject supplied to ICA (default: 5, matching "
            "the archived V4-compatible screening configuration)"
        ),
    )
    parser.add_argument(
        "--n-components",
        type=int,
        default=DEFAULT_N_COMPONENTS,
        help=(
            "Requested ICA components before rank capping (default: 30, matching "
            "the archived V4-compatible screening configuration)"
        ),
    )
    parser.add_argument(
        "--low-freq",
        type=float,
        default=DEFAULT_LOW_FREQ_HZ,
        help="High-pass cutoff in Hz (historical V4-compatible default: 1)",
    )
    parser.add_argument(
        "--high-freq",
        type=float,
        default=DEFAULT_HIGH_FREQ_HZ,
        help="Low-pass cutoff in Hz (historical V4-compatible default: 55)",
    )
    parser.add_argument(
        "--crossfade-seconds",
        type=float,
        default=DEFAULT_CROSSFADE_SECONDS,
        help=(
            "Experimental trial-boundary blend in seconds. The default 0.5 "
            "reproduces the archived V4-compatible configuration for historical "
            "comparison; it is not a universally validated recommendation. Use "
            "0 for no crossfade."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    validate_screening_parameters(
        data_dir=args.data_dir,
        subjects=args.subjects,
        max_trials=args.max_trials,
        n_components=args.n_components,
        low_freq=args.low_freq,
        high_freq=args.high_freq,
        crossfade_seconds=args.crossfade_seconds,
    )


def load_subject_eeg(
    data_dir: Path, subject_id: int, max_trials: int, crossfade_seconds: float
) -> tuple[mne.io.RawArray, int, int, tuple[int, ...]]:
    subject_path = data_dir / f"s{subject_id:02d}.dat"
    if not subject_path.is_file():
        raise FileNotFoundError(f"Subject file not found: {subject_path.name}")

    with subject_path.open("rb") as handle:
        payload = pickle.load(handle, encoding="latin1")
    matrix, observed_shape = validate_deap_payload(payload, f"s{subject_id:02d}")

    trials_available = int(matrix.shape[0])
    trials_used = min(max_trials, trials_available)
    eeg_trials = matrix[:trials_used, :32, :]
    crossfade_samples = int(round(crossfade_seconds * SAMPLING_RATE_HZ))
    continuous_microvolts = concatenate_trials_with_crossfade(
        eeg_trials, crossfade_samples
    )

    info = mne.create_info(
        ch_names=DEAP_32_CHANNELS, sfreq=SAMPLING_RATE_HZ, ch_types="eeg"
    )
    raw = mne.io.RawArray(continuous_microvolts * 1e-6, info, verbose=False)
    raw.set_montage(
        mne.channels.make_standard_montage("standard_1020"),
        on_missing="raise",
        verbose=False,
    )
    return raw, trials_available, trials_used, observed_shape


def evaluate_subject(
    raw: mne.io.BaseRaw,
    subject_tag: str,
    trials_available: int,
    trials_used: int,
    args: argparse.Namespace,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    start = time.perf_counter()
    raw.filter(
        l_freq=args.low_freq,
        h_freq=args.high_freq,
        fir_design="firwin",
        verbose=False,
    )
    raw.set_eeg_reference("average", projection=False, verbose=False)
    estimated_rank = int(mne.compute_rank(raw, rank=None, verbose=False)["eeg"])
    components_used = min(args.n_components, estimated_rank)
    if components_used < 2:
        raise RuntimeError(f"Insufficient EEG rank: {estimated_rank}")

    ica = ICA(
        n_components=components_used,
        method="infomax",
        fit_params={"extended": True},
        random_state=RANDOM_SEED,
        max_iter="auto",
    )
    ica.fit(raw, verbose=False)
    prediction = label_components(raw, ica, method="iclabel")
    labels = list(prediction["labels"])
    probabilities = np.asarray(prediction["y_pred_proba"], dtype=float)
    counts = {class_name: labels.count(class_name) for class_name in ICLABEL_CLASSES}
    if sum(counts.values()) != len(labels):
        raise RuntimeError("Seven-class counts do not reconcile to the ICA total")

    policy_count = sum(counts[class_name] for class_name in ARTIFACT_POLICY_CLASSES)
    elapsed = time.perf_counter() - start
    row: dict[str, object] = {
        "Subject": subject_tag,
        "Status": "Success",
        "Trials Available": trials_available,
        "Trials Used for ICA": trials_used,
        "EEG Rank": estimated_rank,
        "ICA Components": len(labels),
        "Artifact-Policy Predictions": policy_count,
        "Artifact-Policy Percentage": round(policy_count / len(labels) * 100.0, 2),
        "Brain Predictions": counts["brain"],
        "Muscle Predictions": counts["muscle artifact"],
        "Eye Blink Predictions": counts["eye blink"],
        "Heart Beat Predictions": counts["heart beat"],
        "Line Noise Predictions": counts["line noise"],
        "Channel Noise Predictions": counts["channel noise"],
        "Other Predictions": counts["other"],
        "Mean Argmax Probability": round(float(probabilities.mean()), 6),
        "Runtime (s)": round(elapsed, 4),
    }
    details = [
        {
            "Subject": subject_tag,
            "Component Index (within subject ICA only)": index,
            "ICLabel Prediction": label,
            "ICLabel Argmax Probability": round(float(probability), 6),
            "Artifact-Policy Prediction": label in ARTIFACT_POLICY_CLASSES,
        }
        for index, (label, probability) in enumerate(zip(labels, probabilities))
    ]
    return row, details


def plot_aggregate(summary: pd.DataFrame, output_path: Path) -> None:
    columns = [
        "Brain Predictions",
        "Muscle Predictions",
        "Eye Blink Predictions",
        "Heart Beat Predictions",
        "Line Noise Predictions",
        "Channel Noise Predictions",
        "Other Predictions",
    ]
    counts = summary[columns].sum()
    percentages = counts / counts.sum() * 100.0
    labels = [column.replace(" Predictions", "") for column in columns]
    colors = ["#27ae60", "#8e44ad", "#e74c3c", "#2980b9", "#e67e22", "#7f8c8d", "#95a5a6"]

    fig, axis = plt.subplots(figsize=(10, 6), dpi=200)
    axis.bar(np.arange(len(columns)), percentages, color=colors)
    axis.set_xticks(np.arange(len(columns)), labels, rotation=30, ha="right")
    axis.set_ylim(0, 100)
    axis.set_ylabel("Aggregate predicted-class proportion (%)")
    axis.set_title("DEAP ICLabel screening — predictions, not component ground truth")
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    for index, value in enumerate(percentages):
        axis.text(index, value + 1.2, f"{value:.1f}%", ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    validate_args(args)
    mne.set_log_level("ERROR")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    components: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    observed_input_shapes: dict[str, list[int]] = {}

    for subject_id in args.subjects:
        subject_tag = f"s{subject_id:02d}"
        print(f"Processing {subject_tag}")
        try:
            raw, trials_available, trials_used, observed_shape = load_subject_eeg(
                args.data_dir,
                subject_id,
                args.max_trials,
                args.crossfade_seconds,
            )
            observed_input_shapes[subject_tag] = list(observed_shape)
            summary, details = evaluate_subject(
                raw,
                subject_tag,
                trials_available,
                trials_used,
                args,
            )
            summaries.append(summary)
            components.extend(details)
        except Exception as exc:
            observed_shape = getattr(exc, "observed_shape", None)
            if observed_shape is not None:
                observed_input_shapes[subject_tag] = list(observed_shape)
            failures.append(
                {
                    "Subject": subject_tag,
                    "Error": f"{type(exc).__name__}: {exc}",
                }
            )

    summary_frame = pd.DataFrame(summaries)
    component_frame = pd.DataFrame(components)
    summary_path = args.output_dir / "deap_subject_screening_summary.csv"
    component_path = args.output_dir / "deap_component_predictions.csv"
    summary_frame.to_csv(summary_path, index=False)
    component_frame.to_csv(component_path, index=False)

    metadata = {
        "dataset": "DEAP preprocessed Python package; user-supplied licensed files",
        "subjects_requested": args.subjects,
        "expected_input_shape": list(EXPECTED_DEAP_SHAPE),
        "observed_input_shapes": observed_input_shapes,
        "trials": {
            "maximum_trials_per_subject_requested": args.max_trials,
            "note": "Available and used trial counts are reported separately per subject.",
        },
        "eeg_channels_supplied_to_iclabel": 32,
        "peripheral_channels_supplied_to_iclabel": 0,
        "sampling_rate_hz": SAMPLING_RATE_HZ,
        "passband_hz": [args.low_freq, args.high_freq],
        "reference": "common average",
        "ica_method": "Extended Infomax",
        "requested_ica_components": args.n_components,
        "random_seed": RANDOM_SEED,
        "trial_boundary_crossfade_seconds": args.crossfade_seconds,
        "automatic_component_removal_performed": False,
        "limitations": [
            "ICLabel outputs are model predictions, not component ground truth.",
            "No ECG or plethysmography reference is supplied to ICLabel.",
            "The DEAP package was preprocessed before this pipeline received it.",
            "The script does not automatically reconstruct or publish cleaned EEG.",
            "A high Heart Beat prediction proportion requires validation and is not proof of cardiac contamination.",
        ],
        "failures": failures,
    }
    (args.output_dir / "experiment_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    if not summary_frame.empty:
        plot_aggregate(summary_frame, args.output_dir / "deap_screening_distribution.png")

    print(f"Summary:    {summary_path.resolve()}")
    print(f"Components: {component_path.resolve()}")
    if failures:
        raise SystemExit(f"Screening completed with {len(failures)} failed subject(s).")


if __name__ == "__main__":
    main()
