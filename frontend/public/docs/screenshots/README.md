# Interface screenshots

Captured from the running local AIDA installation on 9 November 2026 using the browser screenshot API. JPEG files are unaltered interface captures, not generated mockups.

| File | Screen |
| --- | --- |
| getting-started.jpg | Workspace checks and onboarding |
| task-board.jpg | Kanban columns, filters and paused runner |
| scheduler.jpg | Recurring-scan entry point and empty state |
| scan-runs.jpg | Execution history before the first scan run |

Empty lists reflect the installation at capture time. No sample tasks, schedules or scans were created. Screenshots omit credential pages and target-specific findings.

Canonical images live in assets/docs/screenshots. Run `npm run docs:sync` in frontend after changing guides or screenshots; it refreshes the frontend-only build copies. Source Markdown uses relative image paths; the in-app renderer maps them to /docs/screenshots/.

AppSec captures (`appsec-overview.jpg`, `appsec-findings.jpg`, `appsec-coverage.jpg`) show a synthetic source fixture scanned on 9 November 2026. Unlike the empty network-scan screenshots, these contain real AppSec analysis results from intentionally unsafe test code. No target network scanning or external AI invocation was performed.
