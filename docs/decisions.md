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
