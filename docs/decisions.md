# Design Decisions Log

A running record of the "why" behind key choices in this project, kept as
I build - not written after the fact. Useful for me during Q&A, and useful
for anyone reviewing the repo.

## Week 1

**Decision: save raw JSON to disk before any transformation.**
Reasoning: if the transform step has a bug or the requirements change
later, I want to be able to re-run transformation from the original
source data instead of having lost it. This is the standard "data lake"
pattern of separating raw and processed data.

**Decision: use the national `/status` endpoint instead of area-level
lookups for the first version.**
Reasoning: the EskomSePush free tier does not reliably support area
lookups. Rather than block progress on paid access I don't have yet, I
designed the pipeline around the endpoint that is actually available,
and structured the extractor so area-level ingestion can be added later
without a redesign. Real-world APIs are frequently tiered; handling that
is part of the job.

**Decision: timestamp every raw file rather than overwrite a single file.**
Reasoning: each extraction run is a distinct observation in a time
series. Overwriting would destroy history and make it impossible to
later analyse how the stage changed over time.

## Week 1, incident: API version retirement

While testing, `extract.py` started returning `410 Gone` on the `/status`
endpoint. A 410 specifically means "intentionally removed, not coming
back" (as opposed to a 404, which just means "not found right now").
Investigated and confirmed EskomSePush retired their `2.0` API in favour
of `3.0`/`3.1` - the base URL I originally hardcoded no longer exists.

Fix: moved `API_BASE_URL` out of the code and into an environment
variable (`ESP_API_BASE_URL`), with the old URL kept only as a fallback
default. This means the next time the provider changes versions, it's a
one-line `.env` edit, not a code change.

Broader lesson for this project: third-party APIs are not stable
forever. Any pipeline depending on one needs its integration points
(base URLs, auth schemes) kept as configuration, not constants, and
error handling that distinguishes "my config is wrong" from "the
provider changed something" - which is exactly what happened here.

**Resolution, confirmed working:**

Debugging this took three separate steps, each of which ruled something
out before moving to the next:

1. Ran the extractor against `business/3.1/status` and got a
   `ReadTimeout` instead of a clean error - inconclusive, since a
   timeout could mean a bad URL, a dead endpoint, or a network problem.
2. Bypassed Python entirely and tested with `curl.exe` directly against
   the API. This isolated the problem to "is it my code or the network/
   API" - a useful debugging technique generally: when something fails,
   remove layers until you're testing the smallest possible piece.
   `curl` against `areas_search` returned real data immediately, which
   ruled out a network/firewall problem and confirmed v3.1 itself was
   reachable and correctly authenticated.
3. Ran the same `curl` test directly against `business/3.1/status` and
   got a real, valid response - stage data for both Cape Town and
   Eskom, both at stage 0 at time of testing. This confirmed `/status`
   is still a live endpoint under v3.1; the earlier timeout was
   transient, not caused by the endpoint being retired.

Final fix confirmed working end-to-end: `API_BASE_URL` now reads from
`ESP_API_BASE_URL` (falling back to the v3.1 URL by default), and
`python extract.py` successfully saves real API output to
`data/raw/national_status_<timestamp>.json`.

Takeaway for future incidents: when a request fails, first work out
*which layer* is failing (code / network / auth / endpoint) before
guessing at a fix. Testing with `curl` independently of the Python
script was what actually isolated the issue here, not trial-and-error
changes to the script itself.

## Week 3: database layer

**Decision: separate `sources` from `stage_readings` instead of one flat table.**
Reasoning: a source's display name ("Cape Town") doesn't change per
reading - it only depends on the source code. Storing it once in a
lookup table and referencing it by foreign key avoids repeating the
same string on every row and guarantees it's spelled consistently
everywhere. This is standard 2NF/3NF reasoning applied to a real
(small) dataset rather than a textbook example.

**Decision: `get_or_create_source()` instead of a fixed, hardcoded list.**
Reasoning: the API could add more municipalities later (it already
covers more than just Eskom and Cape Town in principle). Letting the
loader create a new source row automatically when it sees an unfamiliar
code means the pipeline doesn't break or need a manual schema update
if that happens.

