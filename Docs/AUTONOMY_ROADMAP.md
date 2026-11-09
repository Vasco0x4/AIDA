# AIDA → Autonomous Platform: Centralized Roadmap

Single source of truth for the autonomy upgrade. Every change tracks back to
one of the four epics below. Built and verified in the **isolated dev stack**
(`~/AIDA-dev`, ports 5433/8001/5174) — the main stack (`~/AIDA`) is never touched.

Status legend: ☐ not started · ◐ in progress · ☑ done & verified in dev.

---

## Where AIDA is today (verified by codebase audit)

- The backend is a **tool-server, not an agent**: it never calls an LLM. All
  intelligence is delegated to an *external* MCP client (Claude/Cursor/etc.)
  launched by `aida.py`. There is **no in-process agent loop, no model API
  layer, no background worker, and no task queue.**
- Rich data model already exists: `assessments`, `cards` (findings, CVSS 4.0),
  `recon_data`, `credentials`, `command_history`, `timeline_events` (an
  attack-chain log that is **not** yet rendered into reports), `asvs_requirements`.
- Command execution goes through a **human-approval gate** (`pending_commands`,
  modes open/filter/closed). This is a safety primitive we preserve and extend.
- Reports are **PDF-only** (WeasyPrint + Jinja). No screenshots, no Kill-Chain
  narrative section, no CVE/CWE/MITRE knowledge base (only ASVS v5 is baked in).
- Telegram is **outbound-only** (and its event hooks are never even called).
  No inbound bot control exists.
- Settings live in `platform_settings` (key/value) and `notification_configs`
  (per-channel JSONB). New schema is auto-provisioned at startup via
  `create_all()` + `_ensure_columns()` — no manual migration step.
- WebSocket is a ready broadcast hub — free real-time streaming of agent progress.

## Safety invariants (non-negotiable, enforced in code)

1. **Every autonomous task carries an explicit `authorized_scope`.** No scope →
   the agent refuses to act. Targets outside scope are blocked.
2. **Host-OS execution** (running outside the container, on the mac-mini host or
   a Kali box) is the most dangerous mode — it is **opt-in per task**, disabled
   by default, and clearly flagged in the UI and Telegram.
3. The **human-approval gate stays wired** for destructive/《filtered》commands even
   in autonomous mode. Autonomy ≠ removing the brakes.
4. The "offensive knowledge base" is a **research/reference layer** (public
   advisories, CVE metadata, methodology playbooks) — not an auto-exploit generator.

---

## Epic 1 — AI Model Integration (foundation)

Native, in-platform access to any OpenAI-compatible model + aggregators, so the
platform itself can reason (not just relay to an external CLI).

- ☑ `AIModelConfig` table + encrypted-at-rest API keys (Fernet from SECRET_KEY)
      — `models/ai_model_config.py`, `utils/crypto.py`
- ☑ OpenAI-compatible provider client (one client, configurable `base_url`)
      — `services/llm/provider.py`
- ☑ Provider presets: **OpenRouter, Moonshot/Kimi, Zhipu/GLM, OpenAI, DeepSeek,
      Anthropic(via OR), custom** — Anthropic-native adapter still TODO
- ☑ CRUD API + connectivity **/test** endpoint (authoritative 1-token chat check)
      — `api/ai_models.py`, `services/ai_model_service.py`. Verified in dev.
- ☐ Settings UI tab "AI Models" (add/select/test, choose default) — backend ready

## Epic 2 — Autonomous Agent Runtime + Kanban

- ☑ `Task` table = the unit of autonomous work (kanban columns as workflow
  stages: backlog → queued → running → needs_review → done/failed; `position`
  for ordering; `authorized_scope`; `execution_target` container|host)
      — `models/task.py`. Verified in dev.
- ☑ Task CRUD + move/reorder API (WebSocket broadcasts for live board)
      — `api/tasks.py`, `services/task_service.py`, `websocket/events.py`. Verified.
- ☑ In-process **agent runner**: asyncio loop in `main.py` lifespan pulling
  queued tasks, plan→act→observe over a safe tool set, streams AGENT_STEP over
  WebSocket, honors command-mode + scope gate. Pausable via `agent_runner_enabled`.
      — `services/agent/{runner,runtime,tools,scope}.py`. Verified end-to-end in dev
      (task auto-picked up → assessment+workspace created → model call → clean
      failure on invalid key). Needs a real API key to complete a live run.
- ☑ **Scope enforcer** (`services/agent/scope.py`) — hard safety gate, unit-tested
  (domains/wildcards/IPs/CIDRs/exclusions + filename false-positive fix).
