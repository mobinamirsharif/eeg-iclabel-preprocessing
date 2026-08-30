"""Run the four-condition BCI preprocessing comparison for ICLabel.

The script compares class distributions at subject/condition level. It never
matches IC indices across independently fitted ICA decompositions because, for
example, IC 3 in one condition is not guaranteed to represent IC 3 in another.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

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
DEFAULT_OUTPUT_DIR = FINAL_ROOT / "results" / "controlled_experiment"
RANDOM_SEED = 42
DEFAULT_COMPONENTS = 15

ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other",
]


@dataclass(frozen=True)
class Condition:
    code: str
    sampling_rate_hz: float
    low_freq_hz: float
    high_freq_hz: float
    purpose: str


CONDITIONS = [
    Condition("A_250Hz_1-100Hz", 250.0, 1.0, 100.0, "BCI/ICLabel-oriented baseline"),
    Condition("B_250Hz_4-45Hz", 250.0, 4.0, 45.0, "DEAP-like passband at original sampling rate"),
    Condition("C_128Hz_1-63Hz", 128.0, 1.0, 63.0, "128 Hz with a Nyquist-limited passband"),
    Condition("D_128Hz_4-45Hz", 128.0, 4.0, 45.0, "DEAP-like sampling rate and passband"),
]


def safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or "unnamed"


def default_bnci_cache() -> Path:
    """Return the configured MNE/MOABB dataset cache without changing it."""
    configured = (
        mne.get_config("MNE_DATASETS_BNCI_PATH")
        or mne.get_config("MNE_DATA")
        or str(Path.home() / "mne_data")
    )
    return Path(configured)


def configure_bnci_cache(cache: Path) -> Path:
    """Expose a Windows-safe BNCI cache path to MOABB 1.5.

    MOABB 1.5 sanitizes the colon in a full Windows drive path and can turn
    ``C:\\...`` into the relative path ``C-\\...``.  A root-relative path has
    no colon and still resolves to the same location on the current drive.
    """
    resolved = cache.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"BNCI data cache does not exist: {resolved}")

    moabb_path = str(resolved)
    if os.name == "nt" and resolved.drive:
        current_drive = Path.cwd().resolve().drive
        if current_drive.casefold() != resolved.drive.casefold():
            raise RuntimeError(
                "On Windows with MOABB 1.5, run this script from the same drive "
                f"as the data cache ({resolved.drive})."
            )
        _, tail = os.path.splitdrive(moabb_path)
        moabb_path = "\\" + tail.lstrip("\\/")

    os.environ["MNE_DATASETS_BNCI_PATH"] = moabb_path
    return resolved


def portable_path(path: Path) -> str:
    """Represent paths under the user's home without publishing a username."""
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(Path.home().resolve())
    except ValueError:
        return str(resolved)
    return (Path("~") / relative).as_posix()


def load_selected_recording(
    dataset: BNCI2014_001,
    subject_id: int,
    session_index: int,
    run_index: int,
) -> tuple[str, str, mne.io.BaseRaw]:
    subject_data = dataset.get_data(subjects=[subject_id])[subject_id]
    session_keys = list(subject_data.keys())
    try:
        session_key = session_keys[session_index]
        run_keys = list(subject_data[session_key].keys())
        run_key = run_keys[run_index]
    except IndexError as exc:
        raise IndexError(
            f"Invalid session/run index for subject {subject_id}: "
            f"session_index={session_index}, run_index={run_index}"
        ) from exc
    return str(session_key), str(run_key), subject_data[session_key][run_key].copy()


def standardize_eeg(raw: mne.io.BaseRaw) -> mne.io.BaseRaw:
    raw.load_data()
    raw.pick(picks=["eeg"])
    raw.rename_channels(
        {
            channel: channel.replace("EEG-", "").replace("EEG", "").strip()
            for channel in raw.ch_names
        }
    )
    raw.set_montage(
        mne.channels.make_standard_montage("standard_1020"),
        match_case=False,
        on_missing="raise",
    )
    return raw


