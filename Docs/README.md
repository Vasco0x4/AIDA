# AIDA documentation

Start with the workflow you need. This documentation describes the extended local edition, not only upstream AIDA.

| Guide | Purpose |
| --- | --- |
| [Quick Start](QUICK_START.md) | Install this edition with ./start.sh and preserve data during updates |
| [Product guide](PRODUCT_GUIDE.md) | Assessments, tasks, schedules, results and troubleshooting |
| [Kanban and Scheduler](KANBAN_SCHEDULER.md) | Task states, UTC offsets, recurring scans and controls |
| [Application Security](APPSEC.md) | Source snapshots, baseline rules, AI review, findings and reports |
| [Administration](ADMIN_GUIDE.md) | Roles, account security, model settings and audit |
| [Operations](OPERATIONS.md) | The Mac mini deployment, backups, startup and rollback |
| [AI CLI and MCP](AI_CLI_MCP.md) | Client configuration, authentication and diagnostics |
| [Architecture](LOCAL_ARCHITECTURE.md) | Components, execution boundaries and data flows |
| [Upstream comparison](UPSTREAM_COMPARISON.md) | What differs from Vasco0x4/AIDA and what this session changed |
| [Installation](INSTALLATION.md) | General installation reference |
| [MCP tools](MCP_TOOLS.md) | Tool reference |
| [Recurring scan implementation](RECURRING_SCAN_RUNS.md) | API and data model details |

The active Mac mini application is served on port 31337. Use Quick Start for this edition’s launcher and Operations for the existing Mac mini configuration. The deployment uses its own Compose project and persistent volumes.

Legacy filenames ending in `_RU.md` remain as English navigation pointers so older links still work. Their original contents are retained in the deployment backup.

## Illustrated guides

The Product guide and Kanban and Scheduler guide include real interface screenshots captured on 9 November 2026. See [screenshot notes](../assets/docs/screenshots/README.md) for provenance and maintenance instructions. The same images are available in the in-app User guide.
