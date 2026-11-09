> Historical deployment review. For the current integration branch and compatibility decisions, see [Release review](RELEASE_REVIEW.md).

# AIDA upstream comparison and review

Reviewed on 8 November 2026.

## Comparison basis

Upstream: [Vasco0x4/AIDA](https://github.com/Vasco0x4/AIDA), checked-out `main` commit [`7f428c0b582292d8cb00ec5f7d8ed57d2de59cf9`](https://github.com/Vasco0x4/AIDA/commit/7f428c0b582292d8cb00ec5f7d8ed57d2de59cf9).

The production directory did not contain Git history. Therefore this is a file/content comparison against that exact upstream snapshot, not a claim that every difference was authored in this session or that this commit is the fork's original ancestor. The old AIDA directory reported local commit `29d0d6521d3a80fc373162649d859c275cd8e291`, which was not present in the fetched upstream history.

Three layers are distinguished:

1. Upstream AIDA at the pinned commit above.
2. The extended production source that existed before this collaboration (captured locally as baseline `f161011d02498d4bb54d1fb84d3e526080ac6875`).
3. The Kanban/Scheduler improvements and this UTC/interface/consolidation follow-up.

## Inventory

The source snapshot taken at the beginning of this follow-up, after the first Kanban release, contains **419 added files, 90 modified files and 185 unchanged files** relative to upstream, plus **9 upstream paths absent from the snapshot**. Line-ending-only changes are ignored. Runtime environments, dependencies, build output, secrets, backups, logs and evidence were excluded. The missing `backend/logs/.gitkeep` is an extraction exclusion, not evidence of a functional deletion.

Added files are distributed across backend (159), skills (139), frontend (49), documentation images (33), verification (12), Docs (11), Kubernetes manifests (9), scripts (3), deployment configuration (2), CI (1) and an installation guide (1). These numbers describe file inventory, not independently validated features or lines of original work. English documentation and the latest UI follow-up add further files after this baseline snapshot.

The accompanying `AIDA-upstream-file-inventory.csv` lists every compared path and its status/byte sizes. All upstream-tracked paths were checked against the production snapshot; detailed behavioral review focused on execution, scheduling, authentication, evidence and deployment. This is not a line-by-line security certification of all added skill content.

## What upstream already provides

The upstream tree contains the Assessment workspace, recon/cards/credentials, command execution and approvals, MCP tools, authentication, PDF reporting, ASVS and the Docker execution environment. Its launcher already supports several AI clients. These are not new features invented in this session.

## Extensions already present before our first release

| Area | Local difference | Main evidence paths |
| --- | --- | --- |
| Kanban | Durable tasks, six workflow columns, drag ordering, task details, dependencies, comments/files and optimistic versions | `frontend/src/pages/Board.jsx`, `backend/api/tasks.py`, `backend/api/task_extras.py`, `backend/services/task_service.py`, `backend/models/task*.py` |
| Autonomous execution | In-process worker pool, leases/heartbeats, retry/recovery, planner, checkpoints, scope checks and model tools | `backend/services/agent/{runner,runtime,planner,scope,tools}.py` |
| Provider configuration | Built-in model credentials, provider adapters, fallback/settings UI | `backend/api/ai_models.py`, `backend/services/ai_model_service.py`, `backend/services/llm/provider.py` |
| Recurring scans | Schedules, cron/timezones, profile templates, run history, per-run finding snapshots | `backend/api/{schedules,scan_profiles,scan_runs}.py`, `backend/services/scheduler.py`, `frontend/src/pages/RunDashboard.jsx` |
| Bounded web profile | GET-only baseline, scope/DNS checks, redirect denial, page/byte/time/request-spacing limits | `backend/services/scanning/safe_web.py` |
| Findings lifecycle | Fingerprints, idempotent ingest, run snapshots and comparisons | `backend/services/{finding_service,findings_diff}.py`, `backend/models/finding_snapshot.py` |
| Evidence | Artifact API, database bytes, file mirror and hash-chain verification | `backend/api/artifacts.py`, `backend/services/{evidence_store,evidence_chain}.py` |
| Account security | Optional OTP/recovery, OIDC SSO, centralized admin/auditor/viewer policy and audit | `backend/services/{otp_service,oidc_service,audit_service}.py`, `backend/api/{auth,sso,users}.py`, `backend/middleware/rbac.py` |
| Intelligence/context | Knowledge store, skill loader, NVD cache/scheduler and takeover workflow | `backend/services/{knowledge_service,skills_loader,nvd_service,nvd_scheduler,takeover_service}.py` |
| Reports/integrations | Report branding, submission helpers and Telegram integration | `backend/services/{branding,submission_service}.py`, `backend/services/telegram/` |
| Host execution | A separate opt-in policy-constrained implementation | `backend/services/host_execution.py`, `backend/mcp/modules/mcp_host_execution.py` |
| CLI adapters | Expanded client-specific configuration and workspace handling | `backend/launcher_adapters.py`, `aida.py`, frontend MCP client components |
| Operations | CI, tests, metrics, backup scripts, deployment/Kubernetes files and operator manuals | `.github/workflows/ci.yml`, `backend/tests/`, `backend/services/metrics.py`, `scripts/`, `deploy/`, `k8s/`, `Docs/` |

The built-in autonomous runner invokes the provider layer; it is not simply a wrapper that launches every listed external CLI. This distinction matters when diagnosing authentication and model execution.

## Changes from this collaboration

### First Kanban/Scheduler release

- Persisted sidebar expansion instead of hover-driven page movement; accessible control names and correct Dashboard active state.
- Board summary, search, priority/source filters, hide-completed, responsive columns, keyboard card access and status selection.
- Clear runner unavailable/paused state; failed toggles and task actions no longer masquerade as successful state changes.
- Context files upload before queueing; retry resumes the remaining steps without duplicating the task.
- Viewer controls are read-only; administrative model requests are separated from board refreshes.
- Board events coalesce for 250 ms, refresh has a stale-response guard and a 30-second fallback.
- Dedicated `/schedules` page, server-generated five-run preview and explicit timestamp interpretation.
- Standard five-field cron validation, post-lock due/enabled recheck, transaction rollback after scheduler errors.
- Schedule listing retrieves last-task statuses in a batch rather than N+1 queries.
- Dashboard shortcuts and smaller timeline; HTML revalidation and immutable hashed-asset caching.

### This follow-up

- Fixed UTC offset selector from UTC-12:00 to UTC+14:00, UTC default, readable labels and preserved legacy regional zones.
- Clearer Board headers/column accents, stronger contrast, Scheduler workflow cards, form section headings and reduced-motion support.
- Schedule save errors appear inside the open drawer, where the operator can see them.
- Non-admin Scheduler views no longer request the admin-only model endpoint.
- English product, Kanban, administration, operations, architecture and CLI/MCP guides, accessible in the application at `/guide`; English pointers preserve old documentation URLs.
- Same-origin API defaults and regression coverage prevent unconfigured LAN builds from calling the visitor's localhost.
- Nginx forwards the original Host including its port, preserving port 31337 during trailing-slash API redirects.
- Mobile search controls truncate cleanly instead of wrapping beyond the header.
- Consolidation of the Mac mini to the five production containers; old application code and old networks removed, shared volumes protected, autostart corrected.

## Differences that require deliberate integration

The local backend pins `mcp==1.26.0`, while the compared upstream pins `mcp==1.28.1`. This is dependency drift, not a verified vulnerability finding. A dependency update should be validated against local HTTP/stdio MCP and authentication extensions, not copied into production without regression testing.

Upstream's `backend/services/execution/` package, `tools/host_agent.py` and `docker-compose.localhost.yml` are absent locally; the local tree has its own `host_execution.py`. `docker-compose.tls.yml` is also absent from production. These are divergent implementations/configurations, not proof that upstream functionality was intentionally removed by this collaboration. Do not overwrite one architecture with the other during a future merge.

The AGPL license and upstream attribution are retained. No changes were pushed to the public repository.

## Review findings and practical limits

| Finding | Evidence / consequence | Disposition |
| --- | --- | --- |
| Two obsolete stacks remained active | Ten old containers consumed resources and exposed old ports | Removed after inspection and backups |
| Old and production backends shared evidence/log volumes | Blind volume deletion would damage production | Shared volumes preserved |
| Autostart targeted `~/AIDA` | Reboot/login could start the wrong deployment | Updated to explicit `aida-prod` production Compose |
| Production DB/proxy Compose labels referenced AIDA-dev | Historical launch location, despite production volumes/network | Operational commands now use production explicitly; containers remain working |
| Form errors could be behind the drawer | Failed save was hard to diagnose | Inline drawer error added |
| Timezone entry required IANA knowledge | Easy to enter an invalid or confusing zone | UTC offset selector with preview |
| Schema startup catches migration errors | `database.py` can continue with compatibility fallbacks | Remains; health alone is not schema validation |
| Hash-chain linking and evidence mirror are best effort | NULL/legacy links can be skipped; not WORM or an external signature | Documented, not represented as immutable evidence |
| Free-form command scope checks are heuristic | Parsing is not a network enforcement boundary | Retain container/network isolation; no universal containment claim |
| Safe HTTP preflight and request use separate DNS resolution | Potential DNS change between validation and connection; not exploited in this review | Requires a dedicated pinned-resolution/network-isolation design and tests |
| Single-process orchestration assumptions | UI/tests do not establish distributed scheduler/WebSocket guarantees | Keep one backend replica |
| Frontend lint debt | Large pre-existing warning count | No zero-warning claim; do not suppress rules to make a clean-looking report |

Previous verification documents report additional historical tests. They are useful records, but they are not new test runs from this follow-up. The first release in this session passed 1,274 backend tests on an isolated PostgreSQL database. This follow-up changes frontend/documentation/deployment only; its exact final checks are recorded in the release report.

No real target scan or external provider completion was started for this review. Full load testing, all-client live-provider verification, database migration drift remediation and comprehensive security assessment remain separate work. “Everything works 100%” would not be an evidence-based claim.

## Application Security module — 9 November 2026

Added a separate source-review workspace at `/appsec`, three additive database tables and an authenticated `/api/appsec` API. It supports public GitHub/GitLab commit snapshots and ZIP uploads; bounded Python AST / JavaScript pattern checks, masked secret candidates, npm/Python dependency inventory and optional explicitly authorized AI review. Results support manual triage, comparison to the previous completed scan, JSON/HTML/SARIF exports and idempotent Backlog fix tasks.

AppSec has an independent PostgreSQL-coordinated worker. It never executes repository source and does not enable the pentest runner. The first release does not include native PR/MR integrations, dependency CVE matching, dynamic verification, dedicated CI credentials or merge blocking. The AppSec guide documents limits and partial/failure semantics.

Validation: 89 backend tests across AppSec, task API and runner regression suites; 52 frontend tests plus 4 service tests. The live installation processed a synthetic ZIP fixture through both API and browser upload (6 files, 4 expected candidates, 2 dependency records), with a repeat scan reporting zero new candidates. Public source acquisition was checked against small GitHub and GitLab example repositories. AI behavior was tested with a mock provider, not billed live requests.
