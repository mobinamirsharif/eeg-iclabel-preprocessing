import os
import sys
import time
import json
import pickle
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import mne
from mne.preprocessing import ICA
from mne_icalabel import label_components

# ============================================================
# CONFIGURATION
# ============================================================

RANDOM_SEED = 42

# Keep this at 10 for a fair comparison with the previous run
N_COMPONENTS = 10

SAMPLING_RATE = 128.0
LOW_FREQ = 1.0

# DEAP is sampled at 128 Hz, so the Nyquist limit is 64 Hz.
# ICLabel was trained expecting a 1-100 Hz bandpass; we cannot
# reach 100 Hz here, so we push as close to Nyquist as safely
# possible instead of stopping at 45 Hz. This keeps more of the
# high-frequency content ICLabel relies on to separate muscle/
# line-noise/channel-noise components from heart-beat and brain.
HIGH_FREQ = 55.0

# Use a NEW output directory so the previous corrected results
# remain untouched for comparison
BASE_OUTPUT_DIR = "ICLabel_DEAP_Results_CORRECTED_V2"

DIR_CLEANED = os.path.join(BASE_OUTPUT_DIR, "cleaned_data")
DIR_FIGURES = os.path.join(BASE_OUTPUT_DIR, "figures")
DIR_REPORTS = os.path.join(BASE_OUTPUT_DIR, "iclabel_reports")
DIR_SUMMARY = os.path.join(BASE_OUTPUT_DIR, "summary")
DIR_BENCHMARK = os.path.join(BASE_OUTPUT_DIR, "benchmark")

for d in [
    DIR_CLEANED,
    DIR_FIGURES,
    DIR_REPORTS,
    DIR_SUMMARY,
    DIR_BENCHMARK
]:
    os.makedirs(d, exist_ok=True)


# ============================================================
# CORRECT DEAP 32-CHANNEL ORDER (unchanged from previous fix)
# ============================================================

DEAP_32_CHANNELS = [
    'Fp1', 'AF3', 'F3', 'F7',
    'FC5', 'FC1', 'C3', 'T7',
    'CP5', 'CP1', 'P3', 'P7',
    'PO3', 'O1', 'Oz', 'Pz',
    'Fp2', 'AF4', 'Fz', 'F4',
    'F8', 'FC6', 'FC2', 'Cz',
    'C4', 'T8', 'CP6', 'CP2',
    'P4', 'P8', 'PO4', 'O2'
]


# ============================================================
# ICLabel CLASSES
# ============================================================

ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other"
]

ARTIFACT_CLASSES = [
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise"
]

# Components excluded automatically get flagged, but we also want
# to see the raw confidence of every "heart beat" call so we can
# judge whether the model is genuinely confident or just picking
# the least-bad option (argmax among weak probabilities).
HEART_BEAT_PROBE_LOG = []


# ============================================================
# VALIDATE CHANNEL LIST
# ============================================================

print("\n" + "=" * 80)
print("DEAP CHANNEL ORDER VALIDATION")
print("=" * 80)
print(f"Number of channels: {len(DEAP_32_CHANNELS)}")

if len(DEAP_32_CHANNELS) != 32:
    print("ERROR: DEAP channel list does not contain exactly 32 channels.")
    sys.exit(1)

for idx, ch_name in enumerate(DEAP_32_CHANNELS, start=1):
    print(f"{idx:02d}: {ch_name}")

print("=" * 80)
print(f"Bandpass filter: {LOW_FREQ}-{HIGH_FREQ} Hz (Nyquist = {SAMPLING_RATE/2:.1f} Hz)")
print("Channel order loaded successfully.")
print("=" * 80)


# ============================================================
# DATASET PATH (Direct Local Search to Bypass 403 API Error)
# ============================================================

print("\nLocating DEAP dataset (checking local cache first)...")
local_cache_path = os.path.expanduser(r"~/.cache/kagglehub/datasets/manh123df/deap-dataset")
data_dir = None

if os.path.exists(local_cache_path):
    for root, dirs, files in os.walk(local_cache_path):
        if "s01.dat" in files:
            data_dir = root
            break