def apply_condition(raw: mne.io.BaseRaw, condition: Condition) -> mne.io.BaseRaw:
    conditioned = raw.copy()
    current_rate = float(conditioned.info["sfreq"])
    if not np.isclose(current_rate, condition.sampling_rate_hz):
        conditioned.resample(condition.sampling_rate_hz, npad="auto", verbose=False)
    conditioned.filter(
        l_freq=condition.low_freq_hz,
        h_freq=condition.high_freq_hz,
        fir_design="firwin",
        verbose=False,
    )
    conditioned.set_eeg_reference("average", projection=False, verbose=False)
    return conditioned


def evaluate_condition(
    raw: mne.io.BaseRaw,
    subject_tag: str,
    session_key: str,
    run_key: str,
    condition: Condition,
    n_components: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    start_time = time.perf_counter()
    conditioned = apply_condition(raw, condition)
    estimated_rank = int(mne.compute_rank(conditioned, rank=None, verbose=False)["eeg"])
    components_used = min(n_components, estimated_rank)
    if components_used < 2:
        raise RuntimeError(
            f"Insufficient EEG rank for {subject_tag} / {condition.code}: {estimated_rank}"
        )

    ica = ICA(
        n_components=components_used,
        method="infomax",
        fit_params={"extended": True},
        random_state=RANDOM_SEED,
        max_iter="auto",
    )
    ica.fit(conditioned, verbose=False)
    prediction = label_components(conditioned, ica, method="iclabel")
    labels = list(prediction["labels"])
    probabilities = np.asarray(prediction["y_pred_proba"], dtype=float)
    counts = {class_name: labels.count(class_name) for class_name in ICLABEL_CLASSES}
    if sum(counts.values()) != len(labels):
        raise RuntimeError("Seven-class counts do not reconcile to the ICA total")

    elapsed = time.perf_counter() - start_time
    row: dict[str, object] = {
        "Subject": subject_tag,
        "Session": session_key,
        "Run": run_key,
        "Condition": condition.code,
        "Sampling Rate (Hz)": condition.sampling_rate_hz,
        "Low Cutoff (Hz)": condition.low_freq_hz,
        "High Cutoff (Hz)": condition.high_freq_hz,
        "EEG Rank": estimated_rank,
        "Total ICs": len(labels),
        "Brain": counts["brain"],
        "Muscle": counts["muscle artifact"],
        "Eye Blink": counts["eye blink"],
        "Heart Beat": counts["heart beat"],
        "Line Noise": counts["line noise"],
        "Channel Noise": counts["channel noise"],
        "Other": counts["other"],
        "Mean Confidence": round(float(np.mean(probabilities)), 6),
        "Median Confidence": round(float(np.median(probabilities)), 6),
        "Runtime (s)": round(elapsed, 3),
    }
    for class_column in [
        "Brain",
        "Muscle",
        "Eye Blink",
        "Heart Beat",
        "Line Noise",
        "Channel Noise",
        "Other",
    ]:
        row[f"{class_column} Proportion"] = round(
            float(row[class_column]) / len(labels), 6
        )

    details = [
        {
            "Subject": subject_tag,
            "Session": session_key,
            "Run": run_key,
            "Condition": condition.code,
            "Component Index (within condition only)": index,
            "Predicted Label": label,
            "Predicted Class Probability": round(float(probability), 6),
        }
        for index, (label, probability) in enumerate(zip(labels, probabilities))
    ]
    return row, details


def plot_aggregate_distributions(results: pd.DataFrame, output_path: Path) -> None:
    class_columns = [
        "Brain",
        "Muscle",
        "Eye Blink",
        "Heart Beat",
        "Line Noise",
        "Channel Noise",
        "Other",
    ]
    colors = ["#27ae60", "#8e44ad", "#e74c3c", "#2980b9", "#e67e22", "#7f8c8d", "#95a5a6"]
    grouped = results.groupby("Condition", sort=False)[class_columns].sum()
    grouped = grouped.reindex([condition.code for condition in CONDITIONS])
    proportions = grouped.div(grouped.sum(axis=1), axis=0) * 100.0

    fig, axis = plt.subplots(figsize=(12, 6), dpi=200)
    bottoms = np.zeros(len(proportions))
    x = np.arange(len(proportions))
    for column, color in zip(class_columns, colors):
        values = proportions[column].to_numpy(dtype=float)
        axis.bar(x, values, bottom=bottoms, label=column, color=color, edgecolor="black", linewidth=0.4)
        bottoms += values
    axis.set_xticks(x, proportions.index, rotation=10)
    axis.set_ylabel("Aggregate predicted-class proportion (%)")
    axis.set_title("Four-condition ICLabel comparison (subject-level aggregates)")
    axis.set_ylim(0, 100)
    axis.legend(ncols=4, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    fig.text(0.5, 0.01, "ICA components are not matched by index across conditions.", ha="center", fontsize=9)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subjects", nargs="+", type=int, default=list(range(1, 10)))
    parser.add_argument("--session-index", type=int, default=0)
    parser.add_argument("--run-index", type=int, default=0)
    parser.add_argument("--n-components", type=int, default=DEFAULT_COMPONENTS)
    parser.add_argument(
        "--data-cache",
        type=Path,
        default=default_bnci_cache(),
        help="MNE/MOABB cache containing MNE-bnci-data (default: configured MNE cache)",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mne.set_log_level("ERROR")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_cache = configure_bnci_cache(args.data_cache)
    print(f"BNCI data cache: {data_cache}")
    dataset = BNCI2014_001()
    result_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for subject_id in args.subjects:
        subject_tag = f"sub-{subject_id:02d}"
        session_key, run_key, raw = load_selected_recording(
            dataset, subject_id, args.session_index, args.run_index
        )
        base_raw = standardize_eeg(raw)
        for condition in CONDITIONS:
            print(f"Processing {subject_tag} / {condition.code}")
            try:
                result, details = evaluate_condition(
                    base_raw,
                    subject_tag,
                    session_key,
                    run_key,
                    condition,
                    args.n_components,
                )
                result_rows.append(result)
                component_rows.extend(details)
            except Exception as exc:  # Preserve partial results and expose the failure.
                failures.append(
                    {
                        "Subject": subject_tag,
                        "Session": session_key,
                        "Run": run_key,
                        "Condition": condition.code,
                        "Error": f"{type(exc).__name__}: {exc}",
                    }
                )

    results = pd.DataFrame(result_rows)
    components = pd.DataFrame(component_rows)
    results_path = args.output_dir / "condition_summary.csv"
    components_path = args.output_dir / "component_predictions.csv"
    results.to_csv(results_path, index=False)
    components.to_csv(components_path, index=False)

    metadata = {
        "dataset": "BCI Competition IV Dataset 2a / BNCI2014_001",
        "data_cache": portable_path(data_cache),
        "subjects_requested": args.subjects,
        "recording_selection": {
            "session_index": args.session_index,
            "run_index": args.run_index,
            "note": "The same selected recording is reused across all four conditions for each subject.",
        },
        "random_seed": RANDOM_SEED,
        "ica_method": "extended infomax",
        "requested_ica_components": args.n_components,
        "conditions": [asdict(condition) for condition in CONDITIONS],
        "valid_pairwise_interpretations": {
            "A_vs_B": "passband/preprocessing change at 250 Hz",
            "B_vs_D": "sampling-rate change with a shared 4-45 Hz passband",
            "C_vs_D": "passband change at 128 Hz",
            "A_vs_C": "descriptive only; sampling rate and feasible upper bandwidth differ",
        },
        "limitations": [
            "ICLabel outputs are model predictions, not component ground truth.",
            "ICA is refit per condition, so component indices are not paired across conditions.",
            "The source BCI recordings were acquired with their original hardware filters and notch filtering.",
            "This comparison cannot by itself establish a universal causal sampling-rate requirement for ICLabel.",
        ],
        "failures": failures,
    }
    (args.output_dir / "experiment_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    if not results.empty:
        plot_aggregate_distributions(
            results, args.output_dir / "aggregate_condition_distribution.png"
        )
    print(f"Summary:    {results_path.resolve()}")
    print(f"Components: {components_path.resolve()}")
    if failures:
        raise SystemExit(f"Experiment completed with {len(failures)} failed condition(s).")


if __name__ == "__main__":
    main()
