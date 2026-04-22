<p align="center">
  <img src="./assets/banner1.png" alt="AIDA Banner" width="100%">
</p>
<h1 align="center">AI-Driven Security Assessment</h1>

<p align="center">
  <strong>Give your AI the power of 400+ pentesting tools. Let it hack (legally).</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#why-aida-exists">Why AIDA</a> •
  <a href="Docs/INSTALLATION.md">Installation</a> •
  <a href="Docs/USER_GUIDE.md">User Guide</a> •
  <a href="Docs/ARCHITECTURE.md">Architecture</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-AGPL_v3-blue" alt="License">
  <img src="https://img.shields.io/badge/MCP-Compatible-green" alt="MCP">
  <img src="https://img.shields.io/badge/Container-aida--pentest-orange" alt="aida-pentest">
  <img src="https://img.shields.io/badge/Version-1.1.0-purple" alt="Version">
</p>

---

## What is AIDA?

**AIDA** connects AI assistants to a real pentesting environment. Instead of just *talking* about security testing, your AI can actually *do* it.

Here's the deal:
-  **Your choice of pentesting container** — use the built-in `aida-pentest` (~2 GB, starts automatically, covers all the essential tools) or bring your own [Exegol](https://github.com/ThePorgs/Exegol) container (400+ tools, ~20-40 GB). You pick at first launch — and can switch anytime.
-  **MCP integration** that works with *any* AI client (Claude, Gemini, GPT, Antigravity...)
-  **Web dashboard** to track findings, commands, and progress
-  **Structured workflow** from recon to exploitation

Think of it as giving your AI a fully-equipped hacking lab and a notebook to document everything.

<p align="center">
  <img src="./assets/view.png" alt="AIDA Dashboard" width="800">
</p>

---



## Why AIDA Exists

Modern AI assistants know pentesting tools, techniques, and vulnerability classes—**but they can't execute them.**

Without execution capabilities, security testing becomes a tedious back-and-forth: you ask the AI for a command, copy it to your terminal, wait for results, paste the output back, and repeat. Traditional scanners like Burp Suite run fixed patterns and can't adapt to specific tech stacks or chain multi-step exploits.

**AIDA changes this** by connecting AI directly to a professional pentesting environment:

- 🔧 **Direct Execution** - Built-in pentesting environment (nmap, sqlmap, ffuf, nuclei...)
- 🧠 **Persistent Memory** - Full context maintained across sessions in structured database
- 📝 **Auto Documentation** - Findings tracked as cards with severity, proof, and technical analysis
- ⛓️ **Attack Chains** - AI connects dots between discoveries to build multi-step exploits
- 🎯 **Adaptive Testing** - Methodology adjusts based on findings, not fixed patterns

**Result:** Your AI becomes an autonomous security researcher, not just a consultant.

---

##  Video Demo

<p align="">
  <a href="https://www.youtube.com/watch?v=yz6ac-y4g08">
    <img src="https://img.youtube.com/vi/yz6ac-y4g08/maxresdefault.jpg" alt="AIDA Demo Video" width="70%">
  </a>
</p>

---

## System Requirements

### Supported Platforms
- **macOS** (Intel & Apple Silicon)
- **Linux** (Ubuntu, Debian, RHEL, Fedora, Arch, and derivatives)
- **Windows** (Untested)

---

## Quick Start

### Prerequisites

- **Docker Desktop** - To run the platform
- **An AI Client** - Claude Desktop, Claude Code, Gemini CLI, Antigravity... pick your favorite

```bash
# Clone & start
git clone https://github.com/Vasco0x4/AIDA.git
cd AIDA
./start.sh

# Open the dashboard
open http://localhost:31337
```

> **Contributors:** use `./start.sh --dev` for Vite hot reload on `localhost:5173`.
> **LAN access:** use `./start.sh --lan` to share with your team.

### Connect Your AI

Now hook up your AI client.

**Recommended: AIDA CLI (Claude Code or Kimi)**

The easiest way to get started is using the AIDA CLI wrapper, which supports both Claude Code and Kimi CLI:

```bash
# Auto-detect available CLI (Claude or Kimi)
python3 aida.py --assessment "test"

# Force a specific CLI
python3 aida.py --assessment "test" --cli claude
python3 aida.py --assessment "test" --cli kimi

# Auto-approve all actions
python3 aida.py --assessment "test" --yes
```

You can also use your own API keys (Claude only).

**Alternative: Import MCP tools into your AI client**

Here's Claude Desktop as an example:

**Default config path (macOS):**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```
**MCP config:**

```json
{
  "mcpServers": {
    "aida-mcp": {
      "command": "/bin/bash",
      "args": [
        "/absolute/path/to/AIDA/start_mcp.sh"
      ]
    }
  }
}
```

> **Full setup for all AI clients** → [INSTALLATION.md](Docs/INSTALLATION.md)

### First Assessment

1. Create an assessment in the web UI
2. Start your AI client
3. Inject the pre prompt. 
4. Tell it: *"Load assessment 'Acme' and start it"*
5. Watch it go

---

## UI-Initiated Scans (headless agent)

In addition to the CLI flow above, you can kick off a fully headless Claude
session directly from the assessment page. The agent runs inside the backend
container, uses the same MCP server, and streams every `thinking` / `tool_use`
/ `tool_result` event into a live transcript in the UI. You can stop the run
at any time, inspect past runs, and pick a specific model (Sonnet 4.6 / Opus
4.7 / Haiku 4.5).

This path auth'es against your **Max subscription** via an OAuth token — no
API key required, no extra per-token billing.

**One-time setup:**

1. On the host (not inside the container) generate a token:
   ```bash
   claude setup-token
   ```
   It'll open a browser, ask you to sign in, and print a long `sk-ant-oat01-…`
   string.

2. Paste it into `backend/.env`:
   ```ini
   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
   ```

3. (Re)start the stack:
   ```bash
   ./start.sh
   ```

Then open any assessment → **AI Scans** panel → *New scan* → describe the
goal and hit *Start*. Leave the field blank and you get a scripted mock run
— handy for demoing the panel without credentials.

> Behind the scenes the agent runs as a non-root user inside the container
> (claude CLI refuses `--dangerously-skip-permissions` under root) and talks
> to the `aida-pentest` container through the same docker socket proxy the
> rest of the backend uses.

---

## Works With Any AI

AIDA uses the **Model Context Protocol (MCP)** - an open standard. If your AI client supports MCP, it works with AIDA.

| AI Client           | Status      | Setup |
|---------------------|-------------|-------|
| **Claude Code**     | Recommended | Via `aida.py` (automatic) |
| **Kimi CLI**        | Recommended | Via `aida.py` (automatic) |
| **External API**    | Recommended | Via `aida.py --base-url` |
| **Claude Desktop**  | Works       | Manual MCP import |
| **ChatGPT Desktop** | Works       | Manual MCP import |
| **Gemini CLI**      | Works       | Manual MCP import |
| **Antigravity**     | Works       | Manual MCP import |

> **Full setup for all AI clients** → [INSTALLATION.md](Docs/INSTALLATION.md)


---

## MCP Tools

The AI gets access to specialized tools:

```
ASSESSMENT
   load_assessment    - Load and start working
   update_phase       - Document progress

CARDS
   add_card          - Create findings/observations/info
   list_cards        - View all cards
   update_card       - Modify cards
   delete_card       - Remove cards

RECON
   add_recon_data    - Track discovered assets
   list_recon        - View recon data

EXECUTION
   execute           - Run any command in the pentesting container
   scan              - Quick scans (nmap, gobuster, ffuf...)
   subdomain_enum    - Find subdomains
   ssl_analysis      - Check SSL/TLS
   tech_detection    - Identify tech stack
   tool_help         - Get tool documentation

CREDENTIALS
   credentials_add   - Store credentials
   credentials_list  - List stored creds
```

> **Full tool documentation** → [MCP_TOOLS.md](Docs/MCP_TOOLS.md)

---

## Project Structure

```
AIDA/
├── backend/              # FastAPI + MCP Server
│   ├── api/             # REST endpoints
│   ├── mcp/             # MCP server + tools
│   ├── models/          # Database models
│   └── services/        # Business logic
├── frontend/            # React dashboard
│   ├── src/pages/       # Dashboard, Assessments, Settings...
│   └── src/components/  # Reusable UI components
├── pentest/             # Built-in pentesting container (aida-pentest)
│   └── Dockerfile       # Ubuntu 22.04 + nmap, ffuf, gobuster, sqlmap...
├── Docs/                # Documentation and AI methodology
├── aida.py              # CLI launcher
├── start.sh             # Start the platform (prod default, --dev, --lan)
├── stop.sh              # Stop all services (data preserved)
├── restart.sh           # Restart all services
├── docker-compose.yml   # Dev infrastructure
├── docker-compose.prod.yml  # Prod overrides (Nginx reverse proxy)
└── docker-compose.hub.yml   # Standalone — pre-built Docker Hub images
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [**INSTALLATION.md**](Docs/INSTALLATION.md) | Complete setup guide - all AI clients |
| [**USER_GUIDE.md**](Docs/USER_GUIDE.md) | How to use the platform |
| [**ARCHITECTURE.md**](Docs/ARCHITECTURE.md) | Technical deep dive + diagrams |
| [**MCP_TOOLS.md**](Docs/MCP_TOOLS.md) | All MCP tools explained |


---

## What's New in v1.1.0

- **Full authentication system** — JWT-based auth, admin/user roles, first-run setup wizard, API key for CLI/MCP
- **PDF report generation** — Export assessments as professional reports with one click
- **CVSS 4.0 scoring** — Automatic score calculation directly on findings cards
- **Attack timeline** — Auto-generated event timeline per assessment
- **Notifications** — Telegram, Slack, and Email alerts with optional PDF attachment
- **Assessment templates** — Start from predefined methodologies
- **`aida-pentest` container** — Built-in lightweight pentesting environment (~2 GB), no Exegol required
- **LAN / production mode** — Nginx reverse proxy, Docker Hub images (`./start.sh --lan`)
- **New MCP tools** — `python_exec` and `http_request` for advanced AI workflows
- **Security hardening** — Docker socket proxy, path traversal prevention, `shlex.quote` sanitization, PostgreSQL bound to localhost only, auto-generated secret key
- **Cross-assessment findings view** — Aggregate and filter all findings across every assessment

> **⚠️ Deployment note:** Run locally or on your LAN. Do NOT expose the web interface to the public internet without additional hardening (HTTPS, firewall, strong credentials in `.env`).

Report bugs and request features: [GitHub Issues](https://github.com/Vasco0x4/AIDA/issues)

---

## Contributing

AIDA is actively developed. Want to contribute?

**Planned Features:**

- Frontend redesign with flat, professional UI
- OWASP testing guidelines integration
- Enhanced phase workflow system
- Advanced CLI wrapper capabilities

---

Need help? Contact **vasco0x4** on Discord.

---

## License

**AGPL v3** - Free and open source.

You can use, modify, and distribute AIDA freely. If you modify and deploy it (including as a network service), you must open source your changes under AGPL v3.

**Commercial licensing available** for organizations that need proprietary modifications.
Contact: **Vasco0x4@proton.me**

---

## Credits

- [**Anthropic MCP**](https://modelcontextprotocol.io/) - The protocol that makes this possible
- The security community for all the amazing open-source tools
- [**Exegol**](https://github.com/ThePorgs/Exegol) - Supported as an alternative container for advanced users

---
<p align="center">
  <a href="https://github.com/Vasco0x4/AIDA">⭐ Star on GitHub</a> •
  <a href="https://github.com/Vasco0x4/AIDA/issues">Report Bug</a> •
  <a href="mailto:Vasco0x4@proton.me">Contact</a>
</p>