if not data_dir:
    for root, dirs, files in os.walk("."):
        if "s01.dat" in files:
            data_dir = root
            break

if not data_dir:
    try:
        import kagglehub
        dataset_root = kagglehub.dataset_download("manh123df/deap-dataset")
        for root, dirs, files in os.walk(dataset_root):
            if "s01.dat" in files:
                data_dir = root
                break
    except Exception as e:
        print(f"KaggleHub download skipped: {e}")

if not data_dir:
    print("ERROR: s01.dat not found in local cache or current directory.")
    sys.exit(1)

print(f"Dataset path located: {data_dir}")


# ============================================================
# MNE MONTAGE
# ============================================================

montage = mne.channels.make_standard_montage("standard_1020")


# ============================================================
# STORAGE
# ============================================================

global_subject_summaries = []
benchmark_records = []

total_class_counts = {cls_name: 0 for cls_name in ICLABEL_CLASSES}

total_batch_start_time = time.perf_counter()


# ============================================================
# PROCESS ALL 32 SUBJECTS
# ============================================================

for subject_idx in range(1, 33):

    sub_id_str = f"s{subject_idx:02d}"
    file_name = f"{sub_id_str}.dat"
    file_path = os.path.join(data_dir, file_name)

    if not os.path.exists(file_path):
        print(f"[{sub_id_str}] File not found, skipping.")
        continue

    print("\n" + "-" * 80)
    print(f"[{sub_id_str}] Processing pipeline started...")
    print("-" * 80)

    subject_start_time = time.perf_counter()

    try:
        # ------------------------------------------------
        # LOAD DEAP
        # ------------------------------------------------
        with open(file_path, "rb") as f:
            raw_payload = pickle.load(f, encoding="latin1")

        full_data_matrix = raw_payload["data"]
        total_trials = full_data_matrix.shape[0]

        eeg_channels_only = full_data_matrix[:, :32, :]

        n_trials_for_ica = min(5, total_trials)
        continuous_eeg = np.concatenate(
            [eeg_channels_only[t] for t in range(n_trials_for_ica)],
            axis=1
        )

        # ------------------------------------------------
        # BUILD RAW OBJECT
        # ------------------------------------------------
        info = mne.create_info(
            ch_names=DEAP_32_CHANNELS,
            sfreq=SAMPLING_RATE,
            ch_types="eeg"
        )

        raw_mne = mne.io.RawArray(continuous_eeg * 1e-6, info, verbose=False)
        raw_mne.set_montage(montage, on_missing="raise", verbose=False)

        # ------------------------------------------------
        # FILTER (now closer to Nyquist to match ICLabel's
        # expected 1-100 Hz training band as closely as the
        # 128 Hz sampling rate allows)
        # ------------------------------------------------
        raw_mne.filter(
            l_freq=LOW_FREQ,
            h_freq=HIGH_FREQ,
            fir_design="firwin",
            verbose=False
        )

        raw_mne.set_eeg_reference("average", projection=False, verbose=False)

        # ------------------------------------------------
        # ICA
        # ------------------------------------------------
        ica = ICA(
            n_components=N_COMPONENTS,
            method="infomax",
            fit_params=dict(extended=True),
            random_state=RANDOM_SEED
        )
        ica.fit(raw_mne, verbose=False)

        # ------------------------------------------------
        # ICLabel
        # ------------------------------------------------
        ic_classification = label_components(raw_mne, ica, method="iclabel")
        predicted_labels = ic_classification["labels"]
        probability_values = ic_classification["y_pred_proba"]

        component_reports = []
        excluded_component_indices = []
        subject_class_counts = {cls_name: 0 for cls_name in ICLABEL_CLASSES}

        for comp_idx, (assigned_label, prob_val) in enumerate(
            zip(predicted_labels, probability_values)
        ):
            prob_float = float(prob_val)

            if assigned_label in subject_class_counts:
                subject_class_counts[assigned_label] += 1
            if assigned_label in total_class_counts:
                total_class_counts[assigned_label] += 1

            # Log every heart-beat call's confidence for later review
            if assigned_label == "heart beat":
                HEART_BEAT_PROBE_LOG.append({
                    "subject_id": sub_id_str,
                    "component_index": int(comp_idx),
                    "probability": prob_float
                })

            is_excluded = assigned_label in ARTIFACT_CLASSES
            if is_excluded:
                excluded_component_indices.append(comp_idx)
                exclusion_reason = (
                    f"Classified as {assigned_label} with probability {prob_float:.4f}"
                )
            else:
                exclusion_reason = "Retained as brain/other signal"

            component_reports.append({
                "component_index": int(comp_idx),
                "predicted_class": str(assigned_label),
                "confidence_probability": prob_float,
                "excluded": bool(is_excluded),
                "exclusion_reason": exclusion_reason
            })

        print(f"\n[{sub_id_str}] ICLabel classification:")
        for cls_name in ICLABEL_CLASSES:
            print(f"    {cls_name:<20}: {subject_class_counts[cls_name]}")
        print(
            f"\n[{sub_id_str}] Excluded artifact ICs: "
            f"{len(excluded_component_indices)}/{N_COMPONENTS}"
        )

        # ------------------------------------------------
        # RECONSTRUCT CLEAN EEG
        # ------------------------------------------------
        raw_cleaned = raw_mne.copy()
        ica.exclude = excluded_component_indices
        ica.apply(raw_cleaned, verbose=False)

        cleaned_fif_filename = f"deap_{sub_id_str}_cleaned_eeg.fif"
        cleaned_fif_path = os.path.join(DIR_CLEANED, cleaned_fif_filename)
        raw_cleaned.save(cleaned_fif_path, overwrite=True, verbose=False)

        # ------------------------------------------------
        # RAW VS CLEANED FIGURE
        # ------------------------------------------------
        fig_path = os.path.join(DIR_FIGURES, f"{sub_id_str}_raw_vs_clean.png")

        display_duration_sec = 5.0
        n_display_samples = int(display_duration_sec * SAMPLING_RATE)
        time_axis = np.arange(n_display_samples) / SAMPLING_RATE

        raw_sample = raw_mne.get_data(picks=0, start=0, stop=n_display_samples)[0] * 1e6
        clean_sample = raw_cleaned.get_data(picks=0, start=0, stop=n_display_samples)[0] * 1e6

        plt.figure(figsize=(12, 5), dpi=300)
        plt.plot(time_axis, raw_sample, "r--", label="Raw EEG (With Artifacts)", alpha=0.75, linewidth=1.2)
        plt.plot(time_axis, clean_sample, "g-", label="Artifact-Reduced EEG (After ICLabel Removal)", alpha=0.9, linewidth=1.4)
        plt.title(
            f"DEAP Subject {sub_id_str.upper()} (Electrode Fp1) - Raw vs. Artifact-Reduced EEG (V2 Passband)",
            fontsize=11, fontweight="bold"
        )
        plt.xlabel("Time (seconds)", fontsize=10)
        plt.ylabel("Voltage Amplitude (uV)", fontsize=10)
        plt.legend(loc="upper right", fontsize=9)
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()
        plt.savefig(fig_path)
        plt.close()

        subject_elapsed_time = time.perf_counter() - subject_start_time

        # ------------------------------------------------
        # SUBJECT JSON REPORT
        # ------------------------------------------------
        subject_json_report = {
            "subject_id": sub_id_str,
            "total_trials_available": int(total_trials),
            "trials_used_for_ica": int(n_trials_for_ica),
            "sampling_rate_hz": SAMPLING_RATE,
            "eeg_channel_count": len(DEAP_32_CHANNELS),
            "channel_order": DEAP_32_CHANNELS,
            "channel_order_corrected": True,
            "bandpass_filter_hz": [LOW_FREQ, HIGH_FREQ],
            "referencing": "Common Average Reference (CAR)",
            "ica_method": "Extended Infomax",
            "total_ica_components": N_COMPONENTS,
            "excluded_components_count": len(excluded_component_indices),
            "excluded_components_percentage": float(
                round((len(excluded_component_indices) / N_COMPONENTS) * 100, 2)
            ),
            "excluded_component_indices": excluded_component_indices,
            "component_details": component_reports,
            "class_counts": subject_class_counts,
            "hardware": {
                "execution_device": "CPU",
                "processing_time_seconds": float(round(subject_elapsed_time, 4))
            },
            "output_files": {
                "cleaned_eeg_fif": cleaned_fif_path,
                "comparison_figure": fig_path
            }
        }

        json_report_path = os.path.join(DIR_REPORTS, f"{sub_id_str}_iclabel_report.json")
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(subject_json_report, f, indent=4)

        global_subject_summaries.append({
            "subject_id": sub_id_str,
            "status": "Success",
            "total_trials": total_trials,
            "ica_components": N_COMPONENTS,
            "excluded_components": len(excluded_component_indices),
            "excluded_percentage": float(
                round((len(excluded_component_indices) / N_COMPONENTS) * 100, 2)
            ),
            "brain_components": subject_class_counts["brain"],
            "muscle_components": subject_class_counts["muscle artifact"],
            "eye_components": subject_class_counts["eye blink"],
            "heart_components": subject_class_counts["heart beat"],
            "line_noise_components": subject_class_counts["line noise"],
            "channel_noise_components": subject_class_counts["channel noise"],
            "other_components": subject_class_counts["other"],
            "processing_time_sec": float(round(subject_elapsed_time, 4))
        })

        benchmark_records.append({
            "subject_id": sub_id_str,
            "processing_time_seconds": float(round(subject_elapsed_time, 4)),
            "device": "CPU"
        })

        print(f"\n[{sub_id_str}] Successfully processed in {subject_elapsed_time:.2f}s")

    except Exception as e:
        subject_elapsed_time = time.perf_counter() - subject_start_time
        print(f"[{sub_id_str}] ERROR: {str(e)}")

        global_subject_summaries.append({
            "subject_id": sub_id_str,
            "status": f"Failed: {str(e)}",
            "total_trials": 0,
            "ica_components": 0,
            "excluded_components": 0,
            "excluded_percentage": 0.0,
            "brain_components": 0,
            "muscle_components": 0,
            "eye_components": 0,
            "heart_components": 0,
            "line_noise_components": 0,
            "channel_noise_components": 0,
            "other_components": 0,
            "processing_time_sec": float(round(subject_elapsed_time, 4))
        })

        benchmark_records.append({
            "subject_id": sub_id_str,
            "processing_time_seconds": float(round(subject_elapsed_time, 4)),
            "device": "CPU (Failed)"
        })


