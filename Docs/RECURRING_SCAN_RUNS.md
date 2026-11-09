# Recurring Scan Runs, Findings, and Reports

## Scope and authorization

Recurring scans are fail-closed. Create or select an existing Assessment, enter
an explicit target and authorized scope, and record an authorization reference.
Schedules using the `safe_web_baseline` profile require an affirmative
authorization confirmation. Do not schedule a target unless its owner and rules
permit the planned activity. Exclusions use `!pattern`; loopback addresses are
not implicitly authorized.

Only run scans against systems you own or have explicit permission to test.

## Data model

A scheduled engagement stays linked to one Assessment. Each fire creates one
durable `Task` row, which is the Scan Run. Runs use the existing task queue,
versioned claims, leases, heartbeats, checkpoints, bounded retries, audit
records, and lifecycle events. A run stores a policy snapshot in `task.meta`;
editing a profile later does not silently change an existing run.

The `scheduled` metadata links consecutive runs and `previous_task_id`.
`max_concurrency=1` prevents two active runs for the same Assessment, including
runs created by different schedules. A later fire defers rather than splitting
the Assessment into parallel projects.

Saved Scan Profiles are managed in Settings → Schedules and through
`/api/scan-profiles`. The `safe_web_baseline` kind issues same-origin GET
requests only, denies redirects, checks scope before connecting, and enforces
page, request-rate, response-size, and timeout limits. It does not replace an
expert-led assessment. The `autonomous` kind uses the configured agent and
model policy.

## Canonical findings and diffs

`FindingService` computes a stable fingerprint for a finding within an
Assessment. Repeat observations update the canonical Card and create one
immutable `finding_snapshots` row per run/fingerprint. Unique database
constraints make ingestion idempotent across retry races. Human triage state is
preserved; new evidence is appended to the bounded evidence history.

Each run diff contains `new`, `recurring`, `remediated`, and `reopened` groups
with count chips, run IDs, severity, lifecycle, and triage state. `remediated`
means a previously observed fingerprint was absent from a completed consecutive
run; it is not a guarantee that the underlying issue is fixed. HTTP errors,
timeouts, blocked requests, and oversized responses make a safe-profile run
partial. Partial runs do not mark missing findings remediated.

## Operator workflow

1. Settings → Schedules → New Scan Profile. Set conservative rate, page,
   response-size, and timeout caps.
2. New Schedule. Select the existing Assessment and profile, enter cron and
   timezone, then enter the exact target, scope, and authorization evidence.
3. Use Run now for an explicit on-demand run. Open the run link to inspect its
   state, request count, error state, findings, evidence, diff, and events.
4. On `/runs/<id>`, use Pause, Resume, Cancel, or Retry as appropriate. Viewer
   accounts have read-only access. Pause/resume applies to queued work; an
   active step is not falsely reported as instantly frozen.
5. Review `needs_review` runs and triage findings before reporting. Export the
   run HTML report only after checking evidence and errors. The legacy
   cross-assessment comparison remains available under Legacy comparison; the
   primary Assessment history uses same-Assessment runs.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET/POST | `/api/scan-profiles` | List/create bounded profiles |
| PUT/DELETE | `/api/scan-profiles/{id}` | Edit/delete a profile |
| GET/POST | `/api/schedules` | List/create schedules |
| PUT/DELETE | `/api/schedules/{id}` | Edit/delete a schedule |
| POST | `/api/schedules/{id}/run` | Fire an on-demand run |
| GET | `/api/scan-runs?assessment_id=...&limit=...&skip=...` | Run history |
| GET | `/api/scan-runs/{id}` | Run state, metadata, and policy snapshot |
| GET | `/api/scan-runs/{id}/findings` | Immutable run observations |
| GET | `/api/scan-runs/{id}/diff` | Consecutive-run finding delta |
| GET | `/api/scan-runs/{id}/events?limit=...&before_id=...` | Lifecycle event history |
| GET | `/api/scan-runs/{id}/report?format=html` | Escaped HTML run report |
| POST | `/api/scan-runs/{id}/pause` | Requeue with checkpoint where available |
| POST | `/api/scan-runs/{id}/resume` | Resume a paused run |
| POST | `/api/scan-runs/{id}/cancel` | Cancel and record terminal state |
| POST | `/api/scan-runs/{id}/retry` | Explicit bounded retry |

List endpoints require explicit pagination bounds. HTML reports escape evidence
and are served with a restrictive Content-Security-Policy. Treat reports as
sensitive engagement data.

## Deployment and migration

Back up Postgres and evidence before upgrading. Migrations `003` through `005`
add schedule policy, canonical finding snapshots, and saved profiles. Startup
schema compatibility remains in `database.py`; the Alembic chain is also
provided for controlled upgrades. Test `alembic upgrade head` on a copy before
applying it to a production database. Older application versions ignore the
added columns, but rolling back data written by the new finding lifecycle needs
an explicit recovery plan.

Keep the backend at one scheduler/worker replica. Verify `/health`, frontend
`/`, migration revision, schedule/run API authentication, logs, and metrics
after deployment. Do not expose the development stack or unauthenticated
metrics publicly.

## Verification

Backend tests use a disposable Postgres database. Frontend tests use committed
Vitest/Testing Library dependencies; the original NVD Node tests run separately.
The real-lab E2E is `tests/test_safe_web_baseline.py`: it drives schedule →
queued Task → runtime → actual local HTTP requests through new, recurring,
remediated, reopened, and partial outcomes. No external target is needed.

```bash
cd backend
pytest -q tests/test_safe_web_baseline.py tests/test_finding_lifecycle.py \
  tests/test_recurring_scan_runs.py tests/test_scan_profiles.py \
  tests/test_scan_runs_api.py
pytest -q

cd ../frontend
npm ci
npm test
npm run build
npm audit --audit-level=moderate
```