- ◐ Host execution: gated (opt-in). Container path done; host path needs a
  host-side runner daemon (**Phase 2b**) — currently parks host tasks in
  needs_review with an explanation.
- ☐ `AgentRun` / `AgentStep` persistent log (reuse the `timeline_events` pattern)
- ☑ Kanban board page + `taskService.js` — `frontend/src/pages/Board.jsx`,
  `services/taskService.js`, route in `App.jsx`, nav in `Sidebar.jsx`. Native
  HTML5 drag-and-drop (no new dep), runner on/off toggle, new-task modal with
  scope + host-opt-in warning, live updates via WebSocket. `vite build` clean.
- ☑ **Dev frontend hot-reload**: dev compose now builds the Vite dev image
  (was serving the prebuilt prod nginx bundle). UI edits reflect live at :5174.

## Epic 3 — Offensive Knowledge + Kill-Chain Reports

- ☑ Artifact/screenshot store: `models/artifact.py` + `api/artifacts.py`
  (upload/list/serve/delete), bytes in DB, linkable to a card. Verified.
- ☑ Screenshots embedded in the PDF report per finding (Evidence blocks) —
  verified end-to-end (uploaded PNG appears in PDF).
- ☑ **Kill-Chain narrative** section: `timeline_events` wired into
  `report_service.py` + template + CSS, grouped by phase. Verified in PDF text.
- ☑ Agent auto-screenshot: `capture_screenshot` tool (scope-gated). Headless
  browser is now BAKED into the pentest image via **Playwright Chromium**
  (arm64-compatible; Ubuntu apt chromium is snap-only and Chrome has no
  linux/arm64 .deb, so Playwright is the route). Symlinked as `chromium` on PATH.
  Verified end-to-end from a freshly-recreated container: real screenshot of an
  in-scope URL stored as an artifact and embedded in the PDF; out-of-scope URL
  refused. Unlinked screenshots render in an "Evidence — Screenshots" appendix.
- ☑ Knowledge layer: `models/knowledge_entry.py` + `services/knowledge_service.py`
  + `api/knowledge.py` — 5 built-in methodology playbooks (seeded at startup) +
  live **NVD CVE ingestion** + search + agent `search_knowledge` tool. Verified
  (pulled real Grafana CVEs w/ CVSS + CWE).
- ☑ Markdown report export (machine-readable): `generate_markdown_report` +
  `GET /assessments/{id}/report/markdown` + a "Download Markdown" UI menu item.
  Verified (Summary + Kill Chain + Findings render).

## Epic 4 — Telegram Control + UX + Hardening

- ☑ Inbound Telegram bot (long-poll loop in lifespan): `services/telegram/bot.py`
  — `/task target|scope|title|[host]`, `/tasks`, `/board`, `/runner on|off`,
  `/status`. chat_id allowlist. Dormant until token + `telegram_bot_enabled`.
  Verified: `/task` creates a queued task; `/board` reports. Live push on task
  completion added to the runtime.
- ☑ Bot acts via the internal TaskService as the first admin user (no new
  privilege path). UI toggle: `TelegramBotToggle` in Settings → Notifications.
- ◐ Host execution: kept as an explicit human-in-the-loop path (host tasks park
  in needs_review). An autonomous host-command daemon was deliberately NOT built
  — an auto-exec-on-host backdoor is out of bounds even for a pentest tool.
- ◐ Optimization/UX polish — ongoing.
- ☑ **Test-and-fix loop** per increment (each verified in dev; scope enforcer
  self-caught + fixed a filename false-positive).
- ☑ QA sweep: fixed a pre-existing 500 — `system.py` read
  `settings.MAX_CONTEXT_FILE_SIZE` / `MAX_SOURCE_ZIP_SIZE` which were missing from
  `config.py` (both `/system/settings/*` endpoints crashed on a fresh DB). All
  settings + core endpoints now 200; no errors in logs.

---

## Build order (by dependency)

1. **Epic 1** (model layer) — everything reasoning-based depends on it. ← current
2. **Epic 2** (task model + runner) — needs Epic 1 to think.
3. **Epic 3** (reports/knowledge) — the runner produces this output.
4. **Epic 4** (Telegram/UX) — a control surface over Epics 1–3.

Parallelism note: shared files (`models/__init__.py`, `main.py`) are edited by
the foundation coherently in one place; independent leaf features (a report
template, the bot module, the board page) are the parts safe to fan out to
parallel agents later.
