"""
extract.py
Week 1 of the SA Load Shedding pipeline.

Responsibility: pull the current national load shedding status from the
EskomSePush API and persist the raw, untouched JSON response to disk.

Design decision: we save RAW data first, before any cleaning or transformation.
This is the "data lake" pattern - keep an unmodified copy of every extraction
so that if a downstream transform has a bug, we can always re-process from
the original source instead of losing data.

Usage:
    python extract.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("ESP_API_TOKEN")
API_BASE_URL = os.getenv("ESP_API_BASE_URL", "https://developer.sepush.co.za/business/3.1")

# Raw extracts land here, one timestamped file per run.
RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch_national_status() -> dict:
    """
    Calls the /status endpoint, which returns the current national
    load shedding stage. This endpoint works on the free tier.

    Returns the parsed JSON response.
    Raises requests.HTTPError if the API call fails.
    """
    if not API_TOKEN:
        raise RuntimeError(
            "ESP_API_TOKEN is not set. Copy .env.example to .env and add your "
            "token from https://eskomsepush.gumroad.com/l/api"
        )

    headers = {"token": API_TOKEN}
    response = requests.get(f"{API_BASE_URL}/status", headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


def save_raw(payload: dict, source_name: str) -> Path:
    """
    Writes the raw API response to data/raw/, named with a UTC timestamp
    so every extraction run is preserved and traceable back to when it ran.
    """
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{source_name}_{timestamp}.json"
    filepath = RAW_DATA_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return filepath


def main() -> int:
    """
    Runs one extraction cycle. Returns a process exit code (0 = success)
    so this can later be wired into an Airflow task or a cron job and
    its success/failure is machine-readable.
    """
    try:
        print("Fetching national load shedding status...")
        status_payload = fetch_national_status()
    except RuntimeError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"API request failed: {e}", file=sys.stderr)
        return 1

    saved_path = save_raw(status_payload, source_name="national_status")
    print(f"Saved raw extract to: {saved_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
