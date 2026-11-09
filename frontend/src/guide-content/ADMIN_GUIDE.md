# Administration

## Roles

Authorization is enforced on the backend; hidden controls are not the security boundary.

| Role | Access |
| --- | --- |
| Viewer | Read-only operational data |
| Auditor | Operational changes, including tasks, schedules and scan profiles |
| Admin | User management, AI model credentials, MCP keys, audit, platform settings and runner controls |

The authoritative rules are in `backend/middleware/rbac.py` and individual routes. `401` indicates an authentication problem; `403` indicates insufficient permission. These are coarse roles, not a claim of complete tenant isolation.

## Users and OTP

Use Users to create, deactivate and manage accounts. Temporary-password resets require a later password change. Password reset preserves enrolled OTP; **Reset OTP** is a separate action that clears enrollment, pending challenges and recovery codes. OTP reset is not a universal immediate revocation of all already-issued JWTs. Deactivate an account when access must be blocked.

TOTP enrollment exposes the secret only during setup. Store recovery codes separately. The implementation encrypts enrollment secrets using key material associated with `SECRET_KEY`; back up configuration and database together. Losing or casually rotating that key can make existing enrollment unreadable. Recovery codes are single use, and regenerating them replaces the previous set.

## SSO

Configure issuer, client credentials, exact callback URL and default role in Settings. Keep a working local recovery administrator. OIDC and OTP are separate stages: an OTP-enabled SSO account must finish OTP before receiving a full application session. Test account lifecycle and role mapping before broad use.

## Models and execution

AI Models configures the built-in runner's provider endpoint, credentials and model. A successful connection check does not prove an entire scan will succeed. External CLI clients have their own provider login and configuration.

Agent settings control concurrency, budgets, retry and execution policy. Keep the runner paused while preparing work. Resuming can execute already-queued tasks. Kill/stop controls interrupt work; inspect errors before retrying. Arbitrary command execution in a container remains powerful and is not a substitute for host or network isolation.

## MCP and audit

Enable HTTP MCP only when required, select the intended network policy and issue separate revocable keys for clients. AIDA session tokens, MCP API keys and model-provider credentials are different. See [AI CLI and MCP](AI_CLI_MCP.md).

Audit Log records supported account, command, configuration and access events. Preserve independent backups of logs. Do not include passwords, OTP secrets, recovery codes or full bearer tokens in tickets or screenshots.

Report branding and notification channels are configured in Settings. Sending a test notification proves delivery for that test, not correct execution of every scheduled scan.