# ============================================================
# TOTAL BATCH TIME
# ============================================================

total_batch_duration = time.perf_counter() - total_batch_start_time

df_summary = pd.DataFrame(global_subject_summaries)
df_summary.to_csv(os.path.join(DIR_SUMMARY, "deap_32_subjects_summary.csv"), index=False)

df_benchmark = pd.DataFrame(benchmark_records)
df_benchmark.to_csv(os.path.join(DIR_BENCHMARK, "processing_times.csv"), index=False)

df_heart_probe = pd.DataFrame(HEART_BEAT_PROBE_LOG)
if not df_heart_probe.empty:
    df_heart_probe.to_csv(
        os.path.join(DIR_SUMMARY, "heart_beat_confidence_probe.csv"),
        index=False
    )
    mean_conf = df_heart_probe["probability"].mean()
    low_conf_count = (df_heart_probe["probability"] < 0.5).sum()
    high_conf_count = (df_heart_probe["probability"] >= 0.8).sum()
else:
    mean_conf = 0.0
    low_conf_count = 0
    high_conf_count = 0

processing_times_successful = [
    s["processing_time_sec"] for s in global_subject_summaries if s["status"] == "Success"
]

total_ica_components = sum(s["ica_components"] for s in global_subject_summaries)
total_excluded_components = sum(s["excluded_components"] for s in global_subject_summaries)
aggregate_exclusion_rate = (
    total_excluded_components / max(1, total_ica_components)
) * 100

