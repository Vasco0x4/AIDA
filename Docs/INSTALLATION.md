# AIDA Installation Guide

Get AIDA running in under a minute.

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| **Docker Desktop** | Latest | `docker --version` |

Also needed for AI integration:
- **Python** 3.10+ (`python3 --version`) — for the MCP server and CLI
- **An AI client** that supports MCP — Claude Code, Codex, Kimi, or Qwen recommended (see Step 5)

> **Exegol users:** AIDA uses `aida-pentest` by default. You can switch to Exegol anytime in Settings.

---

## Platform Setup

### Step 1: Clone & Start

```bash
git clone https://github.com/Vasco0x4/AIDA.git
cd AIDA
./start.sh
```

Open **http://localhost:31337** — local mode (Nginx, plain HTTP) by default.

The backend image is pulled from Docker Hub. The frontend (Nginx) is always built locally so that `VITE_API_URL=/api` is correctly baked in at compile time.

This starts:
- **PostgreSQL** on port `5432` - The database (localhost only)
- **Backend API** on port `8000` - FastAPI server (localhost only)
- **Frontend (Nginx)** on port `31337` - Web dashboard
- **aida-pentest** - Built-in pentesting container (~2 GB)

> **Sharing on a network or deploying with a domain?** See [`TLS.md`](TLS.md)
> for `./start.sh --lan` (HTTPS over your LAN) and `./start.sh --domain`
> (HTTPS with Let's Encrypt).

### Step 3: First-Run Setup

Open your browser to [http://localhost:31337](http://localhost:31337)

On the very first launch, AIDA shows a **setup wizard** to create the initial admin account. Pick a username and password — these are the credentials you'll use everywhere (web UI, CLI, MCP). Once submitted, you land on the dashboard.

> **Lost your password?** See [`Docs/RESET_PASSWORD.md`](RESET_PASSWORD.md).

---

## Step 4: Pentesting Container

AIDA supports two pentesting containers. You chose one during Step 2 — here's what to do next for each.

### Option 1 — aida-pentest (built-in)

If you selected `aida-pentest`, you're done. The container started automatically as part of `docker compose up` — no extra steps needed.

**Disk space:** ~2 GB.

**What's included:** nmap, ffuf, gobuster, sqlmap, nikto, dirb, hydra, whatweb, subfinder, dnsx, openssl + Python libs (impacket, scapy, pwntools, paramiko, requests...) + SecLists wordlists.

This covers all the essential tools for a typical assessment. If you need additional tools, you can install them directly inside the container at any time:

```bash
docker exec -it aida-pentest bash
# then install whatever you need, e.g.:
apt-get install -y metasploit-framework
```

Or switch to Exegol (Option 2) if you want 400+ tools pre-installed out of the box.

### Option 2 — Exegol

If you selected Exegol (or want to switch to it), refer to the official documentation for installation and setup: https://docs.exegol.com

Then in AIDA Settings, make sure your default container is set to match your Exegol container name.
> **Switching containers:** You can change your container preference anytime in **Settings → Container**. This affects new assessments; existing ones keep their assigned container.

---

## Localhost Mode

For engagements where you want the LLM to operate directly on your host machine instead of inside a pentesting container, AIDA ships a **localhost** deployment mode.

> **This is a power-user feature.** Commands run with your user's privileges against your real filesystem. AIDA defaults to `closed` command approval in this mode so every command requires an explicit click in **Settings → Commands**, but you should still treat localhost mode with the same care as any remote root shell.

### Enable on setup

```bash
./start.sh --localhost    # switch to localhost mode (persisted)
./start.sh --container    # switch back to the pentest container (default)
```

The selected mode is saved in `.aida/deployment-mode` and used on every subsequent `./start.sh` until you change it.

### What changes

| | Container mode (default) | Localhost mode |
|---|---|---|
| Command target | `aida-pentest` (or Exegol) via `docker exec` | Your host, via the `aida-host-agent` daemon |
| Default approval mode | `open` | `closed` — every command requires approval |
| Workspace location | `~/.aida/workspaces/` bind-mounted into the pentest container | `~/.aida/workspaces/` directly on the host |
| Services started | postgres, backend, frontend, docker-proxy, aida-pentest | postgres, backend, frontend (no pentest / proxy) |

### Architecture

The Dockerized backend cannot exec commands on the host directly, so localhost mode ships a small daemon (`tools/host_agent.py`) that runs **on the host** and listens on a Unix socket. `docker-compose.localhost.yml` does an **identity bind-mount** of `~/.aida` into the backend container so every path — socket, token, workspaces — resolves to the same absolute path in both views. That way workspace paths written by the LLM (e.g. `nmap -oN ~/.aida/workspaces/foo/nmap.txt`) work natively on the host without any translation.

```
host                                            backend container
──────────────                                  ──────────────────
~/.aida/host-agent.sock          <—identity—>   ~/.aida/host-agent.sock
~/.aida/host-agent.token  (0600) <—identity—>   ~/.aida/host-agent.token  (RO)
~/.aida/workspaces/              <—identity—>   ~/.aida/workspaces/
```

Every request over the socket is authenticated with a shared-secret token (generated on first `./start.sh --localhost`, stored at `~/.aida/host-agent.token`, mode 0600). Commands execute with the user's own UID/GID, so anything the LLM runs has whatever privileges your shell has — no more, no less.

### Host tool prerequisites

Because commands run on the host instead of inside `aida-pentest`, **you must install pentest tooling yourself.** The LLM will attempt to `apt-get`/`pipx install` missing tools on the fly (subject to command approval), but starting with the essentials in place makes the first assessment smoother.

**Baseline (required):**

```bash
# Debian / Ubuntu / Mint / Kali
sudo apt update && sudo apt install -y \
    bash curl wget git jq openssl netcat-openbsd \
    python3 python3-pip python3-venv \
    nmap dnsutils whois

# Arch
sudo pacman -S --needed bash curl wget git jq openssl gnu-netcat \
    python python-pip nmap bind whois

# Fedora / RHEL
sudo dnf install -y bash curl wget git jq openssl nmap-ncat \
    python3 python3-pip nmap bind-utils whois
```

**Recommended pentest tools (install what you use):**

```bash
# On Kali these are all preinstalled. Elsewhere:

# Web content discovery
sudo apt install -y gobuster ffuf wfuzz

# Web scanners
sudo apt install -y nikto sqlmap wpscan whatweb

# Auth / credential attacks
sudo apt install -y hydra medusa john hashcat

# Subdomain / recon (Go tools — install via `go install`)
go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install github.com/projectdiscovery/httpx/cmd/httpx@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install github.com/OJ/gobuster/v3@latest        # if not in apt
go install github.com/ffuf/ffuf/v2@latest          # if not in apt
```

**Python libraries the LLM commonly imports** (into the system `python3` — the host-agent invokes it directly, not a venv):

```bash
# System-wide (Debian family — needs --break-system-packages on 24.04+ or use pipx)
sudo apt install -y python3-requests python3-bs4 python3-lxml python3-dnspython \
    python3-cryptography python3-paramiko python3-impacket

# Or via pip if your distro is older
pip3 install --user requests beautifulsoup4 lxml dnspython cryptography paramiko impacket
```

**Sanity check** — run this to see what's already there before you start an assessment:

```bash
for t in nmap gobuster ffuf nikto sqlmap hydra dig whois curl python3; do
  command -v "$t" >/dev/null && echo "[OK]  $t" || echo "[MISS] $t"
done
```

### Verifying the agent

```bash
# Daemon status
cat ~/.aida/host-agent.pid
ps -p "$(cat ~/.aida/host-agent.pid)"

# Logs
tail -f ~/.aida/host-agent.log

# Socket probe (requires nc with -U)
echo '{"token":"'"$(cat ~/.aida/host-agent.token)"'","method":"ping"}' \
  | nc -U ~/.aida/host-agent.sock
```

### Stopping

`./stop.sh` terminates the host-agent daemon and cleans up its socket automatically. You can also kill it manually:

```bash
kill "$(cat ~/.aida/host-agent.pid)"
rm -f ~/.aida/host-agent.sock
```

---

## Step 5: Connect Your AI Client

Now you need to hook up AIDA to your AI assistant via MCP.

### Which AI Client Should I Use?

| AI Client | Recommendation | Setup Method |
|-----------|----------------|--------------|
| **Claude Code** | Recommended | Use `aida.py` CLI (automatic) |
| **OpenAI Codex CLI** | Recommended | Use `aida.py --cli codex` (automatic) |
| **Kimi Code CLI** | Recommended | Use `aida.py` CLI (automatic) |
| **Qwen Code CLI** | Recommended | Use `aida.py --cli qwen` (automatic) |
| **Vertex AI / External API** | Recommended | Use `aida.py` with flags |
| **Antigravity** | Works | Manual MCP import (run `aida.py` once first) |
| **Gemini CLI** | Works | Manual MCP import (run `aida.py` once first) |
| **Claude Desktop** | Works | Manual MCP import (run `aida.py` once first) |

> **External MCP clients (Claude Desktop, Cursor, Gemini CLI, etc.)** require running `aida.py` once before connecting. This authenticates against the backend and stores a long-lived API key in `.aida/api-key`. Every subsequent connection reuses it silently — no further login needed.

---

## AIDA CLI — Claude Code, Codex, Kimi & Qwen

The `aida.py` CLI is the recommended way to launch AIDA. It **auto-detects** which AI client you have installed (Claude Code, OpenAI Codex CLI, Kimi Code CLI, or Qwen Code) and configures everything automatically — MCP server, workspace, preprompt, and authentication.

### Authentication (First Launch)

The first time you run `aida.py`, it prompts for your AIDA credentials (the ones you created in the setup wizard) and stores a **long-lived API key** in `.aida/api-key` (`chmod 600`, valid 1 year). Every subsequent launch reuses this key silently — no more prompts.

The same key is used by the MCP server to authenticate against the backend, so it works for both the launcher and AI tool calls. To force a re-login, delete `.aida/api-key`.

For non-interactive use (CI, scripts), set `AIDA_TOKEN` in the environment to bypass the prompt entirely.

### Common Options

| Flag | Description |
|------|-------------|
| `-a`, `--assessment NAME` | Load a specific assessment directly |
| `--cli claude\|codex\|kimi\|qwen\|auto` | Select a CLI (default: Claude Code; use `auto` for detection) |
| `-m`, `--model MODEL` | Override the model used |
| `--preprompt FILE` | Use a custom preprompt file |
| `-y`, `--yes` | Auto-approve all AI actions |
| `--no-mcp` | Disable MCP server (for testing) |
| `--debug` | Enable debug output |
| `-q`, `--quiet` | Minimal startup output |
| `PROMPT...` | Pass an initial prompt directly |

---

## Claude Code

**Claude Code is recommended** because the AIDA CLI does everything for you.

### Prerequisites

You MUST have Claude Code installed and logged in:

```bash
# Install Claude Code
curl -fsSL https://claude.ai/install.sh | bash
```

### Launch AIDA

```bash
# Interactive — select assessment from list
python3 aida.py

# Direct launch with assessment name
python3 aida.py --assessment "MyTarget"

# With custom model
python3 aida.py --assessment "MyTarget" --model claude-opus-4-6

# Force Claude if both CLIs are installed
python3 aida.py --assessment "MyTarget" --cli claude

# Auto-approve all actions (no confirmation prompts)
python3 aida.py --assessment "MyTarget" --yes
```

The CLI automatically:
- Generates MCP config
- Sets working directory to assessment workspace
- Injects the pentesting methodology preprompt
- Configures all tools

You can verify if the MCP server is correctly loaded using `/mcp`

<img src="../assets/doc/mcp.png" alt="MCP Server" width="33%" />

**That's it. You're ready.**

---

## OpenAI Codex CLI

Codex is fully supported through its documented CLI configuration surfaces.
AIDA injects the preprompt as one-run developer instructions, sets the
assessment workspace, and adds the AIDA MCP server without modifying your
global `~/.codex/config.toml`.

### Prerequisites

```bash
npm install -g @openai/codex
codex login
```

### Launch AIDA with Codex

```bash
# Force Codex explicitly
python3 aida.py --assessment "MyTarget" --cli codex

# Select a model available to your Codex account
python3 aida.py --assessment "MyTarget" --cli codex --model gpt-5.4

# Pass an initial task
python3 aida.py --assessment "MyTarget" --cli codex \
  "Load the assessment and continue reconnaissance"
```

By default, Codex runs with `workspace-write` sandboxing and `on-request`
approvals. AIDA MCP commands still follow the command approval mode configured
in the AIDA dashboard.

`--yes` maps to Codex's full-access bypass flag. It disables Codex approvals
and sandboxing for that session, so use it only in a trusted, isolated
environment:

```bash
python3 aida.py --assessment "MyTarget" --cli codex --yes
```

Inside Codex, use `/mcp` to verify that `aida-mcp` is active.

---

## Kimi Code CLI

**Kimi Code CLI** is fully supported as an alternative to Claude Code. The AIDA CLI handles the full setup automatically.

> **Note:** Kimi Code CLI is the Node.js successor of the legacy Python `kimi-cli`, which is being phased out. If you still have the old one, run `kimi migrate` after installing to carry over your config, MCP servers, and session history.

### Prerequisites

Install Kimi Code CLI:

```bash
curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash
# or
npm install -g @moonshot-ai/kimi-code
```

Then log in with `/login` (or `kimi login`) and configure Kimi Code CLI according to its documentation.

### Launch AIDA with Kimi

```bash
# Auto-detect (picks Kimi if Claude isn't installed)
python3 aida.py --assessment "MyTarget"

# Force Kimi explicitly
python3 aida.py --assessment "MyTarget" --cli kimi

# With a specific model
python3 aida.py --assessment "MyTarget" --cli kimi --model kimi-k2

# Yolo mode — auto-approve everything
python3 aida.py --assessment "MyTarget" --cli kimi --yes
```

The CLI automatically:
- Writes project instructions with assessment context to `.kimi-code/AGENTS.md` in the workspace
- Configures the MCP server for Kimi (`.kimi-code/mcp.json` in the workspace)
- Sets the working directory to the assessment workspace

> **Note:** `--yes` maps to `--yolo` in Kimi Code CLI, which auto-approves all tool calls. Use with caution. When a non-interactive prompt is passed, `--yolo` is omitted because Kimi Code CLI auto-approves tool calls in that mode by default.

---

## Vertex AI / External API

If you're using Vertex AI or another external API (Claude only):

```bash
python3 aida.py --assessment "MyTarget" \
  --base-url "https://YOUR-VERTEX-ENDPOINT" \
  --api-key "YOUR-API-KEY" \
  --model claude-sonnet-4-5-20250929
```

Same benefits as Claude Code, but routing through your own API endpoint.

---

## Other AI Clients (Manual MCP Import)

For Antigravity, Gemini CLI, Claude Desktop, or ChatGPT, you need to manually configure the MCP server.

> ⚠️ **Authentication first** — The MCP server reads its API key from `.aida/api-key`, which is created the first time you run `aida.py`. **Run `python3 aida.py` once before starting your external client**, log in when prompted, and you can `Ctrl+C` immediately after — the key is now cached and any external MCP client will use it.

**The process:**

1. Run `python3 aida.py` once to log in and generate `.aida/api-key`
2. Import the MCP server config (see examples below)
3. Copy the preprompt from `Docs/PrePrompt.txt`
4. Paste it into your AI client when starting an assessment

> Antigravity works great if you select Claude. Gemini is OK. Any MCP-compatible client should work.
>
> **Prefer Claude Code, Codex, Kimi, or Qwen?** Use `aida.py` instead — it handles all of this automatically.

### Config Paths

**Antigravity:** MCP settings (UI)

**Gemini CLI:** `~/.gemini/settings.json`

**Claude Desktop:**
* **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
* **Linux:** `~/.config/Claude/claude_desktop_config.json`

**ChatGPT Desktop:**
* **macOS:** `~/Library/Application Support/ChatGPT/mcp_config.json`

### MCP Configuration

Add this to your config file (replace `/absolute/path/to/AIDA/` with your actual path):

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

⚠️ **Important:** Replace `/absolute/path/to/AIDA/` with your actual AIDA directory path.

**After MCP setup:**
- Restart your AI client
- Copy the preprompt from `Docs/PrePrompt.txt` and paste it into your AI client
- Say to the AI: `Load assessment "your-assessment-name" and start it`

---

## Verify Installation

Run through this checklist:

| Check | How | Expected |
|-------|-----|----------|
| Platform running | http://localhost:31337 | Dashboard loads |
| API healthy | http://localhost:8000/health | `{"status": "healthy"}` |
| Database connected | Check backend logs | No connection errors |
| Pentest container | `docker ps \| grep aida-pentest` or `docker ps \| grep exegol` | Container running |
| MCP server | Check AI client | AIDA tools visible |


## Platform Scripts

One script, three modes:

| Command | Description |
|---------|-------------|
| `./start.sh` | Local — `http://localhost:31337`, no TLS (default) |
| `./start.sh --lan` | LAN — `https://<LAN_IP>`, Caddy + self-signed cert |
| `./start.sh --domain X.Y` | Public — `https://X.Y`, Caddy + Let's Encrypt |
| `./start.sh --dev` | Dev — `http://localhost:5173`, Vite hot reload |
| `./stop.sh` | Stop all services — data is preserved |
| `./restart.sh` | Restart all services and wait for health checks |

Switching between modes is safe — `start.sh` tears down the old stack first
and your Postgres data volume is never touched.

```bash
# Local-only (default)
./start.sh

# Share on your network (HTTPS with self-signed cert)
./start.sh --lan

# Deploy with a real domain (Let's Encrypt)
./start.sh --domain aida.example.com --email admin@example.com

# Development (Vite hot reload)
./start.sh --dev

# Stop / restart
./stop.sh
./restart.sh
```

> Full TLS reference → [`TLS.md`](TLS.md)

---

## Troubleshooting

### "Backend not reachable" in the web UI (default `./start.sh`)

This means the frontend loaded but can't reach the API. In default mode, Nginx proxies `/api` requests to the backend container over Docker's internal network. If that path is broken, the UI shows this banner even though the backend is running.

**Step 1 — Check the backend is actually healthy:**
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

**Step 2 — Check Nginx can reach the backend:**
```bash
docker logs aida_frontend --tail 20
# Look for "connect() failed" or "no live upstreams" — confirms a network issue
```

**Step 3 — Ubuntu: check Docker bridge networking (most common cause)**

On Ubuntu, `ufw` with `DEFAULT_FORWARD_POLICY=DROP` blocks Docker's inter-container traffic. This only affects prod mode (which uses Nginx as a proxy between containers) — dev mode works because the browser hits `localhost:8000` directly.

Check the current policy:
```bash
sudo grep DEFAULT_FORWARD_POLICY /etc/default/ufw
```

If it says `DROP`, fix it:
```bash
sudo sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
sudo ufw reload
```

Then restart the stack:
```bash
./stop.sh && ./start.sh
```

> **Why does `--dev` work but default mode doesn't?**  
> In dev mode, `VITE_API_URL=http://localhost:8000/api` — the browser calls the backend directly via the published host port. No Docker networking is needed. In default mode, Nginx (in the frontend container) must route to the backend container over `aida-network`. If the Docker bridge forward policy is `DROP`, that intra-container traffic is blocked.

**Step 4 — Verify containers are on the same network:**
```bash
docker network inspect aida-network --format '{{range .Containers}}{{.Name}} {{end}}'
# Should list: aida_backend aida_frontend aida_postgres aida_docker_proxy
```

---

### Frontend timeout during `./start.sh` ("TIMEOUT" then exits with error)

The Nginx build can take 2–5 minutes on first run (npm install + Vite build). If you see a timeout, re-run `./start.sh` — it will detect the already-running containers and skip the startup.

---

### Port 31337 already in use

```bash
# Find what's using it
sudo ss -tlnp | grep 31337
# Or
sudo lsof -i :31337

# Kill the process or change AIDA_PORT in start.sh
```

---

### Docker pull fails (no internet / private mirror)

`start.sh` automatically falls back to building the backend from source if the Hub pull fails. The frontend is always built locally regardless. A full build takes ~5 minutes on first run.

---

## Next Steps

- [**User Guide**](USER_GUIDE.md) - Learn how to use the platform
- [**MCP Tools Reference**](MCP_TOOLS.md) - All available tools for your AI
- [**TLS Setup**](TLS.md) - LAN sharing and Let's Encrypt for public domains
- [**Architecture**](ARCHITECTURE.md) - Technical deep dive

---

## CLI Quick Reference

```bash
# List available assessments and pick one interactively
python3 aida.py

# Load a specific assessment (Claude Code by default)
python3 aida.py -a "MyTarget"

# Auto-detect an installed CLI
python3 aida.py -a "MyTarget" --cli auto

# Force Claude Code
python3 aida.py -a "MyTarget" --cli claude

# Force OpenAI Codex CLI
python3 aida.py -a "MyTarget" --cli codex

# Force Kimi Code CLI
python3 aida.py -a "MyTarget" --cli kimi

# Auto-approve all actions
python3 aida.py -a "MyTarget" --yes

# Custom preprompt
python3 aida.py -a "MyTarget" --preprompt /path/to/custom-preprompt.txt

# External API (Claude only)
python3 aida.py -a "MyTarget" --base-url "https://..." --api-key "..." --model claude-sonnet-4-5-20250929

# Pass an initial prompt
python3 aida.py -a "MyTarget" "Start from phase 1 and run reconnaissance"
```

---

## Need Help?

Need help? Contact **vasco0x4** on Discord.

- **GitHub Issues**: [Report bugs](https://github.com/Vasco0x4/AIDA/issues)
- **Email**: Vasco0x4@proton.me
