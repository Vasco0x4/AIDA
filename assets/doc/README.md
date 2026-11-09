# AIDA documentation images

This directory contains the historical documentation capture set. Its original provenance record describes real UI screenshots from an isolated smoke deployment with synthetic Assessments, targets, findings, commands and accounts. They are not mockups. These historical captures were not regenerated during the UTC/interface update; newer screenshots accompany that release report.

## Capture workflow

- `frontend/scripts/capture_docs.cjs`: login, OTP enrollment/challenge, recovery-code login and Users.
- `frontend/scripts/capture_all_docs.cjs`: main pages, Settings tabs and six MCP client snippets.
- `verification/seed_docs_demo.py`: disposable test-database data using Example Organization, Demo Assessments, `.example.test` hosts and `192.0.2.0/24` addresses.

The historical capture viewport was 1440 × 1000 with full-page images. Real targets were not scanned for that set. Do not substitute production credentials or customer data when regenerating documentation.

## Image groups

| Group | Files / purpose |
| --- | --- |
| Main workflow | `dashboard.png`, `dashboard-full.png`, `assessments.png`, `assessment-detail-full.png`, `scan-runs.png`, `commands.png`, `task-board.png`, `subdomain-takeover.png`, `users.png` |
| Settings | `settings-general.png`, `settings-tools.png`, `settings-notifications.png`, `settings-ai-models.png`, `settings-knowledge.png`, `settings-agents.png`, `settings-scheduler.png`, `settings-reports.png`, `settings-sso.png`, `settings-audit.png`, `settings-about.png`, `settings-mcp.png` |
| OTP | `otp-enrollment.png`, `otp-recovery-codes.png`, `otp-security.png`, `otp-login.png`, `users-otp.png` |
| MCP clients | `mcp-client-claude-code.png`, `mcp-client-codex.png`, `mcp-client-gemini.png`, `mcp-client-cursor.png`, `mcp-client-claude-desktop.png`, `mcp-client-generic.png` |

## Redaction and reuse

The capture record states that enrollment secrets were replaced with `REDACTED_DEMO_SECRET`, recovery codes with placeholders, and disposable MCP keys with `REDACTED_DEMO_KEY` before screenshots. OTP QR codes were also blurred. Disposable MCP keys were revoked after capture. The real flow ran in the isolated environment; redaction was applied to its visible output.

When regenerating images, replace textual secrets rather than relying on blur. Inspect the entire image, including modal content, snippets, audit details and query parameters. Revoke disposable credentials and clean up test accounts afterward. Configuration screenshots do not prove successful external model-provider authentication or completion.

Older images such as `mcp.png`, `workspace-view.png`, `finding-card-example.png`, `command-approval-*.png`, `command-history.png`, `context-upload.png`, `credentials-management.png`, `recon-data.png`, `import-scans.png`, `new-assessment-button.png`, `assessment-creation.png` and `system-overview.png` are outside that historical main/settings/OTP/MCP capture set. Verify provenance and redaction before reusing them.
