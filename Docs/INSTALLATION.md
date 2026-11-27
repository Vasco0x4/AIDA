# AIDA Installation Guide

One command installs AIDA, a second one starts your first assessment.

- [Install](#install)
- [First login](#first-login)
- [Everyday commands](#everyday-commands)
- [Connect your AI](#connect-your-ai)
- [Pentesting container](#pentesting-container)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Contributing: dev mode](#contributing-dev-mode)

---

## Install

**You need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) or [OrbStack](https://orbstack.dev) on macOS, Docker Engine on Linux, and `git`. Windows works through WSL 2.

```bash
curl -fsSL https://raw.githubusercontent.com/Vasco0x4/AIDA/main/install.sh | bash
```

The installer:

1. checks that Docker is installed and running (it tells you what to do if not);
2. downloads AIDA into `~/AIDA`;
3. installs the `aida` command;
4. downloads the images (about 3 GB the first time) and starts everything.

When it's done it prints something like:

```
==> AIDA is running

  Web UI     https://localhost:31337
  Network    https://192.168.1.20:31337

  Setup code 7F3K-Q9P2   (asked when you create the admin account)
```

Running the same command again updates an existing install.

<details>
<summary>Install options</summary>

Set them before `bash`:

```bash
curl -fsSL https://raw.githubusercontent.com/Vasco0x4/AIDA/main/install.sh | AIDA_DIR=~/tools/AIDA bash
```

| Variable | Default | |
|---|---|---|
| `AIDA_DIR` | `~/AIDA` | Where to install |
| `AIDA_BRANCH` | `main` | Branch to install |
| `AIDA_PORT` | `31337` | Web UI port, if 31337 is taken (remembered for later starts) |

Prefer not to pipe into bash? Do the same by hand:

```bash
git clone https://github.com/Vasco0x4/AIDA.git ~/AIDA
~/AIDA/install.sh
```

</details>

---

## First login

1. Open **https://localhost:31337**. From another computer on your network, use the `Network` address the installer printed.
2. Your browser warns that the connection is not private. That's expected: AIDA uses a self-signed certificate. Continue to the site:
   - Chrome / Edge: **Advanced → Proceed to localhost**
   - Firefox: **Advanced → Accept the Risk and Continue**
   - Safari: **Show Details → visit this website**

   To get rid of the warning on this machine, run `aida trust`.
3. Create the admin account. AIDA asks for the **setup code** printed by the installer: since the UI is reachable from your network, the code makes sure nobody else creates the admin account before you. Lost it? `aida status` shows it again.

> AIDA is meant for your machine and your local network. Do not expose it on the internet.

---

## Everyday commands

| Command | |
|---|---|
| `aida start` | Start AIDA |
| `aida stop` | Stop AIDA. Assessments, findings and workspaces are kept |
| `aida restart` | Restart |
| `aida status` | What is running, the URLs, the setup code |
| `aida logs [service]` | Follow the logs: `backend`, `frontend`, `caddy`, `postgres`, `aida-pentest` |
| `aida update` | Get the latest version and restart |
| `aida doctor` | Check the installation and explain what is wrong |
| `aida trust` | Trust AIDA's certificate on this machine |

`./start.sh`, `./stop.sh` and `./restart.sh` in the AIDA folder do the same as `aida start`, `aida stop` and `aida restart`.

---

## Connect your AI

AIDA gives an AI agent its pentesting tools over [MCP](https://modelcontextprotocol.io/). Pick one way to run the agent:

| | Needs on your machine | |
|---|---|---|
| [**Agent containers**](#agent-containers-claude-code-inside-the-sandbox) — `aida run` (recommended) | Docker only | Claude Code runs inside the assessment's own container |
| [**AI CLI on this machine**](#ai-cli-on-this-machine) — `aida --assessment` | Python 3.10+ and the AI CLI | Claude Code, OpenAI Codex, Kimi Code or Qwen Code |
| [**Other MCP clients**](#other-mcp-clients) | the client | Claude Desktop, Gemini CLI, ChatGPT Desktop, Antigravity... |

In every case, first create an assessment in the web UI.

### Agent containers: Claude Code inside the sandbox

`aida run` gives each assessment its **own container** and runs **Claude Code inside it**. Claude's own Bash and file tools, and the AIDA `execute()` / `python_exec()` / `http_request()` tools, all run in the same sandbox: nothing executes on your host. Claude Code ships in the image, so there is nothing else to install.

**From the web UI:** open the assessment and click **Launch agent** → **Open in terminal**. A terminal opens on the AIDA machine running `aida run "<assessment>"`. If the button isn't there (the UI is opened from another machine, or the AIDA helper isn't running), the menu shows the command to copy instead.

**From a terminal:**

```bash
aida run "target-corp"            # create/start the container, launch Claude, attach
aida run "target-corp" --yes      # no permission prompts (Claude is sandboxed)
aida run "target-corp" --continue # resume the last conversation
aida shell "target-corp"          # shell in the same container
aida ps                           # list agent containers
aida stop "target-corp"           # stop (files and installed tools kept)
aida rm "target-corp"             # remove container + network (workspace kept)
```

Claude runs in a tmux session: **detach with `Ctrl-b d`** and it keeps working; `aida run` (or Launch agent) re-attaches. When Claude exits you land in a shell inside the container (`aida-claude` restarts it).

**Several assessments at once.** Each agent only sees its own assessment, so you can run one per assessment side by side: `aida run "client-a"` in one terminal, `aida run "client-b"` in another. Findings, recon and commands always land in the right assessment.

**What each assessment gets**

| | |
|--|--|
| Container | `aida-agent-<id>`, image `vasco0x4/aida-agent` (aida-pentest tools + Claude Code), non-root user `aida` without sudo |
| Privileges | only the `NET_RAW` capability, so nmap SYN and OS scans work. The image has no setuid binary, so no process in the container can become root or hold more. System packages can't be installed; `pip install --user` works |
| Resources | at most 4 GB of memory, 2 CPUs and 2048 processes. Change them with `AIDA_AGENT_MEMORY`, `AIDA_AGENT_CPUS` and `AIDA_AGENT_PIDS_LIMIT` (empty = no limit) |
| Claude config | its own volume `aida-agent-claude-<id>` (login, settings, conversations), never shared with another assessment |
| Workspace | only this assessment's folder (`~/.aida/workspaces/<name>`), mounted at the same path as in `aida-pentest` |
| Network | its own bridge `aida-agent-net-<id>`: internet access, the AIDA backend reachable as `aida-backend`, but no access to postgres, the docker proxy or other assessments |
| MCP | HTTP transport with an `agent` API key bound to this assessment (cached in `.aida/agents/<id>.key`): the agent can't load, list or create any other assessment |

While an assessment's agent container is running, its `execute()` commands run there instead of the shared `aida-pentest` container.

**Claude login.** Each assessment's container keeps its own Claude Code login and settings, so an agent can't read another assessment's credentials or leave hooks that would run there. The first `aida run` of an assessment shows the login screen. Alternatively, export `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) before `aida run`: they're forwarded to Claude at launch and never stored in the container. `aida rm X` deletes that login along with the container.

**The agent image.** The first `aida run` downloads `vasco0x4/aida-agent` (amd64 and arm64; it shares most of its layers with `aida-pentest`, already on your machine). `aida start` / `aida update` keep it up to date once you have it, and it's republished weekly with the latest Claude Code.

| | |
|--|--|
| `aida run X --pull` | download the latest image now (newer Claude Code) |
| `aida run X --recreate` | recreate the container on the current image (workspace and Claude login kept, tools you installed in the container are lost) |
| `aida run X --new` | restart the Claude session, keep the container |
| `aida run X --rebuild` | build the image from `agent/Dockerfile` instead of downloading it |

If the image can't be downloaded (offline, a fork without published images), `aida run` builds `agent/Dockerfile` locally instead (a few minutes). On Linux, files the agent writes in the workspace are owned by you: if your user isn't `1000:1000`, `aida run` adds a small local layer that gives the agent user your UID/GID.

**Notes**

- `agent` keys work even when HTTP MCP is disabled in Settings, and are accepted from private addresses only (`lan` policy): that's how the container reaches the backend. `aida run` mints one per assessment and revokes the previous one; deleting the assessment deletes its keys.
- An older agent key that isn't bound to an assessment is refused: `aida run "<assessment>" --new` replaces it.
- Other HTTP MCP clients also get their own context per API key: give each client its own key (Settings → MCP Access).

### AI CLI on this machine

`aida --assessment` launches an AI CLI installed on your machine and configures everything for it: MCP server, workspace, pentesting preprompt and authentication. It needs **Python 3.10+** (it creates its own virtualenv on first use).

**1. Install and log in to the CLI you want**

| CLI | Install |
|---|---|
| Claude Code (default) | `curl -fsSL https://claude.ai/install.sh \| bash` |
| OpenAI Codex | `npm install -g @openai/codex && codex login` |
| Kimi Code | `curl -fsSL https://code.kimi.com/kimi-code/install.sh \| bash`, then `kimi login` |
| Qwen Code | see the Qwen Code documentation |

**2. Launch it on an assessment**

```bash
aida --assessment "MyTarget"                    # Claude Code
aida --assessment "MyTarget" --cli codex        # OpenAI Codex
aida --assessment "MyTarget" --cli kimi         # Kimi Code
aida --assessment "MyTarget" --cli auto         # whichever is installed
aida                                            # pick the assessment from a list
```

`aida --assessment ...` is the same as `python3 aida.py --assessment ...` run from the AIDA folder.

The first launch asks for your AIDA username and password, then stores a long-lived API key in `.aida/api-key` (`chmod 600`, valid 1 year) that later launches and the MCP server reuse. Delete that file to log in again. For scripts and CI, set `AIDA_TOKEN` instead.

**Common options**

| Flag | Description |
|------|-------------|
| `-a`, `--assessment NAME` | Load a specific assessment directly |
| `--cli claude\|codex\|kimi\|qwen\|auto` | Select a CLI (default: Claude Code) |
| `-m`, `--model MODEL` | Override the model, e.g. `--model claude-opus-5-5` |
| `--preprompt FILE` | Use a custom preprompt file |
| `-y`, `--yes` | Auto-approve all AI actions |
| `--no-mcp` | Disable the MCP server (for testing) |
| `--debug` | Enable debug output |
| `-q`, `--quiet` | Minimal startup output |
| `PROMPT...` | Pass an initial prompt directly |

Inside the CLI, `/mcp` shows whether `aida-mcp` is connected.

<details>
<summary>OpenAI Codex notes</summary>

AIDA injects the preprompt as one-run developer instructions, sets the assessment workspace and adds the AIDA MCP server without modifying your global `~/.codex/config.toml`. Codex runs with `workspace-write` sandboxing and `on-request` approvals; AIDA MCP commands still follow the approval mode set in the dashboard.

`--yes` maps to Codex's full-access bypass flag: it disables Codex approvals and sandboxing for that session, so only use it in a trusted, isolated environment.

</details>

<details>
<summary>Kimi Code notes</summary>

Kimi Code CLI is the Node.js successor of the legacy Python `kimi-cli`; if you still have the old one, run `kimi migrate` after installing. AIDA writes the assessment instructions to `.kimi-code/AGENTS.md` and the MCP server to `.kimi-code/mcp.json` in the workspace.

`--yes` maps to `--yolo`, which auto-approves all tool calls. When a non-interactive prompt is passed, `--yolo` is omitted because Kimi auto-approves in that mode anyway.

</details>

<details>
<summary>Vertex AI / external Anthropic-compatible API (Claude Code only)</summary>

```bash
aida --assessment "MyTarget" \
  --base-url "https://YOUR-ENDPOINT" \
  --api-key "YOUR-API-KEY" \
  --model claude-sonnet-5-5
```

Without `--model`, AIDA uses `claude-sonnet-5-5` for external endpoints.

</details>

### Other MCP clients

For Claude Desktop, Gemini CLI, ChatGPT Desktop, Antigravity or any MCP client:

1. Run `aida --assessment "MyTarget"` once and log in, so the API key is stored in `.aida/api-key` (you can quit right after).
2. Add the AIDA MCP server to the client's config, with the real path of your AIDA folder:

   ```json
   {
     "mcpServers": {
       "aida-mcp": {
         "command": "/bin/bash",
         "args": ["/Users/you/AIDA/start_mcp.sh"]
       }
     }
   }
   ```

   | Client | Config file |
   |---|---|
   | Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json` · Linux `~/.config/Claude/claude_desktop_config.json` · Windows `%APPDATA%\Claude\claude_desktop_config.json` |
   | Gemini CLI | `~/.gemini/settings.json` |
   | ChatGPT Desktop | macOS `~/Library/Application Support/ChatGPT/mcp_config.json` |
   | Antigravity | MCP settings in the UI |

3. Restart the client, paste the preprompt from [`PrePrompt.txt`](PrePrompt.txt), then say: `Load assessment "MyTarget" and start it`.

Clients that speak MCP over HTTP can skip the local server and use an API key instead: see [HTTP transport](MCP_TOOLS.md#http-optional-remote-capable).

---

## Pentesting container

AIDA runs the agent's commands in a Docker container, never on your machine.

**aida-pentest** (default, started automatically, about 2 GB) includes nmap, ffuf, gobuster, sqlmap, nikto, dirb, hydra, whatweb, subfinder, dnsx, openssl, Python libraries (impacket, scapy, pwntools, paramiko, requests...) and SecLists. Missing a tool? The agent can install it, or you can:

```bash
docker exec -it aida-pentest bash
apt-get install -y metasploit-framework
```

**Exegol** (400+ tools): install it with the [Exegol documentation](https://docs.exegol.com), then select it in **Settings**. AIDA then stops starting its own container.

---

## Troubleshooting

**Start with `aida doctor`.** It checks Docker, every container, the ports and the URLs, and says what to do for each problem. Paste its output when you ask for help on [GitHub](https://github.com/Vasco0x4/AIDA/issues) or [Discord](https://discord.gg/RVJTWtkVA2).

<details>
<summary>Port 31337 is already in use</summary>

Pick another port. AIDA remembers it for the next starts:

```bash
AIDA_PORT=8443 aida start
```

`AIDA_PORT=31337 aida start` goes back to the default.

</details>

<details>
<summary>Other computers can't open the web UI</summary>

- Use the `Network` address from `aida status`, with `https://` and the port.
- Allow incoming connections for Docker / OrbStack if the macOS firewall asks; on Linux, open the port (`sudo ufw allow 31337/tcp`).
- If you started AIDA with `AIDA_BIND=127.0.0.1`, it only listens on this machine.

</details>

<details>
<summary>"Wrong setup code"</summary>

Run `aida status` to see the current code. If AIDA was started without the `aida` command (plain `docker compose up`), the backend made up its own code: `docker logs aida_backend | grep "Setup code"`.

</details>

<details>
<summary>Docker says "permission denied" (Linux)</summary>

Your user needs to be in the `docker` group: `sudo usermod -aG docker $USER`, then log out and back in.

</details>

<details>
<summary>Upgrading from an older version</summary>

Run `aida update` (or the install command again): your data is kept. What changed:

- The web UI moved from `http://localhost:31337` to **https**://localhost:31337, reachable from your network, with a setup code for the first admin account.
- `--lan`, `--lan-port`, `--domain` and `--localhost` were removed: there is a single mode now, and commands always run in the pentesting container.
- PostgreSQL is no longer published on port 5432 of your machine.

</details>

<details>
<summary>Forgot your password</summary>

See [`RESET_PASSWORD.md`](RESET_PASSWORD.md).

</details>

---

## Uninstall

```bash
aida stop
rm -rf ~/AIDA "$(command -v aida)"
```

That keeps your data. To delete it too (assessments, findings, certificates):

```bash
docker volume rm aida_postgres_data aida_caddy_data aida_caddy_config
docker image rm vasco0x4/aida-backend vasco0x4/aida-frontend vasco0x4/aida-pentest
rm -rf ~/.aida
```

---

## Contributing: dev mode

```bash
git clone https://github.com/Vasco0x4/AIDA.git && cd AIDA
./start.sh --dev
```

- Web UI with hot reload: http://localhost:5173 · API: http://localhost:8000/docs
- The backend runs your local source with `--reload`.
- `./start.sh` (without `--dev`) goes back to the normal mode.
- To test the normal mode with your local backend/frontend code instead of the Docker Hub images: `AIDA_BUILD=1 ./start.sh`.
