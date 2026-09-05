"""
test_extract.py
Unit tests for extractor/extract.py.

Design decision: every test mocks requests.get - none of these tests
make a real network call. That's deliberate: unit tests should be fast,
free, and runnable with no API token and no internet connection. Testing
against the REAL API is a separate, manual step (which we already did),
not something that should run every time this test suite runs.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import extract


class FakeResponse:
    """A minimal stand-in for requests.Response, only implementing what extract.py actually uses."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_fetch_national_status_missing_token_raises(monkeypatch):
    """If no API token is configured, we should fail fast with a clear
    error - before ever attempting a network call."""
    monkeypatch.setattr(extract, "API_TOKEN", None)

    with pytest.raises(RuntimeError, match="ESP_API_TOKEN"):
        extract.fetch_national_status()


def test_fetch_national_status_success(monkeypatch):
    """A successful API call should return the parsed JSON body."""
    monkeypatch.setattr(extract, "API_TOKEN", "fake-token-123")
    fake_payload = {"status": {"eskom": {"stage": "0"}}}

    with patch("extract.requests.get", return_value=FakeResponse(fake_payload)) as mock_get:
        result = extract.fetch_national_status()

    assert result == fake_payload
    # Confirm the token was actually sent as the 'token' header, not
    # something like Authorization - the API's actual auth scheme.
    _, kwargs = mock_get.call_args
    assert kwargs["headers"] == {"token": "fake-token-123"}


def test_fetch_national_status_http_error_propagates(monkeypatch):
    """A 4xx/5xx response should raise, not silently return bad data."""
    monkeypatch.setattr(extract, "API_TOKEN", "fake-token-123")

    with patch("extract.requests.get", return_value=FakeResponse({}, status_code=500)):
        with pytest.raises(requests.HTTPError):
            extract.fetch_national_status()


def test_save_raw_creates_timestamped_json_file(tmp_path, monkeypatch):
    """save_raw should create a new file whose name contains a UTC
    timestamp, with the exact payload written as JSON."""
    monkeypatch.setattr(extract, "RAW_DATA_DIR", tmp_path)

    payload = {"status": {"eskom": {"stage": "1"}}}
    saved_path = extract.save_raw(payload, source_name="national_status")

    assert saved_path.exists()
    assert saved_path.name.startswith("national_status_")
    assert saved_path.name.endswith(".json")
    # Matches the pattern load.py's regex expects, e.g. _20260904T140501Z.json
    import re
    assert re.search(r"_\d{8}T\d{6}Z\.json$", saved_path.name)

    with open(saved_path) as f:
        assert json.load(f) == payload


def test_save_raw_does_not_overwrite_previous_files(tmp_path, monkeypatch):
    """Two separate extraction runs should never collide on filename -
    this is what makes data/raw/ a genuine time series."""
    monkeypatch.setattr(extract, "RAW_DATA_DIR", tmp_path)

    extract.save_raw({"status": {}}, source_name="national_status")
    # Force a different timestamp by writing a second file directly,
    # simulating "some time later" without actually sleeping in a test.
    with patch("extract.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "20991231T235959Z"
        second_path = extract.save_raw({"status": {}}, source_name="national_status")

    all_files = list(tmp_path.glob("national_status_*.json"))
    assert len(all_files) == 2
    assert second_path.name == "national_status_20991231T235959Z.json"


def test_main_returns_1_and_prints_config_error_when_token_missing(monkeypatch, capsys):
    monkeypatch.setattr(extract, "API_TOKEN", None)

    exit_code = extract.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Configuration error" in captured.err


def test_main_returns_1_on_api_request_failure(monkeypatch, capsys):
    monkeypatch.setattr(extract, "API_TOKEN", "fake-token")

    with patch("extract.requests.get", side_effect=requests.ConnectionError("no network")):
        exit_code = extract.main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "API request failed" in captured.err


def test_main_returns_0_and_saves_file_on_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extract, "API_TOKEN", "fake-token")
    monkeypatch.setattr(extract, "RAW_DATA_DIR", tmp_path)
    fake_payload = {"status": {"eskom": {"stage": "0"}}}

    with patch("extract.requests.get", return_value=FakeResponse(fake_payload)):
        exit_code = extract.main()

    assert exit_code == 0
    saved_files = list(tmp_path.glob("national_status_*.json"))
    assert len(saved_files) == 1
    captured = capsys.readouterr()
    assert "Saved raw extract to" in captured.out
