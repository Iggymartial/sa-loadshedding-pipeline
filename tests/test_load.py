"""
test_load.py
Unit tests for loader/load.py (the pre-pandas version: reads raw JSON
directly and inserts into MySQL).

Design decision: every test uses a MagicMock in place of a real MySQL
cursor/connection. This means these tests run instantly, need no
database running, and can't accidentally write to a real database. The
real end-to-end behaviour (does this actually work against real MySQL)
was already verified manually against a live database - these tests
check the LOGIC in isolation: parsing, timezone conversion, idempotency,
and error handling.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import load


# ---------------------------------------------------------------------
# parse_recorded_at
# ---------------------------------------------------------------------

def test_parse_recorded_at_extracts_correct_utc_datetime():
    result = load.parse_recorded_at("national_status_20260904T140501Z.json")
    assert result == datetime(2026, 9, 4, 14, 5, 1, tzinfo=timezone.utc)


def test_parse_recorded_at_rejects_unexpected_filename():
    with pytest.raises(ValueError, match="does not match expected pattern"):
        load.parse_recorded_at("not_a_matching_filename.json")


# ---------------------------------------------------------------------
# get_or_create_source
# ---------------------------------------------------------------------

def test_get_or_create_source_returns_existing_id_without_inserting():
    cursor = MagicMock()
    cursor.fetchone.return_value = (5,)  # source already exists

    source_id = load.get_or_create_source(cursor, "eskom", "Eskom")

    assert source_id == 5
    # Only the SELECT should have run - no INSERT for a source that already exists.
    assert cursor.execute.call_count == 1


def test_get_or_create_source_inserts_when_missing():
    cursor = MagicMock()
    cursor.fetchone.return_value = None  # source does not exist yet
    cursor.lastrowid = 7

    source_id = load.get_or_create_source(cursor, "newmunicipality", "New Municipality")

    assert source_id == 7
    assert cursor.execute.call_count == 2  # SELECT, then INSERT
    insert_call = cursor.execute.call_args_list[1]
    assert "INSERT INTO sources" in insert_call.args[0]
    assert insert_call.args[1] == ("newmunicipality", "New Municipality")


# ---------------------------------------------------------------------
# already_loaded
# ---------------------------------------------------------------------

def test_already_loaded_true_when_row_exists():
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    assert load.already_loaded(cursor, "some_file.json") is True


def test_already_loaded_false_when_no_row():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    assert load.already_loaded(cursor, "some_file.json") is False


# ---------------------------------------------------------------------
# load_file - the most important tests: this is where the real
# timezone bug lived, so we test that conversion explicitly.
# ---------------------------------------------------------------------

def _write_sample_raw_file(tmp_path, filename="national_status_20260904T140501Z.json"):
    payload = {
        "status": {
            "capetown": {
                "name": "Cape Town",
                "stage": "0",
                "stage_updated": "2025-04-25T00:00:00.150529+02:00",
            },
            "eskom": {
                "name": "Eskom",
                "stage": "2",
                "stage_updated": "2025-05-15T22:00:00.748588+02:00",
            },
        }
    }
    filepath = tmp_path / filename
    filepath.write_text(json.dumps(payload))
    return filepath


def test_load_file_inserts_one_row_per_source(tmp_path):
    filepath = _write_sample_raw_file(tmp_path)
    cursor = MagicMock()

    with patch("load.get_or_create_source", side_effect=[1, 2]):
        inserted = load.load_file(cursor, filepath)

    assert inserted == 2
    assert cursor.execute.call_count == 2


def test_load_file_converts_timezone_offset_to_utc_correctly(tmp_path):
    """
    This is the regression test for the real bug we hit: the API sends
    '2025-04-25T00:00:00.150529+02:00'. Naively inserting that string
    into MySQL fails. The fix converts it to UTC first - this test
    locks in that '00:00:00+02:00' correctly becomes '22:00:00' the
    PREVIOUS day in UTC, not just "some datetime".
    """
    filepath = _write_sample_raw_file(tmp_path)
    cursor = MagicMock()

    with patch("load.get_or_create_source", side_effect=[1, 2]):
        load.load_file(cursor, filepath)

    # First execute() call is for Cape Town's insert - inspect the actual
    # parameters that would have been sent to MySQL.
    first_insert_params = cursor.execute.call_args_list[0].args[1]
    inserted_stage_updated = first_insert_params[2]  # (source_id, stage, stage_updated, ...)

    assert inserted_stage_updated == datetime(2025, 4, 24, 22, 0, 0, 150529)
    assert inserted_stage_updated.tzinfo is None  # must be naive UTC, not offset-aware


def test_load_file_stores_stage_as_integer_not_string(tmp_path):
    filepath = _write_sample_raw_file(tmp_path)
    cursor = MagicMock()

    with patch("load.get_or_create_source", side_effect=[1, 2]):
        load.load_file(cursor, filepath)

    first_insert_params = cursor.execute.call_args_list[0].args[1]
    stage_value = first_insert_params[1]
    assert stage_value == 0
    assert isinstance(stage_value, int)


# ---------------------------------------------------------------------
# main() - orchestration, idempotency, and error handling
# ---------------------------------------------------------------------

def test_main_returns_0_when_no_raw_files_present(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "RAW_DATA_DIR", tmp_path)

    with patch("load.mysql.connector.connect") as mock_connect:
        exit_code = load.main()

    assert exit_code == 0
    mock_connect.assert_not_called()  # no point opening a DB connection with nothing to load
    captured = capsys.readouterr()
    assert "No raw files found" in captured.out


def test_main_returns_1_when_database_connection_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(load, "RAW_DATA_DIR", tmp_path)
    _write_sample_raw_file(tmp_path)

    with patch("load.mysql.connector.connect", side_effect=load.mysql.connector.Error("connection refused")):
        exit_code = load.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Could not connect to MySQL" in captured.err


def test_main_skips_files_already_loaded(tmp_path, monkeypatch, capsys):
    """Proves idempotency at the orchestration level, not just the
    already_loaded() function in isolation."""
    monkeypatch.setattr(load, "RAW_DATA_DIR", tmp_path)
    _write_sample_raw_file(tmp_path)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)  # already_loaded() will report True
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("load.mysql.connector.connect", return_value=mock_conn):
        exit_code = load.main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "already loaded (skipped): 1" in captured.out
    # load_file's INSERT statements should never have run for a skipped file
    insert_calls = [c for c in mock_cursor.execute.call_args_list if "INSERT INTO stage_readings" in c.args[0]]
    assert len(insert_calls) == 0


def test_main_logs_failure_and_continues_when_one_file_is_corrupt(tmp_path, monkeypatch, capsys):
    """If one raw file is malformed, the pipeline should log the
    failure and keep going, not crash the whole run."""
    monkeypatch.setattr(load, "RAW_DATA_DIR", tmp_path)
    bad_file = tmp_path / "national_status_20260904T140501Z.json"
    bad_file.write_text("{not valid json")

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None  # not already loaded
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("load.mysql.connector.connect", return_value=mock_conn):
        exit_code = load.main()

    assert exit_code == 0  # main() itself completes even though one file failed
    mock_conn.rollback.assert_called_once()
    captured = capsys.readouterr()
    assert "Failed to load" in captured.err