global_summary_json = {
    "experiment_metadata": {
        "dataset_name": "DEAP",
        "total_subjects_evaluated": len(global_subject_summaries),
        "successful_subjects_count": len(processing_times_successful),
        "failed_subjects_count": len(global_subject_summaries) - len(processing_times_successful),
        "total_trials_processed": int(sum(s["total_trials"] for s in global_subject_summaries)),
        "eeg_channels": 32,
        "channel_order": DEAP_32_CHANNELS,
        "channel_order_corrected": True,
        "sampling_rate_hz": SAMPLING_RATE,
        "passband_filter_hz": [LOW_FREQ, HIGH_FREQ],
        "ica_algorithm": "Extended Infomax",
        "ica_components_per_subject": N_COMPONENTS,
        "random_seed": RANDOM_SEED
    },
    "artifact_component_accounting": {
        "total_ica_components_extracted": int(total_ica_components),
        "total_excluded_components": int(total_excluded_components),
        "aggregate_exclusion_rate_percentage": float(round(aggregate_exclusion_rate, 2)),
        "total_brain_components": total_class_counts["brain"],
        "total_muscle_components": total_class_counts["muscle artifact"],
        "total_eye_components": total_class_counts["eye blink"],
        "total_heart_components": total_class_counts["heart beat"],
        "total_line_noise_components": total_class_counts["line noise"],
        "total_channel_noise_components": total_class_counts["channel noise"],
        "total_other_components": total_class_counts["other"]
    },
    "heart_beat_confidence_probe": {
        "mean_probability": float(round(mean_conf, 4)),
        "low_confidence_calls_below_0.5": int(low_conf_count),
        "high_confidence_calls_0.8_or_above": int(high_conf_count),
        "total_heart_beat_calls": int(len(HEART_BEAT_PROBE_LOG))
    },
    "hardware_benchmark_summary": {
        "execution_device": "CPU",
        "gpu_acceleration_utilized": False,
        "total_batch_time_seconds": float(round(total_batch_duration, 4)),
        "average_subject_processing_time_seconds": (
            float(round(np.mean(processing_times_successful), 4))
            if processing_times_successful else 0.0
        ),
        "minimum_subject_processing_time_seconds": (
            float(round(np.min(processing_times_successful), 4))
            if processing_times_successful else 0.0
        ),
        "maximum_subject_processing_time_seconds": (
            float(round(np.max(processing_times_successful), 4))
            if processing_times_successful else 0.0
        )
    },
    "per_subject_records": global_subject_summaries
}

