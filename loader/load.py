"""
load.py
Loads VALIDATED records from data/processed/ (produced by transform.py)
into MySQL. Only rows marked `valid` are inserted into stage_readings -
rows that failed a data quality check were already flagged and logged
to data/quality_log.csv by the transform stage, and are skipped here
rather than silently loaded as if they were trustworthy.

Design decision: idempotent by design, same as before - a raw file that
has already been loaded (tracked via the raw_file column on
stage_readings) is skipped on re-run.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

PROCESSED_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER", "pipeline_user"),
    "password": os.getenv("MYSQL_PASSWORD", "pipeline_password"),
    "database": os.getenv("MYSQL_DATABASE", "loadshedding"),
}


def get_or_create_source(cursor, code: str, display_name: str) -> int:
    """Looks up a source by code, creating it if the API introduces a new one."""
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


def insert_valid_rows(cursor, df: pd.DataFrame, raw_file: str) -> int:
    """Inserts only rows where valid == True. Returns the number inserted."""
    valid_df = df[df["valid"]]
    inserted = 0

    for _, row in valid_df.iterrows():
        source_id = get_or_create_source(cursor, row["source_code"], row["source_name"])
        cursor.execute(
            """
            INSERT INTO stage_readings (source_id, stage, stage_updated, recorded_at, raw_file)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                source_id,
                int(row["stage"]),
                row["stage_updated"].to_pydatetime(),
                row["recorded_at"].to_pydatetime(),
                raw_file,
            ),
        )
        inserted += 1

    return inserted


def log_ingestion_run(cursor, status: str, records_fetched: int, raw_file: str,
                       error_message: str = None, notes: str = None):
    cursor.execute(
        """
        INSERT INTO ingestion_runs (run_at, status, records_fetched, raw_file, error_message, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (datetime.now(timezone.utc), status, records_fetched, raw_file, error_message, notes),
    )


def main() -> int:
    if not PROCESSED_DATA_DIR.exists():
        print(f"Processed data directory not found: {PROCESSED_DATA_DIR}", file=sys.stderr)
        print("Run transform.py first.", file=sys.stderr)
        return 1

    processed_files = sorted(PROCESSED_DATA_DIR.glob("national_status_*.parquet"))
    if not processed_files:
        print("No processed files found to load. Run transform.py first.")
        return 0

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"Could not connect to MySQL: {e}", file=sys.stderr)
        return 1

    cursor = conn.cursor()
    total_loaded = 0
    total_skipped = 0

    for filepath in processed_files:
        df = pd.read_parquet(filepath)
        if df.empty:
            continue

        raw_file = df["raw_file"].iloc[0]

        if already_loaded(cursor, raw_file):
            total_skipped += 1
            continue

        try:
            inserted = insert_valid_rows(cursor, df, raw_file)
            invalid_count = len(df) - inserted
            notes = f"{invalid_count} row(s) failed validation and were skipped" if invalid_count else None

            log_ingestion_run(cursor, "success", inserted, raw_file, notes=notes)
            conn.commit()
            total_loaded += 1

            msg = f"Loaded {inserted} reading(s) from {raw_file}"
            if invalid_count:
                msg += f" ({invalid_count} flagged and skipped - see data/quality_log.csv)"
            print(msg)
        except Exception as e:
            conn.rollback()
            log_ingestion_run(cursor, "failure", 0, raw_file, error_message=str(e))
            conn.commit()
            print(f"Failed to load {raw_file}: {e}", file=sys.stderr)

    cursor.close()
    conn.close()

    print(f"Done. Files loaded: {total_loaded}, already loaded (skipped): {total_skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
