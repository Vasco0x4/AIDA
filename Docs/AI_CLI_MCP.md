# AI CLI and MCP

## Three independent credentials

1. The AIDA account signs in to the application, with OTP when enabled.
2. HTTP MCP uses a separately issued API key; stdio MCP receives launcher context.
3. The external CLI authenticates to its own model provider.

Success at one layer does not authenticate the others. Settings → AI Models configures the built-in runner, not every external CLI.

## Launcher

Run `python3 aida.py --clients` to inspect detected clients and capabilities, then choose an installed client explicitly with `--cli`. The local adapters include Claude, Codex, Kimi, Qwen, Gemini and Cursor Agent. Cursor requires its `agent` executable. Complete the client's own provider login before starting an Assessment workflow.

Use `--assessment` to select the workspace. The model still needs to load Assessment context through MCP. Keep generated workspace configuration private: it may contain credentials. Client configuration formats and flags can evolve; inspect `--help` and the installed client's documentation before changing the adapters.

The launcher supports stdio and `--http URL` / `AIDA_MCP_HTTP_URL`. Prefer environment-based credentials over command-line secrets. For this Mac mini, the directly published API is `http://127.0.0.1:18080/api`; general guides may show different development defaults. Check actual Compose port mappings.

`--yes` changes tool approval behavior and can bypass client sandbox/approval protections for some adapters. It is not required for registration and should not be used simply to troubleshoot connectivity. `--no-mcp` skips MCP registration. `--preprompt` selects a custom context file.

## Transport diagnostics

| Symptom | Meaning or check |
| --- | --- |
| CLI missing | Executable and PATH; run `--clients` |
| Provider 401/403 | Provider login, subscription and model access |
| MCP HTTP 401 | Missing, expired or revoked MCP API key |
| MCP HTTP 403 | Network policy or permission restriction |
| MCP HTTP 503 | HTTP transport disabled/unavailable |
| stdio exits | Dependencies, database/API configuration and stdout protocol cleanliness |
| No Assessment loaded | Call the MCP load tool for the intended Assessment |
| Tool waits | Pending command approval, timeout, runner or backend health |

The UI's generated snippets are the preferred starting point. Restart/reload the client after editing configuration. A successful tools-list operation proves registration, not provider completion or full end-to-end scanning. Review [MCP tools](MCP_TOOLS.md) for the tool catalog.

This release does not certify live provider execution for every adapter. Those checks need valid provider sessions and an isolated target with explicit scope.

## Built-in Kimi Code configuration

In **Settings → AI Models**, select **Kimi Code (international)**, use `https://api.kimi.ai/coding/v1` and model `k3.1-pro`, and enter your own Coding API key. Run the connection test before assigning the model to a task or explicitly consenting to AppSec AI review. The built-in provider sets the required temperature for this K3 Coding endpoint and preserves reasoning content across tool rounds. This does not configure the external Kimi CLI.

The actual connection, a synthetic AppSec review and a bounded agent tool loop were verified in the [November QA report](QA_REPORT.md). Test credentials are not distributed with AIDA.
