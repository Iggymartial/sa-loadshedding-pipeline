# SA Load Shedding Data Pipeline

An end-to-end data engineering pipeline that ingests South African national
load shedding status data, stores it, transforms it, and serves it via a
REST API.

Built as a solo project to demonstrate the full data engineering lifecycle:
extraction, storage, transformation, database design, orchestration, and
serving — using Python, Java, and MySQL as the primary stack.

## Status: Week 1 - Extraction

This repo is being built incrementally and committed as I go (see commit
history). Right now it covers just the extraction layer. Planned next:

- [x] Extract national load shedding status from the EskomSePush API
- [x] Persist raw JSON to a local "data lake" folder, timestamped per run
- [ ] MySQL schema + load step
- [ ] Pandas transformation/cleaning layer
- [ ] Dockerise the pipeline
- [ ] Airflow DAG to schedule extraction hourly
- [ ] Java (Spring Boot) REST API to serve processed data
- [ ] Data quality checks + ingestion logging

## Why this data source

South Africa's load shedding schedule is real, live, and constantly
changing - it's a good fit for a data pipeline because there's genuine
volume (data accumulates every run) and velocity (the stage can change
multiple times a day) to work with, not a static dataset.

Data comes from the [EskomSePush API](https://eskomsepush.gumroad.com/l/api).
Note: as of this build, the free tier reliably supports the national
`/status` endpoint. Area-level schedule lookups may require a paid plan -
this pipeline is designed around the free national status endpoint, with
area-level ingestion as a stretch goal if/when that access is available.
Handling a tiered API gracefully (rather than assuming full access) is a
deliberate design decision, not an oversight.

## Architecture (target end state)

```
EskomSePush /status API
        |
        v
Python extractor  ->  data/raw/  (timestamped raw JSON, untouched)
        |
        v
Python transform (pandas: clean, validate, reshape)
        |
        v
MySQL (normalised schema: stage_readings, ingestion_runs)
        |
        v
Java (Spring Boot) REST API  ->  serves processed data
        |
Airflow DAG orchestrates extract -> transform -> load, scheduled hourly
```

## Setup (current state)

1. Register for a free API token: https://eskomsepush.gumroad.com/l/api
2. Copy `.env.example` to `.env` and add your token
3. Install dependencies:
   ```
   cd extractor
   pip install -r requirements.txt
   ```
4. Run the extractor:
   ```
   python extract.py
   ```
5. Check `data/raw/` for the saved JSON extract

## Design decisions

See [docs/decisions.md](docs/decisions.md) for the reasoning behind key
choices as the project develops.

## Author

Njabulo Zondo