with open(os.path.join(DIR_SUMMARY, "deap_32_subjects_summary.json"), "w", encoding="utf-8") as f:
    json.dump(global_summary_json, f, indent=4)

print("\n" + "=" * 80)
print("BATCH PROCESSING COMPLETED (CORRECTED CHANNELS + WIDER BANDPASS)")
print("=" * 80)
print(f"Total Batch Runtime: {total_batch_duration:.2f} seconds ({total_batch_duration/60:.2f} minutes)")
if processing_times_successful:
    print(f"Average Subject Processing Time: {np.mean(processing_times_successful):.2f} seconds")
print(f"Total ICA Components: {total_ica_components}")
print(f"Total Artifact Components Excluded: {total_excluded_components}")
print(f"Aggregate Exclusion Rate: {aggregate_exclusion_rate:.2f}%")

print("\nClass distribution:")
for cls_name in ICLABEL_CLASSES:
    print(f"  {cls_name:<20}: {total_class_counts[cls_name]}")

print(f"\nHeart-beat confidence probe:")
print(f"  Mean probability: {mean_conf:.4f}")
print(f"  Calls below 0.5 confidence: {low_conf_count}")
print(f"  Calls at/above 0.8 confidence: {high_conf_count}")
print(f"  Total heart-beat calls: {len(HEART_BEAT_PROBE_LOG)}")

print(f"\nBandpass filter used: {LOW_FREQ}-{HIGH_FREQ} Hz")
print(f"Output directory: {os.path.abspath(BASE_OUTPUT_DIR)}")
print("=" * 80)