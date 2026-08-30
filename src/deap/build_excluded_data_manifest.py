"""Fingerprint historical DEAP artifacts intentionally excluded from Git.

The manifest contains only collection-relative paths, byte sizes, hashes, and
exclusion reasons. It does not copy licensed or participant-level signal data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = PROJECT_ROOT.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "archive" / "EXCLUDED_DATA_MANIFEST.csv"

COLLECTIONS = [
    "ICLabel_DEAP_Results",
    "ICLabel_DEAP_Results_CORRECTED",
    "ICLabel_DEAP_Results_CORRECTED_V2",
    "ICLabel_DEAP_Results_CORRECTED_V3",
    "ICLabel_DEAP_Results_FINAL",
]

EXCLUDED_DIRECTORIES = {
    "cleaned_data": "reconstructed participant-level EEG (FIF)",
    "figures": "participant-level raw-versus-reconstructed signal figure",
    "heartbeat_topographies": "participant-derived IC topography/PSD figure",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for collection in COLLECTIONS:
        collection_root = args.source_root / collection
        if not collection_root.is_dir():
            raise FileNotFoundError(f"Historical collection not found: {collection_root}")
        for directory, reason in EXCLUDED_DIRECTORIES.items():
            source_directory = collection_root / directory
            if not source_directory.is_dir():
                continue
            for path in sorted(source_directory.rglob("*")):
                if not path.is_file():
                    continue
                rows.append(
                    {
                        "source_collection": collection,
                        "relative_path": path.relative_to(collection_root).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                        "exclusion_reason": reason,
                    }
                )

    archive_path = args.source_root / "ICLabel_DEAP_Results.rar"
    if archive_path.is_file():
        rows.append(
            {
                "source_collection": "project root",
                "relative_path": archive_path.name,
                "bytes": archive_path.stat().st_size,
                "sha256": sha256(archive_path),
                "exclusion_reason": "compressed duplicate containing participant-level derived signal artifacts",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "source_collection",
                "relative_path",
                "bytes",
                "sha256",
                "exclusion_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Excluded artifacts fingerprinted: {len(rows)}")
    print(f"Manifest: {args.output.resolve()}")


if __name__ == "__main__":
    main()
