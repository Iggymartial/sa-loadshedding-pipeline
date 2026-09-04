"""
load.py
Week 3 slice of the pipeline: read raw JSON extracts from data/raw/ and
load them into MySQL using the normalised schema in db/schema.sql.

Design decision: idempotent by design. Before inserting, this checks
whether a raw file has already been loaded (tracked via the raw_file
column on stage_readings) and skips it if so. This means it's safe to
re-run this script - important once it's wired into a scheduler that
might retry a run, or if you manually run it twice by mistake.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "pipeline_user"),
    "password": os.getenv("MYSQL_PASSWORD", "pipeline_password"),
    "database": os.getenv("MYSQL_DATABASE", "loadshedding"),
}

# Matches filenames produced by extract.py, e.g.
# national_status_20260904T140501Z.json
FILENAME_TIMESTAMP_RE = re.compile(r"_(\d{8}T\d{6}Z)\.json$")


def parse_recorded_at(filename: str) -> datetime:
    """
    Extracts the extraction timestamp from the raw filename itself,
    rather than trusting the file's modification time (which changes
    if the file is copied, moved, or checked out from git fresh on a
    different machine - the filename is the one source of truth that
    travels with the data).
    """
    match = FILENAME_TIMESTAMP_RE.search(filename)
    if not match:
        raise ValueError(f"Filename does not match expected pattern: {filename}")
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def get_or_create_source(cursor, code: str, display_name: str) -> int:
    """
    Looks up a source by its code (e.g. 'eskom'). Creates it if it
    doesn't exist yet. This makes the loader resilient to the API
    adding new municipalities later, without needing a schema change
    or a code deploy to handle them.
    """
    cursor.execute("SELECT id FROM sources WHERE code = %s", (code,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO sources (code, display_name) VALUES (%s, %s)",
        (code, display_name),
    )
    return cursor.lastrowid


def already_loaded(cursor, raw_file: str) -> bool:
    """Checks if this raw file has already been loaded, so re-running the script is safe."""
    cursor.execute("SELECT 1 FROM stage_readings WHERE raw_file = %s LIMIT 1", (raw_file,))
    return cursor.fetchone() is not None


def load_file(cursor, filepath: Path) -> int:
    """
    Loads a single raw JSON file into stage_readings.
    Returns the number of reading rows inserted.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    recorded_at = parse_recorded_at(filepath.name)
    status = payload.get("status", {})

    inserted = 0
    for code, details in status.items():
        source_id = get_or_create_source(cursor, code, details.get("name", code))

        # The API returns ISO-8601 timestamps with a local timezone offset,
        # e.g. "2025-04-25T00:00:00.150529+02:00". MySQL's DATETIME column
        # has no concept of timezone and cannot parse an offset string
        # directly - inserting the raw string fails. Parsing it in Python
        # and converting to UTC before insert means every timestamp in the
        # database is consistently UTC, avoiding ambiguity later when
        # comparing readings from different sources or time zones.
        stage_updated_utc = datetime.fromisoformat(details["stage_updated"]).astimezone(timezone.utc).replace(tzinfo=None)

        cursor.execute(
            """
            INSERT INTO stage_readings (source_id, stage, stage_updated, recorded_at, raw_file)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                source_id,
                int(details["stage"]),
                stage_updated_utc,
                recorded_at.replace(tzinfo=None),
                filepath.name,
            ),
        )
        inserted += 1

    return inserted


def log_ingestion_run(cursor, status: str, records_fetched: int, raw_file: str, error_message: str = None):
    cursor.execute(
        """
        INSERT INTO ingestion_runs (run_at, status, records_fetched, raw_file, error_message)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (datetime.now(timezone.utc), status, records_fetched, raw_file, error_message),
    )


def main() -> int:
    if not RAW_DATA_DIR.exists():
        print(f"Raw data directory not found: {RAW_DATA_DIR}", file=sys.stderr)
        return 1

    raw_files = sorted(RAW_DATA_DIR.glob("national_status_*.json"))
    if not raw_files:
        print("No raw files found to load.")
        return 0

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"Could not connect to MySQL: {e}", file=sys.stderr)
        return 1

    cursor = conn.cursor()
    total_loaded = 0
    total_skipped = 0

    for filepath in raw_files:
        if already_loaded(cursor, filepath.name):
            total_skipped += 1
            continue

        try:
            records = load_file(cursor, filepath)
            log_ingestion_run(cursor, "success", records, filepath.name)
            conn.commit()
            total_loaded += 1
            print(f"Loaded {records} reading(s) from {filepath.name}")
        except Exception as e:
            conn.rollback()
            log_ingestion_run(cursor, "failure", 0, filepath.name, str(e))
            conn.commit()
            print(f"Failed to load {filepath.name}: {e}", file=sys.stderr)

    cursor.close()
    conn.close()

    print(f"Done. Files loaded: {total_loaded}, already loaded (skipped): {total_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