**Decision: loader checks `raw_file` before inserting, to make loads idempotent.**
Reasoning: this script will eventually run on a schedule (Airflow). If
a scheduled run is retried after a partial failure, or if I run it
manually twice by accident, it must not create duplicate readings.
Tracking which raw files have already been loaded and skipping them
makes re-running always safe.

**Incident: MySQL rejected the API's timestamp format.**
The API returns timestamps like `2025-04-25T00:00:00.150529+02:00`
(ISO-8601 with a timezone offset and microseconds). MySQL's `DATETIME`
type has no concept of timezone and cannot parse an offset directly -
inserting the raw string failed with error 1292. Confirmed this by
actually running the loader against a real database rather than
assuming it would work.

Fix: parse the timestamp in Python with `datetime.fromisoformat()`,
convert it to UTC, then strip the timezone info before inserting a
plain UTC datetime. Now every timestamp in the database is consistently
UTC regardless of what offset the source API used - important since
different sources (Eskom vs municipalities) could theoretically report
in different local offsets.

The failed attempt is still visible as a `failure` row in
`ingestion_runs` - proof the audit table does its job: a real failure
happened, was logged with its actual error message, and the fix is
traceable against it.

## Week 3, incident: Docker couldn't reach Docker Hub

`docker compose up -d` failed trying to pull `mysql:8.0`, with an error
about failing to resolve `registry-1.docker.io`. Debugged this by
isolating layers, the same technique used for the earlier API incident:

1. `docker pull hello-world` failed identically - ruled out anything
   specific to the MySQL image (size, tag, etc).
2. `ping 8.8.8.8` (a raw IP, no hostname lookup involved) succeeded with
   normal latency - confirmed the actual internet connection was fine.
3. `ping`/`nslookup` against an actual hostname both failed - narrowed
   the problem specifically to DNS resolution, not connectivity.
4. `ipconfig /flushdns` followed by a fresh `nslookup` resolved
   correctly - a stale/corrupted DNS cache entry was the root cause.

Fix required no code or config change at all - it was an environment
issue on the development machine, not the project. Documenting it
anyway because "the pipeline broke and here's exactly how I diagnosed
it" is a legitimate demo/Q&A story, and the diagnostic method (test the
smallest possible piece, rule things out one layer at a time) is the
same one used for the API version incident earlier - a pattern worth
having ready to describe, not just the individual fixes.

## Automated tests, added before starting the pandas rewrite

**Decision: write a unit test suite for extract.py and load.py before touching either for the transform layer.**
Reasoning: changing code without tests means any regression is only
caught by manual re-testing, which is slow and easy to skip. Writing
tests first means the pandas rewrite of `load.py` can be checked
against the same expectations the pre-pandas version had to meet.

**Decision: mock the API and the database in every test - no real network calls, no real MySQL connection.**
Reasoning: unit tests should be fast, free to run, and not depend on
having a valid API token or a running database container. Testing
against the *real* API and *real* MySQL already happened manually
earlier in this log - that's integration testing, a different
concern from unit testing the logic in isolation.

**Proof the tests aren't just decorative:** deliberately reintroduced
the exact timezone bug that was fixed earlier (reverted
`stage_updated_utc` back to the raw, unconverted string) and reran the
suite. `test_load_file_converts_timezone_offset_to_utc_correctly`
failed immediately, with a clear assertion error showing the raw string
where a converted `datetime` was expected. Restored the fix and
confirmed all 21 tests passed again. This is the difference between a
test that happens to pass and a test that actually verifies something:
it has to be capable of failing when the bug it targets is present.

## Week 5: transform/validation layer

**Decision: introduce a distinct transform stage instead of validating inline in the loader.**
Reasoning: extraction, validation, and loading are three different
concerns, and keeping them as separate scripts with a file handed
between them (raw JSON -> processed Parquet -> MySQL) means each stage
can be run, tested, and reasoned about independently. It also means
`data/processed/` becomes a permanent, inspectable record of exactly
what the pipeline decided was valid at each point in time.

