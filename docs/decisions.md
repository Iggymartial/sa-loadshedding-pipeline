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
