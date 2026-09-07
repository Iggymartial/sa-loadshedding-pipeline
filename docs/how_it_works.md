# How This System Works

A plain-English explanation of what this project does, how it does it,
and why each piece exists. For the detailed technical design decisions
and real incidents encountered while building it, see
[decisions.md](decisions.md). For setup and run instructions, see the
main [README.md](../README.md).

## What problem does this solve?

South Africa's power supply gets interrupted on a rotating schedule
known as "load shedding." This system automatically watches that
situation, remembers its history, checks that the data it collects is
trustworthy, and makes it available for anyone - a website, an app,
another program - to ask two simple questions:

- **What's happening right now?**
- **What's happened recently?**

## The story of one piece of data, start to finish

Imagine it's 2pm and Eskom's load shedding stage changes from 0 to 2.
Here is the entire journey that fact takes through this system, with
no human involved at any point.

### 1. Waking up (Airflow)

Every hour, a scheduler this project runs (Apache Airflow) wakes up on
its own and says: "time to check for updates."

### 2. Asking the outside world (the Extractor)

A small Python program reaches out to a real, live South African data
provider (EskomSePush) and asks: "what's the current status?" It saves
the honest, raw answer exactly as received - nothing altered yet, like
taking a photograph before editing it.

### 3. Checking it's trustworthy (the Transformer)

Before that data is allowed anywhere near a permanent record, it gets
inspected:

- Is anything missing?
- Is the stage number actually a sane value (0 through 8), not some
  nonsense number?
- Does the timing make logical sense?

Only data that passes every check gets marked as trustworthy. Anything
suspicious gets flagged and set aside with a written reason - never
silently thrown away, and never silently trusted either.

### 4. Remembering it properly (MySQL database)

The trustworthy data gets filed away in an organised, permanent
record - not just a pile of files, but structured the way a librarian
organises books: this reading belongs to Eskom, it happened at this
time, here's what stage it reported.

This is also where the system keeps a diary of its own behaviour: "at
2pm I checked, it worked, here's what I found." Weeks later, this diary
is what proves the system was actually running and doing its job
correctly, not just assumed to be.

### 5. Making it available to anyone (the Java API)

Finally, a separate program stands ready to answer questions from the
outside world:

- What's the current stage?
- What's Eskom's history for the past week?
- Did the pipeline run successfully today?

It answers instantly, in a simple, standard format any website or app
could understand, without anyone needing to know SQL or touch the
database directly.

### 6. All of it, running itself

The entire five-step story above repeats automatically, once an hour,
forever, without anyone lifting a finger - because Airflow keeps
waking the whole chain up on schedule.

## The shape of the whole system

```
   Real live SA electricity data, out in the world
                    |
                    v
        Extract  ->  Validate  ->  Store  ->  Serve
        (Python)     (Python)     (MySQL)    (Java)

        Airflow wakes this whole chain up automatically, hourly

        Everything runs inside Docker containers, so it behaves
        the same way on any machine, not just the one it was built on
```

## What purpose does this actually serve?

**Practically:** this is a real, working piece of infrastructure. If a
website or app were connected to the Java API right now, it could
genuinely show people accurate, current load shedding information -
this isn't a simulation of a real system, it *is* one, just running at
a small scale.

**As a demonstration of skill:** it shows, with real evidence rather
than just claims, the ability to take data from *outside* one's
control (a real API that changes, breaks, and misbehaves - which it
genuinely did, more than once, during development), get it into a
*trustworthy* permanent record, and make it *usable* by other
systems - while also proving the whole thing keeps running unattended
and can recover from its own mistakes. That is the actual job of a
data engineer, done in miniature, but done for real.

## Why each piece of technology exists, in one line each

| Technology | Its one job |
|---|---|
| **Python** | Does the pipeline work - extraction, validation, loading - because it's the language built for data wrangling |
| **MySQL** | Remembers everything permanently, in an organised, queryable way |
| **Java (Spring Boot)** | Exposes that memory to the outside world safely and consistently |
| **Docker** | Means "this runs the same everywhere," not just on one laptop |
| **Apache Airflow** | Means "this happens automatically," not "someone has to remember to run it" |

Five honest, understandable jobs, each done by the right tool, working
together - with no single piece needing to know the internal details
of any other.
