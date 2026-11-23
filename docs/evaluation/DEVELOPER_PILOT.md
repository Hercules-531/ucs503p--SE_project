# Developer time-to-first-call pilot

**Status: not yet conducted.** This protocol and the summarizer do not represent participant
results. Run the study with real volunteers and record actual observations before reporting it.

## Preparation

1. Recruit a small convenience sample of developers or computing students. Participation is
   voluntary; explain the task, the anonymous data recorded and that they may stop at any time.
2. Use a disposable local database initialized with `scripts.start_local --db PATH --skip-mirror`.
   Prepare a separate fresh database for each participant so existing accounts, keys and usage do
   not affect the task. Use synthetic email addresses and passwords; do not record credentials.
3. Give each person the same starting page (`/developers`) and access to the same documentation.
   Record the project version, configuration, date, dataset size, sample size and timeout in the
   final report. Do not give step-by-step help unless requested; record any assistance.

## Task and measurement

Read the same instruction to everyone: “Using the supplied documentation, create a developer
account and API key, then make a successful authenticated request for the scheme list. Show the
HTTP status and identify the source field in the response.” Start a stopwatch when the participant
first sees the developer page. Stop at the first **HTTP 200** response whose `data` and `meta.source`
are visible, using the participant's personal key. Both the playground and a direct HTTP client
are acceptable. A demo key or unauthenticated response does not meet the task.

Use a fixed 10-minute limit. Record completion time in whole seconds, whether assistance occurred,
and whether the task completed, timed out, or was voluntarily stopped. Do not count a 401, a
partial response or an account creation as completion. Stop the clock at the limit for a timeout;
record the actual elapsed time if the participant stops earlier. Do not enter names, emails, API
keys, session tokens, screen recordings or other identifying information in the observations file.

## Record and summarize

Create a **private** JSON file outside the repository using the structure below. The values shown
are format examples only; replace them with real observed values and never present them as results.

```json
{
  "timeout_seconds": 600,
  "observations": [
    {"outcome": "completed", "elapsed_seconds": 145, "assistance": false},
    {"outcome": "timed_out", "elapsed_seconds": 600, "assistance": true}
  ]
}
```

Run `.venv\Scripts\python.exe -m scripts.summarize_pilot PATH_TO_OBSERVATIONS.json`.
The command prints participant and outcome counts, completion rate, and median completion times
for all successful participants and for the unassisted subset. Failed or stopped attempts are
reported separately and are **not** included in the median; their elapsed times are censored, not
completed times. If nobody completes, the corresponding median is `null`.

Report the number recruited and completing, all assistance and stop counts, both medians and the
time limit. Describe recruitment and any disruptions. A small convenience sample is exploratory;
it does not establish population-wide performance. Store private notes securely, retain them only
as needed for the course, and publish only aggregated, non-identifying results with permission.
