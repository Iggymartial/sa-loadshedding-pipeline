"""
transform.py
Week 5 slice of the pipeline: read raw JSON extracts, apply data quality
checks with pandas, and write cleaned, validated records to a processed
Parquet file for the loader to pick up.

Design decision: validation happens BEFORE data reaches MySQL, not after.
Bad data should be caught and quarantined at this stage, not allowed into
the database and cleaned up later. Records that fail a check are still
written to the processed file (with a note on what failed) so nothing is
silently lost - but they are excluded from what the loader inserts into
stage_readings.

Why Parquet instead of CSV for the processed output: it's a columnar,
typed format (Week 2 material) - it preserves the fact that `stage` is
an integer and `stage_updated` is a real datetime, rather than everything
becoming a string the way CSV does. That avoids re-parsing types on read.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
QUALITY_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "quality_log.csv"

# Eskom's published load shedding stages run from 0 (no load shedding) to
# 8 (the highest stage implemented at time of writing). A value outside
# this range is more likely a data problem (a typo, a new unpublicised
# stage, a parsing bug) than something to trust blindly.
VALID_STAGE_RANGE = range(0, 9)

FILENAME_TIMESTAMP_RE = re.compile(r"_(\d{8}T\d{6}Z)\.json$")


def parse_recorded_at(filename: str) -> datetime:
    """Extracts the extraction timestamp from the filename itself (see extract.py for why)."""
    match = FILENAME_TIMESTAMP_RE.search(filename)
    if not match:
        raise ValueError(f"Filename does not match expected pattern: {filename}")
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def raw_to_rows(filepath: Path) -> list[dict]:
    """Flattens one raw JSON file's status dict into one row per source."""
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    recorded_at = parse_recorded_at(filepath.name)
    status = payload.get("status", {})

    rows = []
    for code, details in status.items():
        stage_updated_utc = None
        stage_updated_raw = details.get("stage_updated")
        if stage_updated_raw:
            stage_updated_utc = (
                datetime.fromisoformat(stage_updated_raw)
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )

        rows.append({
            "source_code": code,
            "source_name": details.get("name", code),
            "stage": details.get("stage"),
            "stage_updated": stage_updated_utc,
            "recorded_at": recorded_at.replace(tzinfo=None),
            "raw_file": filepath.name,
        })
    return rows


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds two columns: `valid` (bool) and `validation_notes` (str).
    Checks map to standard data quality dimensions (Week 6):

    - completeness: required fields must not be null
    - validity: stage must be a whole number in the expected range
    - consistency: stage_updated cannot be later than recorded_at -
      that would mean the API reported an update from our perspective
      hasn't happened yet, which signals a clock or parsing problem
    - uniqueness: no duplicate source within the same extraction run
    """
    df = df.reset_index(drop=True)
    notes = [[] for _ in range(len(df))]

    for col in ["source_code", "stage", "stage_updated", "recorded_at"]:
        for i in df.index[df[col].isna()]:
            notes[i].append(f"missing required field: {col}")

    def stage_is_valid(value):
        try:
            return int(value) in VALID_STAGE_RANGE
        except (TypeError, ValueError):
            return False

    invalid_stage = ~df["stage"].apply(stage_is_valid)
    for i in df.index[invalid_stage]:
        notes[i].append(f"stage out of expected range 0-8: {df.at[i, 'stage']!r}")

    both_present = df["stage_updated"].notna() & df["recorded_at"].notna()
    future_update = both_present & (df["stage_updated"] > df["recorded_at"])
    for i in df.index[future_update]:
        notes[i].append("stage_updated is after recorded_at")

    dup_mask = df.duplicated(subset=["source_code", "recorded_at"], keep="first")
    for i in df.index[dup_mask]:
        notes[i].append("duplicate source within same extraction run")

    df["validation_notes"] = ["; ".join(n) for n in notes]
    df["valid"] = df["validation_notes"] == ""
    return df


def append_quality_log(df: pd.DataFrame):
    """Appends only FAILED rows to a running log, so issues accumulate visibly over time."""
    failed = df[~df["valid"]]
    if failed.empty:
        return

    failed = failed.copy()
    failed["logged_at"] = datetime.now(timezone.utc).replace(microsecond=0)

    QUALITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not QUALITY_LOG_PATH.exists()
    failed.to_csv(QUALITY_LOG_PATH, mode="a", index=False, header=write_header)


def main() -> int:
    if not RAW_DATA_DIR.exists():
        print(f"Raw data directory not found: {RAW_DATA_DIR}", file=sys.stderr)
        return 1

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(RAW_DATA_DIR.glob("national_status_*.json"))
    if not raw_files:
        print("No raw files found to transform.")
        return 0

    processed_count = 0
    skipped_count = 0

    for filepath in raw_files:
        processed_path = PROCESSED_DATA_DIR / (filepath.stem + ".parquet")
        if processed_path.exists():
            skipped_count += 1
            continue

        df = pd.DataFrame(raw_to_rows(filepath))
        df = validate(df)
        df.to_parquet(processed_path, index=False)
        append_quality_log(df)

        valid_count = int(df["valid"].sum())
        invalid_count = len(df) - valid_count
        print(f"Processed {filepath.name}: {valid_count} valid, {invalid_count} flagged -> {processed_path.name}")
        processed_count += 1

    print(f"Done. Files processed: {processed_count}, already processed (skipped): {skipped_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
