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