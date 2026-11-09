# Extended assessment workflows: integration review

This branch is based on upstream `7f428c0b582292d8cb00ec5f7d8ed57d2de59cf9`. It imports an extended deployment snapshot and subsequent improvements; it is not a claim that every added feature was authored during this review. The deployment snapshot did not retain its original Git ancestry. Upstream attribution and the AGPL license are preserved. See [the historical comparison](UPSTREAM_COMPARISON.md) for provenance.

## Scope

- Durable Kanban tasks, bounded built-in model execution, recurring schedules, run evidence and finding lifecycle views.
- A separate Application Security workspace with source snapshots, baseline rules, optional AI review, triage and JSON/HTML/SARIF reports.
- Administrator-managed GitHub/GitLab connections with encrypted PAT storage, per-repository grants and revocation checks.
- OTP/recovery, OIDC SSO, role restrictions, audit and operational extensions inherited from the deployment snapshot.
- Clearer navigation, UTC timestamp handling, English in-app guides and illustrated documentation.
- Source-build bootstrap, CI and deployment examples.

## Compatibility and review decisions

- Keep upstream's `mcp==1.28.1`; do not downgrade it to the deployed snapshot's earlier pin.
- Preserve upstream-only host-agent execution modules and legacy TLS/localhost Compose files. Their presence does not certify compatibility with the new launcher; the extended snapshot uses its own host-execution path. Reconciliation remains an explicit maintainer decision.
- **Launcher change:** `./start.sh` creates private configuration and builds this edition from source. It accepts `--build`, `--check` and `--help`. Upstream `--dev`, `--lan`, `--domain` and `--localhost` flags are not implemented by this launcher. See [supported installation modes](QUICK_START.md). This is a breaking workflow change requiring review before merging.
- Remove the tracked runtime `backend/.env.docker`; ship examples and generate secrets instead. Existing deployment configuration must be backed up and preserved during migration.
- Keep upstream line-ending attributes and shell executable modes. Exclude dependencies, build output, databases, credentials, test-server state and local image downloads.
- Use one backend replica for the extended orchestration architecture. AppSec source is not executed, and AI transfer requires explicit consent. Findings remain review candidates.

## Validation evidence

The [initial QA report](QA_REPORT.md) and [live integration report](LIVE_INTEGRATION_QA.md) record the deployed snapshot's tests, including real Kimi, local GitLab, Keycloak/OTP, SMTP/PDF and signed webhooks. They are historical evidence, not a claim that all external providers were exercised again on this branch.

Release preparation additionally runs backend lint, dependency consistency and the full backend suite with upstream MCP; a clean frontend dependency install, tests and production build; installer bootstrap tests; whitespace and credential/artifact checks. CI runs frontend tests as well as its build. Exact branch results are included in the pull request.

The live checks found and corrected Kimi temperature/reasoning handling, UTC parsing, false remediation after unrelated agent tasks, and OIDC `at_hash` verification. Public documentation omits machine-specific addresses and paths.

This is a draft integration proposal. It does not certify live GitHub private-account delivery, every AI CLI, Slack/Telegram delivery, public TLS/DNS installation, distributed orchestration or sustained load. Native PR/MR checks, dependency advisory matching and merge gates are not implemented by the initial AppSec module.
