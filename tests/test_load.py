"""
test_load.py
Unit tests for loader/load.py - the PANDAS-BASED version, which reads
validated Parquet files from data/processed/ (produced by transform.py)
rather than parsing raw JSON directly.

Design decision: every test uses a MagicMock in place of a real MySQL
cursor/connection, and real (small) DataFrames written to temporary
Parquet files rather than mocking pandas itself - this keeps the tests
honest about what pandas actually returns (real Timestamps, real dtypes)
instead of assuming how it behaves.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import load


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def make_processed_df(rows):
    """
    Builds a DataFrame matching exactly what transform.py writes to
    data/processed/*.parquet: source_code, source_name, stage,
    stage_updated, recorded_at, raw_file, validation_notes, valid.
    """
    return pd.DataFrame(rows)


def write_parquet(tmp_path, filename, df):
    path = tmp_path / filename
    df.to_parquet(path, index=False)
    return path


VALID_ROW = {
    "source_code": "eskom",
    "source_name": "Eskom",
    "stage": 0,
    "stage_updated": datetime(2026, 1, 1, 10, 0, 0),
    "recorded_at": datetime(2026, 1, 1, 10, 5, 0),
    "raw_file": "national_status_20260101T100500Z.json",
    "validation_notes": "",
    "valid": True,
}

INVALID_ROW = {
    "source_code": "capetown",
    "source_name": "Cape Town",
    "stage": 12,
    "stage_updated": datetime(2026, 1, 1, 10, 0, 0),
    "recorded_at": datetime(2026, 1, 1, 10, 5, 0),
    "raw_file": "national_status_20260101T100500Z.json",
    "validation_notes": "stage out of expected range 0-8: 12",
    "valid": False,
}


# ---------------------------------------------------------------------
# get_or_create_source / already_loaded - unchanged from the pre-pandas
# version, but re-tested here since they now live in the rewritten file.
# ---------------------------------------------------------------------

def test_get_or_create_source_returns_existing_id_without_inserting():
    cursor = MagicMock()
    cursor.fetchone.return_value = (5,)

    source_id = load.get_or_create_source(cursor, "eskom", "Eskom")

    assert source_id == 5
    assert cursor.execute.call_count == 1


def test_get_or_create_source_inserts_when_missing():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.lastrowid = 7

    source_id = load.get_or_create_source(cursor, "newmunicipality", "New Municipality")

    assert source_id == 7
    assert cursor.execute.call_count == 2


def test_already_loaded_true_when_row_exists():
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    assert load.already_loaded(cursor, "some_file.json") is True


def test_already_loaded_false_when_no_row():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    assert load.already_loaded(cursor, "some_file.json") is False


# ---------------------------------------------------------------------
# insert_valid_rows - the core new logic in the pandas rewrite
# ---------------------------------------------------------------------

def test_insert_valid_rows_only_inserts_rows_marked_valid():
    df = make_processed_df([VALID_ROW, INVALID_ROW])
    cursor = MagicMock()

    with patch("load.get_or_create_source", return_value=1) as mock_get_source:
        inserted = load.insert_valid_rows(cursor, df, VALID_ROW["raw_file"])

    assert inserted == 1
    mock_get_source.assert_called_once_with(cursor, "eskom", "Eskom")
    insert_calls = [c for c in cursor.execute.call_args_list if "INSERT INTO stage_readings" in c.args[0]]
    assert len(insert_calls) == 1


def test_insert_valid_rows_passes_correct_python_types_to_mysql():
    """
    Guards against a real category of pandas bug: values coming out of
    a DataFrame are numpy/pandas types (numpy.int64, pandas.Timestamp),
    not plain Python types. MySQL's connector expects plain int/datetime.
    """
    df = make_processed_df([VALID_ROW])
    cursor = MagicMock()

    with patch("load.get_or_create_source", return_value=1):
        load.insert_valid_rows(cursor, df, VALID_ROW["raw_file"])

    insert_call = [c for c in cursor.execute.call_args_list if "INSERT INTO stage_readings" in c.args[0]][0]
    _, stage, stage_updated, recorded_at, raw_file = insert_call.args[1]

    assert isinstance(stage, int)
    assert isinstance(stage_updated, datetime)
    assert isinstance(recorded_at, datetime)
    assert raw_file == VALID_ROW["raw_file"]


def test_insert_valid_rows_returns_zero_when_all_rows_invalid():
    df = make_processed_df([INVALID_ROW])
    cursor = MagicMock()

    inserted = load.insert_valid_rows(cursor, df, INVALID_ROW["raw_file"])

    assert inserted == 0
    cursor.execute.assert_not_called()


# ---------------------------------------------------------------------
# log_ingestion_run - now has a `notes` parameter that didn't exist
# in the pre-pandas version
# ---------------------------------------------------------------------

def test_log_ingestion_run_includes_notes_when_provided():
    cursor = MagicMock()

    load.log_ingestion_run(cursor, "success", 1, "file.json", notes="1 row(s) failed validation and were skipped")

    args = cursor.execute.call_args.args[1]
    assert args[1] == "success"
    assert args[2] == 1
    assert args[4] is None  # error_message
    assert args[5] == "1 row(s) failed validation and were skipped"  # notes


def test_log_ingestion_run_notes_default_to_none():
    cursor = MagicMock()
    load.log_ingestion_run(cursor, "success", 2, "file.json")
    args = cursor.execute.call_args.args[1]
    assert args[5] is None


# ---------------------------------------------------------------------
# main() - orchestration, now reading Parquet instead of JSON
# ---------------------------------------------------------------------

def test_main_returns_1_when_processed_dir_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path / "does_not_exist")

    exit_code = load.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Run transform.py first" in captured.err


def test_main_returns_0_when_no_processed_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path)

    with patch("load.mysql.connector.connect") as mock_connect:
        exit_code = load.main()

    assert exit_code == 0
    mock_connect.assert_not_called()
    captured = capsys.readouterr()
    assert "No processed files found" in captured.out


def test_main_returns_1_when_database_connection_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path)
    write_parquet(tmp_path, "national_status_20260101T100500Z.parquet", make_processed_df([VALID_ROW]))

    with patch("load.mysql.connector.connect", side_effect=load.mysql.connector.Error("connection refused")):
        exit_code = load.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Could not connect to MySQL" in captured.err


def test_main_skips_files_already_loaded(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path)
    write_parquet(tmp_path, "national_status_20260101T100500Z.parquet", make_processed_df([VALID_ROW]))

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)  # already_loaded() reports True
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("load.mysql.connector.connect", return_value=mock_conn):
        exit_code = load.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "already loaded (skipped): 1" in captured.out
    insert_calls = [c for c in mock_cursor.execute.call_args_list if "INSERT INTO stage_readings" in c.args[0]]
    assert len(insert_calls) == 0


def test_main_loads_valid_rows_and_notes_skipped_invalid_rows(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path)
    write_parquet(
        tmp_path,
        "national_status_20260101T100500Z.parquet",
        make_processed_df([VALID_ROW, INVALID_ROW]),
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # not already loaded, and no existing source
    mock_cursor.lastrowid = 1
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("load.mysql.connector.connect", return_value=mock_conn):
        exit_code = load.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Loaded 1 reading(s)" in captured.out
    assert "1 flagged and skipped" in captured.out

    # Confirm the ingestion_runs insert actually carried the notes text.
    run_log_calls = [c for c in mock_cursor.execute.call_args_list if "INSERT INTO ingestion_runs" in c.args[0]]
    assert len(run_log_calls) == 1
    notes_value = run_log_calls[0].args[1][5]
    assert notes_value == "1 row(s) failed validation and were skipped"


def test_main_continues_after_one_corrupt_processed_file(tmp_path, monkeypatch, capsys):
    """
    Regression test for a real bug found while writing this suite:
    pd.read_parquet() was originally called OUTSIDE the try/except in
    main(), so a single corrupt processed file crashed the entire run
    instead of being logged and skipped. This test locks in the fix.
    """
    monkeypatch.setattr(load, "PROCESSED_DATA_DIR", tmp_path)

    corrupt_path = tmp_path / "national_status_20260101T000000Z.parquet"
    corrupt_path.write_text("this is not a real parquet file")

    write_parquet(
        tmp_path,
        "national_status_20260101T100500Z.parquet",
        make_processed_df([VALID_ROW]),
    )

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.lastrowid = 1
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("load.mysql.connector.connect", return_value=mock_conn):
        exit_code = load.main()  # must not raise

    assert exit_code == 0
    mock_conn.rollback.assert_called_once()

    captured = capsys.readouterr()
    assert "Loaded 1 reading(s)" in captured.out  # the good file still got processed
    assert "Failed to load national_status_20260101T000000Z.parquet" in captured.err

    failure_log_calls = [
        c for c in mock_cursor.execute.call_args_list
        if "INSERT INTO ingestion_runs" in c.args[0] and c.args[1][1] == "failure"
    ]
    assert len(failure_log_calls) == 1

