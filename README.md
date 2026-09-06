# SA Load Shedding Data Pipeline

An end-to-end data engineering pipeline that ingests South African national
load shedding status data, stores it, transforms it, and serves it via a
REST API.

Built as a solo project to demonstrate the full data engineering lifecycle:
extraction, storage, transformation, database design, orchestration, and
serving — using Python, Java, and MySQL as the primary stack.

## Status: full pipeline working end-to-end (extraction through serving)

This repo has been built incrementally and committed as I go (see
commit history and docs/decisions.md for the full story, including
real bugs found and fixed along the way). Every stage below has been
run against real, live data - nothing here is a mock or a stub:

- [x] Extract national load shedding status from the EskomSePush API
- [x] Persist raw JSON to a local "data lake" folder, timestamped per run
- [x] Confirmed working end-to-end against the live API (v3.1)
- [x] Pandas transformation + data quality validation layer
- [x] MySQL schema + load step (only loads validated data)
- [x] Data quality checks + ingestion logging
- [x] Java (Spring Boot) REST API to serve processed data
- [x] Automated tests for both the Python pipeline and the Java API
- [x] Dockerise the Python side (extractor, transform, loader all run as containers)

Remaining:
- [ ] Airflow DAG to schedule extract -> transform -> load automatically

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
Python transform (pandas: flatten, validate against data quality rules)
        |
        +--> data/quality_log.csv  (flagged rows, with reasons)
        |
        v
data/processed/  (validated Parquet files)
        |
        v
Python loader (only inserts rows that passed validation)
        |
        v
MySQL (normalised schema: sources, stage_readings, ingestion_runs)
        |
        v
Java (Spring Boot) REST API  ->  serves processed data
        |
Airflow DAG orchestrates extract -> transform -> load, scheduled hourly
```

## Setup (current state)

1. Register for a free API token: https://eskomsepush.gumroad.com/l/api
2. Copy `.env.example` to `.env` and add your token
3. Start MySQL (schema applies automatically on first run):
   ```
   docker compose up -d
   ```
4. Extract a reading:
   ```
   cd extractor
   pip install -r requirements.txt
   python extract.py
   ```
5. Transform and validate it:
   ```
   cd ../transform
   pip install -r requirements.txt
   python transform.py
   ```
6. Load the validated data into MySQL:
   ```
   cd ../loader
   pip install -r requirements.txt
   python load.py
   ```
7. Check the data landed correctly:
   ```
   docker exec -it loadshedding_mysql mysql -u pipeline_user -p loadshedding -e "SELECT * FROM stage_readings;"
   ```
   (password is whatever you set for `MYSQL_PASSWORD` in `.env`)

   If anything got flagged along the way, check `data/quality_log.csv`
   to see exactly what failed and why.

8. Run the REST API (needs Java 17+ and Maven installed):
   ```
   cd api
   mvn spring-boot:run
   ```
   Then in another terminal:
   ```
   curl http://localhost:8080/api/sources
   curl http://localhost:8080/api/readings/latest
   curl http://localhost:8080/api/readings
   curl http://localhost:8080/api/readings/source/eskom
   curl http://localhost:8080/api/ingestion-runs
   ```

## Design decisions

See [docs/decisions.md](docs/decisions.md) for the reasoning behind key
choices as the project develops.

## Author

Njabulo Zondo