**Decision: use Parquet, not CSV, for the processed output.**
Reasoning: Parquet is columnar and typed (Week 2 material applied) - a
`stage` column stays an integer and `stage_updated` stays a real
datetime on disk, rather than everything flattening to text the way CSV
does. That avoids re-parsing types every time the file is read again.

**Decision: invalid rows are flagged and logged, never silently dropped.**
Reasoning: silently discarding bad data hides real problems (a broken
API response, a bug in extraction) behind an innocent-looking pipeline
that "just works". Every failed row is written to `data/quality_log.csv`
with the specific reason it failed, so a reviewer - or future me - can
see exactly what was rejected and why, not just that something was.

**Decision: a run with flagged rows is still logged as `success` in
`ingestion_runs`, with details in a separate `notes` column.**
Reasoning: `error_message` should mean "the run itself broke" (a crash,
a connection failure). Skipping bad data is a different thing entirely
- the pipeline worked correctly, the *data* had a problem. Conflating
those two would make it harder to tell, at a glance, whether the
pipeline needs debugging or the upstream data source does.

**Tested with a deliberately broken input, not just clean data.**
Built one raw file with a stage value of 12 (outside the valid 0-8
range) and a missing `stage_updated`. Ran the full transform -> load
flow against it alongside a normal file, and confirmed: the bad file's
2 rows were both flagged with specific, correct reasons in
`quality_log.csv`; zero rows from that file reached `stage_readings`;
the good file's 2 rows loaded normally; and `ingestion_runs` correctly
recorded a `success` status with a note explaining the 2 skipped rows.
Testing against intentionally bad data, not just the happy path, is
what actually proves a validation layer works rather than just
compiles.

## Full pipeline confirmed working end-to-end, real data

Ran extract -> transform -> load in sequence against the real
EskomSePush API on the actual development machine. Result: 5 separate
extraction runs, all validated (0 rows flagged - the data has
genuinely stayed at stage 0 throughout testing), all loaded into
MySQL, all 5 recorded as `success` in `ingestion_runs`. This is the
first time all three stages ran back-to-back against live data rather
than synthetic test fixtures.

**Incident: pyarrow 17.0.0 failed to install on Python 3.13.**
Pip tried to build pyarrow from source (no prebuilt wheel existed for
that combination) and the build itself failed with an unrelated
`pkg_resources` error, not something specific to this project. Confirmed
via research that pyarrow only shipped prebuilt Python 3.13 wheels from
version 18.0.0 onward - the original pin simply predated that. Fixed by
bumping to `18.1.0`, checked against PyPI's actual published version
list before recommending it rather than guessing a number.

## Updated tests for the pandas-based load.py, and a bug found in the process

**Decision: rewrite test_load.py from scratch rather than patch the old one.**
Reasoning: the pandas rewrite changed load.py's actual functions -
`load_file()` (JSON-based) no longer exists; it's replaced by
`insert_valid_rows()` (DataFrame-based). Trying to adapt the old tests
line-by-line would have hidden how different the new code's contract
actually is. Writing fresh tests against the new function signatures
was more honest about what actually needed covering.

**Bug found while writing the new tests: `pd.read_parquet()` was called
outside the try/except block in `main()`.**
While designing a test for "what happens if a processed file is
corrupt", I traced through the actual code path and noticed the parquet
read happened before the try/except that was supposed to catch
per-file failures. Proved this concretely before touching anything:
wrote a corrupt file, mocked a working MySQL connection, and called
`main()` directly - it crashed with an unhandled `ArrowInvalid`
exception instead of logging a failure and continuing to the next file.

This was a real regression introduced during the pandas rewrite: the
pre-pandas `load.py` wrapped its equivalent read (`load_file()`) inside
the try/except, so this exact failure mode was already handled before -
it just didn't get carried over when the code changed shape.

Fix: widened the try/except to cover the entire per-file body (read,
raw_file extraction, already_loaded check, insert), so any failure at
any point in processing one file is caught, rolled back, logged with
the filename as a fallback identifier, and the loop moves on to the
next file. Re-ran the same corrupt-file scenario after the fix and
confirmed: the corrupt file logs a `failure` row and is skipped, and a
second, valid file in the same run still loads successfully.

