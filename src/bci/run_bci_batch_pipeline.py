"""Run a reproducible ICLabel evaluation on BCI Competition IV Dataset 2a.

By default, the script evaluates the first available session and first available
run for each of the nine subjects. That scope reproduces the design of the
existing project; it does not claim to cover every recording in the dataset.
Use ``--all-recordings`` to evaluate all available session/run combinations.

The default workflow reports ICLabel predictions without reconstructing EEG or
excluding components. Reconstruction is available only through the explicit
``--apply-exclusions`` option. ICLabel predictions and policy candidates are not
manually validated component ground truth.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Iterator

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd
from mne.preprocessing import ICA
from mne_icalabel import label_components
from moabb.datasets import BNCI2014_001


FINAL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = FINAL_ROOT / "results" / "bci_evaluation"
RANDOM_SEED = 42
N_COMPONENTS = 15
LOW_FREQ = 1.0
HIGH_FREQ = 100.0
DISPLAY_SECONDS = 5.0

ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other",
]
ARTIFACT_CLASSES = [
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
]


def safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or "unnamed"


def iter_recordings(
    dataset: BNCI2014_001,
    subject_id: int,
    all_recordings: bool,
    session_index: int,
    run_index: int,
) -> Iterator[tuple[str, str, mne.io.BaseRaw]]:
    subject_data = dataset.get_data(subjects=[subject_id])[subject_id]
    session_keys = list(subject_data.keys())
    if not session_keys:
        raise RuntimeError(f"No sessions returned for subject {subject_id}")

    if all_recordings:
        for session_key in session_keys:
            for run_key, raw in subject_data[session_key].items():
                yield str(session_key), str(run_key), raw.copy()
        return

    try:
        session_key = session_keys[session_index]
        run_keys = list(subject_data[session_key].keys())
        run_key = run_keys[run_index]
    except IndexError as exc:
        raise IndexError(
            f"Invalid session/run index for subject {subject_id}: "
            f"session_index={session_index}, run_index={run_index}"
        ) from exc
    yield str(session_key), str(run_key), subject_data[session_key][run_key].copy()


def prepare_raw(raw: mne.io.BaseRaw) -> mne.io.BaseRaw:
    raw.load_data()
    raw.pick(picks=["eeg"])
    rename_map = {
        channel: channel.replace("EEG-", "").replace("EEG", "").strip()
        for channel in raw.ch_names
    }
    raw.rename_channels(rename_map)
    montage = mne.channels.make_standard_montage("standard_1020")
    raw.set_montage(montage, match_case=False, on_missing="raise")
    raw.filter(l_freq=LOW_FREQ, h_freq=HIGH_FREQ, fir_design="firwin", verbose=False)
    raw.set_eeg_reference("average", projection=False, verbose=False)
    return raw


def create_output_dirs(
    output_root: Path, include_reconstructed_data: bool
) -> dict[str, Path]:
    directories = {
        "figures": output_root / "figures",
        "reports": output_root / "iclabel_reports",
        "summary": output_root / "summary",
        "benchmark": output_root / "benchmark",
    }
    if include_reconstructed_data:
        directories["filtered"] = output_root / "iclabel_filtered_data"
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def evaluate_recording(
    raw: mne.io.BaseRaw,
    subject_tag: str,
    session_key: str,
    run_key: str,
    output_dirs: dict[str, Path],
    artifact_threshold: float,
    apply_exclusions: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    start_time = time.perf_counter()
    raw = prepare_raw(raw)
    sampling_rate = float(raw.info["sfreq"])

    ica = ICA(
        n_components=N_COMPONENTS,
        method="infomax",
        fit_params={"extended": True},
        random_state=RANDOM_SEED,
        max_iter="auto",
    )
    ica.fit(raw, verbose=False)
    result = label_components(raw, ica, method="iclabel")
    labels = list(result["labels"])
    probabilities = np.asarray(result["y_pred_proba"], dtype=float)
    total_components = len(labels)

    class_distribution = {class_name: 0 for class_name in ICLABEL_CLASSES}
    policy_candidate_indices: list[int] = []
    component_details: list[dict[str, object]] = []
    for index, (label, probability) in enumerate(zip(labels, probabilities)):
        if label not in class_distribution:
            raise ValueError(f"Unexpected ICLabel class: {label}")
        class_distribution[label] += 1
        policy_candidate = (
            label in ARTIFACT_CLASSES and probability >= artifact_threshold
        )
        if policy_candidate:
            policy_candidate_indices.append(index)
        component_details.append(
            {
                "component_index": index,
                "predicted_label": label,
                "predicted_class_probability": round(float(probability), 6),
                "artifact_policy_candidate": policy_candidate,
                "excluded_from_reconstruction": (
                    apply_exclusions and policy_candidate
                ),
            }
        )

    if sum(class_distribution.values()) != total_components:
        raise RuntimeError("Seven-class counts do not reconcile to the ICA total")

    recording_tag = "__".join(
        [subject_tag, safe_name(session_key), safe_name(run_key)]
    )

    # Probability plot.
    probability_path = output_dirs["figures"] / f"{recording_tag}_probabilities.png"
    fig, axis = plt.subplots(figsize=(11, 4.5), dpi=200)
    candidate_set = set(policy_candidate_indices)
    colors = [
        "#d9534f" if index in candidate_set else "#5cb85c"
        for index in range(total_components)
    ]
    bars = axis.bar(range(total_components), probabilities * 100.0, color=colors, edgecolor="#222222", alpha=0.85)
    for bar, label, probability in zip(bars, labels, probabilities):
        axis.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 1.0,
            f"{label}\n{probability * 100.0:.1f}%",
            ha="center",
            va="bottom",
            fontsize=6.5,
        )
    axis.set_title(f"ICLabel model predictions: {subject_tag}, session={session_key}, run={run_key}")
    axis.set_xlabel("Independent-component index")
    axis.set_ylabel("Predicted-class probability (%)")
    axis.set_ylim(0, 120)
    axis.set_xticks(range(total_components), [f"IC {index:02d}" for index in range(total_components)], fontsize=8)
    axis.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(probability_path, dpi=300)
    plt.close(fig)

    applied_indices = policy_candidate_indices if apply_exclusions else []
    if apply_exclusions:
        reconstructed = raw.copy()
        ica.apply(reconstructed, exclude=applied_indices, verbose=False)
        reconstructed.save(
            output_dirs["filtered"]
            / f"{recording_tag}_iclabel_filtered_raw.fif",
            overwrite=True,
            verbose=False,
        )

        # The comparison starts from filtered/CAR data, so avoid calling it raw.
        waveform_path = (
            output_dirs["figures"] / f"{recording_tag}_pre_vs_post_ica.png"
        )
        sample_count = min(int(DISPLAY_SECONDS * sampling_rate), raw.n_times)
        time_axis = np.arange(sample_count) / sampling_rate
        channel = "Cz" if "Cz" in raw.ch_names else raw.ch_names[0]
        before = raw.get_data(picks=[channel], start=0, stop=sample_count)[0] * 1e6
        after = (
            reconstructed.get_data(picks=[channel], start=0, stop=sample_count)[0]
            * 1e6
        )
        fig, axis = plt.subplots(figsize=(12, 4.5), dpi=200)
        axis.plot(
            time_axis,
            before,
            color="#d9534f",
            linestyle="--",
            alpha=0.75,
            linewidth=1.1,
            label="Filtered/CAR signal before ICA exclusion",
        )
        axis.plot(
            time_axis,
            after,
            color="#2e7d32",
            alpha=0.95,
            linewidth=1.3,
            label="ICLabel-policy reconstruction",
        )
        axis.set_title(f"Pre/post ICA-policy comparison: {channel}, {recording_tag}")
        axis.set_xlabel("Time (seconds)")
        axis.set_ylabel("Amplitude (uV)")
        axis.legend(loc="upper right")
        axis.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()
        fig.savefig(waveform_path, dpi=300)
        plt.close(fig)

    elapsed = time.perf_counter() - start_time

    report = {
        "subject_id": subject_tag,
        "selected_session": session_key,
        "selected_run": run_key,
        "recording_scope": "one explicitly recorded session/run",
        "sampling_rate_hz": sampling_rate,
        "nyquist_hz": sampling_rate / 2.0,
        "channels_count": len(raw.ch_names),
        "bandpass_hz": [LOW_FREQ, HIGH_FREQ],
        "reference": "common average reference",
        "ica_method": "extended infomax",
        "random_seed": RANDOM_SEED,
        "total_components": total_components,
        "artifact_policy": {
            "artifact_classes": ARTIFACT_CLASSES,
            "minimum_predicted_class_probability": artifact_threshold,
            "automatic_reconstruction_applied": apply_exclusions,
            "note": (
                "ICLabel predictions and policy candidates are not manually "
                "verified component ground truth."
            ),
        },
        "artifact_policy_candidate_count": len(policy_candidate_indices),
        "artifact_policy_candidate_indices": policy_candidate_indices,
        "excluded_components_count": len(applied_indices),
        "excluded_indices": applied_indices,
        "class_distribution": class_distribution,
        "mean_predicted_class_probability": round(float(np.mean(probabilities)), 6),
        "median_predicted_class_probability": round(float(np.median(probabilities)), 6),
        "execution_time_seconds": round(elapsed, 3),
        "processing_device": "system default (no explicit GPU selection)",
        "components": component_details,
    }
    (output_dirs["reports"] / f"{recording_tag}_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    summary = {
        "Subject": subject_tag,
        "Session": session_key,
        "Run": run_key,
        "Fs (Hz)": sampling_rate,
        "Nyquist (Hz)": sampling_rate / 2.0,
        "Channels": len(raw.ch_names),
        "Total ICs": total_components,
        "Artifact-Policy Candidates": len(policy_candidate_indices),
        "Components Excluded From Reconstruction": len(applied_indices),
        "Reconstruction Applied": apply_exclusions,
        "Brain": class_distribution["brain"],
        "Muscle": class_distribution["muscle artifact"],
        "Eye Blink": class_distribution["eye blink"],
        "Heart Beat": class_distribution["heart beat"],
        "Line Noise": class_distribution["line noise"],
        "Channel Noise": class_distribution["channel noise"],
        "Other": class_distribution["other"],
        "Mean Confidence": round(float(np.mean(probabilities)), 6),
        "Median Confidence": round(float(np.median(probabilities)), 6),
        "Runtime (s)": round(elapsed, 3),
        "Processing Device": "system default (no explicit GPU selection)",
    }
    benchmark = {
        "subject": subject_tag,
        "session": session_key,
        "run": run_key,
        "device": "system default (no explicit GPU selection)",
        "processing_time_seconds": round(elapsed, 3),
    }
    return summary, benchmark


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subjects", nargs="+", type=int, default=list(range(1, 10)))
    parser.add_argument("--session-index", type=int, default=0)
    parser.add_argument("--run-index", type=int, default=0)
    parser.add_argument("--all-recordings", action="store_true")
    parser.add_argument(
        "--apply-exclusions",
        action="store_true",
        help=(
            "Explicitly reconstruct EEG after excluding artifact-policy "
            "candidates. Disabled by default."
        ),
    )
    parser.add_argument(
        "--artifact-threshold",
        type=float,
        default=0.0,
        help=(
            "Minimum predicted-class probability for an artifact-policy "
            "candidate. With --apply-exclusions, 0 reproduces the archived "
            "argmax exclusion behavior."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if not 0.0 <= args.artifact_threshold <= 1.0:
        parser.error("--artifact-threshold must be between 0 and 1")
    return args


def main() -> None:
    args = parse_args()
    mne.set_log_level("ERROR")
    output_dirs = create_output_dirs(
        args.output_dir, include_reconstructed_data=args.apply_exclusions
    )
    dataset = BNCI2014_001()
    summaries: list[dict[str, object]] = []
    benchmarks: list[dict[str, object]] = []

    for subject_id in args.subjects:
        subject_tag = f"sub-{subject_id:02d}"
        for session_key, run_key, raw in iter_recordings(
            dataset,
            subject_id,
            args.all_recordings,
            args.session_index,
            args.run_index,
        ):
            print(f"Processing {subject_tag}: session={session_key}, run={run_key}")
            summary, benchmark = evaluate_recording(
                raw,
                subject_tag,
                session_key,
                run_key,
                output_dirs,
                args.artifact_threshold,
                args.apply_exclusions,
            )
            summaries.append(summary)
            benchmarks.append(benchmark)

    summary_df = pd.DataFrame(summaries)
    benchmark_df = pd.DataFrame(benchmarks)
    summary_df.to_csv(output_dirs["summary"] / "cohort_iclabel_summary.csv", index=False)
    benchmark_df.to_csv(output_dirs["benchmark"] / "benchmark_times.csv", index=False)
    (output_dirs["summary"] / "cohort_iclabel_summary.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )
    print(summary_df.to_string(index=False))
    print(f"Outputs: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