Locked this in as `test_main_continues_after_one_corrupt_processed_file`,
which fails against the pre-fix code and passes against the fix -
confirmed both directions, not just that the final version happens to
pass.

Takeaway: writing tests isn't just about proving code that already
works still works - tracing through "what should happen in this edge
case" while writing a test is itself a way of finding bugs before a
user (or a demo audience) does.

## Java REST API (Spring Boot) - serving layer

**Decision: Spring Boot 3.5.x over the newer 4.1.x line.**
Reasoning: Spring Boot 4.1 is only weeks old at time of writing. Since I
can't compile or run Java code myself in this environment (Maven
Central isn't reachable the way PyPI was for the Python side), reducing
risk by picking the mature, extremely well-documented 3.x line matters
more than being on the newest release. Java 17 was chosen as the
baseline for the same reason - the widest compatible floor for
whatever JDK is actually installed.

**Decision: DTOs (records) for every API response, never raw JPA entities.**
Reasoning: what the API returns is a deliberate contract, not just
"whatever the database table happens to contain." If the schema
changes later (a new column, a renamed field), the API's shape doesn't
have to change with it unless that's actually intended.

**Decision: `spring.jpa.hibernate.ddl-auto=none` for the real application.**
Reasoning: the schema is owned entirely by `db/schema.sql`, applied by
the Python side of the pipeline. Letting Hibernate auto-generate or
alter tables would create two competing sources of truth for the same
database - a real anti-pattern when a schema is shared across
languages/services.

**Decision: H2 in-memory database for tests, real MySQL only for the running app.**
Reasoning: unit/repository tests should never require Docker to be
running. Tests use a completely separate `application.properties`
(under `src/test/resources`) that points at an in-memory database
Hibernate builds fresh from the entity annotations each run.

**Decision: a correlated subquery (JPQL) for "latest reading per source", not a derived query method.**
Reasoning: Spring Data's method-name query derivation has no built-in
concept of "the latest row per group" - that requires an actual query.
Tested this specifically (not just the simple lookups) because it's
the one piece of genuinely non-trivial logic in this layer: it's easy
to write a query that returns ALL readings, or the wrong one per
source, without a test that inserts two readings for the same source
and asserts specifically that the LATER one comes back.

**Important limitation, stated honestly:** unlike the Python side of
this project, I could not compile or run this Java code myself before
handing it over - Maven Central is not reachable from the environment
used to build it, only a fixed allow-list of package registries.
Every file was written carefully against known Spring Boot 3.5/Spring
Data JPA conventions, but the FIRST real compile and the FIRST real
`mvn test` run happens on the actual development machine, not before.
Any errors get debugged the same way Docker/DNS issues were earlier in
this project: paste the real error, diagnose from there.

## Java REST API confirmed working end-to-end, real data

`mvn clean install` succeeded on the FIRST attempt - all 16 source
files compiled cleanly, all 4 repository tests passed (including the
correlated subquery for "latest reading per source"), and the app
started successfully against the real MySQL database via HikariCP.

Verified all four endpoints against real data:
- GET /api/sources - returned both seeded sources correctly
- GET /api/readings/latest - correctly returned exactly ONE reading
  per source (2 total, not all 12 rows in the table) - proof the
  correlated subquery genuinely filters to the latest per group rather
  than just returning everything
- GET /api/readings - returned all 12 accumulated readings, most
  recent first
- GET /api/readings/source/eskom - correctly filtered to only Eskom's
  6 readings
- GET /api/ingestion-runs - served the pipeline's own audit log over
  HTTP, showing every extract/transform/load run as `success`

This is the full four-layer system working together for the first
time: a real live API -> a Python pipeline (extract, validate, load)
-> MySQL -> a Java REST API, with nothing mocked or faked at any layer.

**Incident: Maven commands failed with "no POM in this directory".**
Ran `mvn test` from the project root instead of the `api/` subfolder,
where `pom.xml` actually lives. Not a bug - Maven always operates
relative to the current working directory, and this project has
multiple language ecosystems (Python at the root, Java under `api/`)
living side by side, so `cd`-ing into the right subfolder before
running language-specific tooling matters more here than in a
single-language project.
