# MCP Tools Reference

Complete reference for all MCP tools available to AI clients.

---

## Overview

AIDA exposes tools through the Model Context Protocol (MCP). These tools give AI assistants the ability to:

- Execute commands in the pentesting container
- Document findings and observations
- Track reconnaissance data
- Manage credentials
- Run specialized security scans

---

## Transport: stdio vs HTTP

AIDA ships two transports. stdio is the default and spawns the MCP server as a local subprocess. HTTP (Streamable HTTP, spec 2025-11-25) is optional and lets remote clients connect with a Bearer API key.

### stdio (default)

```bash
python3 aida.py --assessment "my-target"
```

Generates `.aida/mcp-config.json` pointing at the backend venv's Python. No network exposure — the AI client and MCP server share stdin/stdout.

### HTTP (optional, remote-capable)

1. Open AIDA → Settings → **MCP Access**.
2. Toggle **Enable HTTP MCP transport**.
3. Pick a network policy (localhost / LAN / any). LAN and Any require `BACKEND_BIND_HOST=0.0.0.0` in `.env` and a backend restart.
4. Click **Create API key**, copy the value shown once.
5. Paste the generated snippet into your MCP client's config. For Claude Code:

The endpoint is reachable at three URLs depending on how AIDA was started:

| Mode | URL |
|------|-----|
| Local (default) | `http://localhost:31337/mcp` (via Nginx) or `http://localhost:8000/mcp` (direct backend) |
| `--lan` | `https://<LAN_IP>/mcp` (via Caddy) |
| `--domain example.com` | `https://example.com/mcp` (via Caddy + Let's Encrypt) |

```bash
# Local
claude mcp add --transport http aida http://localhost:8000/mcp \
  --header "Authorization: Bearer aida_sk_..."

# LAN — use the LAN IP shown by ./start.sh --lan
claude mcp add --transport http aida https://192.168.1.42/mcp \
  --header "Authorization: Bearer aida_sk_..."

# Public domain
claude mcp add --transport http aida https://aida.example.com/mcp \
  --header "Authorization: Bearer aida_sk_..."
```

In a client's `mcp.json`:

```json
{
  "mcpServers": {
    "aida": {
      "url": "https://aida.example.com/mcp",
      "headers": { "Authorization": "Bearer aida_sk_..." }
    }
  }
}
```

The CLI launcher can emit the HTTP config for you:

```bash
python3 aida.py --http http://localhost:8000/mcp --mcp-api-key aida_sk_...
```

For OpenAI Codex CLI, AIDA configures this automatically when launched with
`--cli codex`. To register the HTTP server directly in Codex:

```bash
export AIDA_MCP_API_KEY="aida_sk_..."
codex mcp add aida --url http://localhost:8000/mcp \
  --bearer-token-env-var AIDA_MCP_API_KEY
```

### Security

- **Default off.** The `/mcp` route returns 503 until an admin enables it.
- **Keys are bcrypt-hashed** at rest; the plaintext is shown exactly once on creation.
- **Revocation is instant** via the Settings UI.
- **Network policy** is enforced at the application layer even when the socket binds to 0.0.0.0.
- **TLS is optional and mode-driven.** In `./start.sh --lan` and `./start.sh --domain` modes,
  Caddy fronts the backend and the MCP endpoint is also reachable at
  `https://<host>/mcp`. In default local mode there is no TLS — `http://localhost:8000/mcp`
  is fine because the traffic stays on your machine. See [`TLS.md`](TLS.md).

---

## 📋 MCP Tools Cheatsheet

| Category | Tool | Signature | Description |
|----------|------|-----------|-------------|
| **Assessment** | `load_assessment` | `load_assessment(name="Target")` | Load assessment and get full context |
| | `update_phase` | `update_phase(phase_number=1.0, content="...")` | Document progress in a phase |
| **Cards** | `add_card` | `add_card(card_type="finding", title="...", severity="HIGH", ...)` | Create finding card |
| | | `add_card(card_type="observation", title="...", notes="...")` | Create observation card |
| | | `add_card(card_type="info", title="...", context="...")` | Create info card |
| | `list_cards` | `list_cards()` | List all cards |
| | | `list_cards(card_type="finding", severity="CRITICAL")` | Filter cards by type/severity |
| | `update_card` | `update_card(card_id=42, status="confirmed", proof="...")` | Update existing card |
| | `delete_card` | `delete_card(card_id=42)` | Delete card by ID |
| **Recon** | `add_recon_data` | `add_recon_data(data_type="endpoint", name="/api/users", details={...})` | Add single recon entry |
| | | `add_recon_data(entries=[{...}, {...}])` | Batch import recon data |
| | `list_recon` | `list_recon()` | List all recon data |
| | | `list_recon(data_type="subdomain", limit=100)` | Filter recon by type |
| **Execution** | `execute` | `execute(command="nmap -sV 10.0.0.1")` | Run shell command in Exegol |
| | | `execute(command="...", phase="recon")` | Run with phase context |
| | `host_execute` | `host_execute(action="echo", args=["hello"], working_directory="/srv/aida-work", targets=[])` | Optional policy-constrained direct host argv; disabled and hidden by default |
| | `python_exec` | `python_exec(code="import socket; ...")` | Execute Python code in Exegol |
| | | `python_exec(code="...", phase="recon")` | Run Python with phase context |
| | `http_request` | `http_request(method="GET", url="https://...")` | Make HTTP request from Exegol |
| | | `http_request(method="POST", url="...", body={...}, headers={...})` | POST with body and headers |
| **Pentesting** | `scan` | `scan(type="nmap_quick", target="10.0.0.1")` | Quick nmap scan |
| | | `scan(type="nmap_full", target="10.0.0.1", ports="1-65535")` | Full port scan |
| | | `scan(type="gobuster", target="https://...", wordlist="medium")` | Directory enumeration |
| | | `scan(type="ffuf", target="https://.../FUZZ", wordlist="common")` | Web fuzzing |
| | `subdomain_enum` | `subdomain_enum(domain="acme.com")` | Find subdomains |
| | `ssl_analysis` | `ssl_analysis(target="acme.com:443")` | Analyze SSL/TLS config |
| | `tech_detection` | `tech_detection(url="https://acme.com")` | Detect technology stack |
| | `tool_help` | `tool_help(tool="sqlmap")` | Get tool documentation |
| **Credentials** | `credentials_add` | `credentials_add(credential_type="bearer_token", name="...", token="...")` | Store bearer token |
| | | `credentials_add(credential_type="cookie", name="...", cookie_value="...")` | Store cookie |
| | | `credentials_add(credential_type="ssh", username="...", password="...")` | Store SSH credentials |
| | `credentials_list` | `credentials_list()` | List all stored credentials |
| | | `credentials_list(credential_type="bearer_token")` | Filter by credential type |

---

## Tool Categories

| Category | Tools | Purpose |
|----------|-------|---------|
| [Assessment](#assessment-management) | 2 | Load and update assessments |
| [Cards](#cards-management) | 4 | Findings, observations, info |
| [Recon](#reconnaissance) | 2 | Track discovered assets |
| [Execution](#command-execution) | 3 | Run commands, Python code, HTTP requests in Exegol |
| [Pentesting](#pentesting-tools) | 5 | Specialized security tools |
| [Credentials](#credentials-management) | 2 | Store and retrieve creds |

---

`host_execute` is not part of the container execution flow. It requires explicit executable, working-directory, and (for network tools) target policy. See [Reliability and security operations](RELIABILITY_OPERATIONS.md#opt-in-direct-host-mcp-execution) for configuration and threat-model limitations.

## Assessment Management

### `load_assessment`

Load an existing assessment to begin work.

> Assessments are created via the web interface, not by the AI.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Assessment name |
| `skip_data` | boolean | No | If true, only sets context without returning data |

**Returns:**
- Assessment metadata (name, target, container)
- Existing findings and observations
- Recon data collected so far
- Recent command history
- Stored credentials (placeholders only)

---

### `update_phase`

Document progress in a phase section.

**Example:**

```python
update_phase(
    phase_number=1.0,
    content="## Initial Reconnaissance\n\nCompleted nmap scan of 10.0.0.1\nFound 3 open ports: 22, 80, 443\nIdentified nginx 1.18.0 on port 80"
)
```

---

## Cards Management

Cards are the primary way to document findings.

### `add_card`

Create a finding, observation, or info card.

**Examples:**

```python
# Critical finding
add_card(
    card_type="finding",
    title="SQL Injection in Login Form",
    severity="CRITICAL",
    status="confirmed",
    target_service="https://app.acme.com/login",
    technical_analysis="The login form is vulnerable to SQL injection via the username parameter.",
    proof="sqlmap -u 'https://app.acme.com/login' --data='user=admin&pass=test' -p user --dbs"
)

# Observation
add_card(
    card_type="observation",
    title="Missing Rate Limiting",
    target_service="https://app.acme.com/api",
    notes="The API does not implement rate limiting. This could allow brute force attacks."
)

# Info
add_card(
    card_type="info",
    title="Technology Stack",
    context="Frontend: React 18\nBackend: Node.js/Express\nDatabase: PostgreSQL 14"
)
```

**Returns:** Card ID

---

### `list_cards`

List all cards with optional filters.

**Examples:**

```python
# All cards
list_cards()

# Only critical findings
list_cards(card_type="finding", severity="CRITICAL")

# All observations
list_cards(card_type="observation")
```

---

### `update_card`

Update an existing card by ID.

**Example:**

```python
update_card(
    card_id=42,
    status="confirmed",
    proof="Additional exploitation proof:\n$ curl -X POST..."
)
```

---

### `delete_card`

Delete a card by ID.

**Example:**

```python
delete_card(card_id=42)
```

---

## Reconnaissance

Track discovered assets automatically.

### `add_recon_data`

Add reconnaissance data (single or batch).

**Examples:**

```python
# Single entry
add_recon_data(
    data_type="subdomain",
    name="api.acme.com",
    details={"ip": "10.0.0.5", "source": "subfinder"}
)

# Batch entry
add_recon_data(entries=[
    {"data_type": "endpoint", "name": "/api/v1/users"},
    {"data_type": "endpoint", "name": "/api/v1/admin"},
    {"data_type": "endpoint", "name": "/api/v1/config"},
])
```

---

### `list_recon`

List reconnaissance data with filters.

**Examples:**

```python
# All recon data
list_recon()

# Just endpoints
list_recon(data_type="endpoint")

# Just subdomains
list_recon(data_type="subdomain", limit=100)
```

---

## Command Execution

Three tools allow code execution inside the Exegol container. Each has its own independently configurable output max length (Settings → Command Settings → Output Max Length).

### `execute`

Execute any shell command in the pentesting container.

**Examples:**

```python
# Simple command
execute(command="whoami")

# With phase context
execute(
    command="nmap -sV -sC 10.0.0.1",
    phase="reconnaissance"
)

# Complex command
execute(command="sqlmap -u 'https://target.com/api?id=1' --dbs --batch")
```

**Returns:**
- Command output (stdout/stderr)
- Exit code
- Execution time

**Notes:**
- Commands may require approval based on settings
- Output is truncated to the `execute` output max length setting
- Credential placeholders (`{{TOKEN}}`) are auto-substituted

---

### `python_exec`

Execute Python code directly inside the pentesting container via stdin, without shell escaping issues.

**Examples:**

```python
# Network recon
python_exec(code="""
import socket
ip = socket.gethostbyname('acme.com')
print(f'Resolved: {ip}')
""")

# Use installed libraries (requests, scapy, impacket, etc.)
python_exec(
    code="""
import requests
r = requests.get('https://target.com/api/users', verify=False)
print(r.status_code, r.text[:500])
""",
    phase="recon"
)
```

**Returns:**
- Python stdout/stderr output
- Exit code

**Notes:**
- Code is passed via stdin — no shell escaping needed
- All tools installed in the pentesting container are available (requests, scapy, impacket, etc.)
- Output is truncated to the `python_exec` output max length setting
- Credential placeholders (`{{TOKEN}}`) are auto-substituted in the code

---

### `http_request`

Make HTTP requests directly from the pentesting container. Useful for testing endpoints that require specific network routing, proxies, or certificates.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `method` | string | Yes | HTTP method: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS` |
| `url` | string | Yes | Target URL |
| `headers` | object | No | HTTP headers dict |
| `body` | any | No | Request body (dict → JSON, string → raw) |
| `timeout` | int | No | Request timeout in seconds (default: 30) |
| `verify_ssl` | bool | No | Verify SSL certificates (default: true) |
| `follow_redirects` | bool | No | Follow HTTP redirects (default: true) |
| `proxy` | string | No | Proxy URL (e.g. `http://127.0.0.1:8080`) |
| `phase` | string | No | Phase context for logging |

**Examples:**

```python
# Simple GET
http_request(method="GET", url="https://target.com/api/users")

# POST with JSON body
http_request(
    method="POST",
    url="https://target.com/api/login",
    headers={"Content-Type": "application/json"},
    body={"username": "admin", "password": "test"}
)

# With auth header and SSL bypass
http_request(
    method="GET",
    url="https://internal.target.com/admin",
    headers={"Authorization": "Bearer {{ADMIN_API_TOKEN}}"},
    verify_ssl=False,
    phase="exploitation"
)

# Through Burp proxy
http_request(
    method="GET",
    url="https://target.com/api/secret",
    proxy="http://127.0.0.1:8080",
    verify_ssl=False
)
```

**Returns:**
- Status code and response headers
- Response body (truncated to `http_request` output max length setting)
- Response time

**Notes:**
- Requests are made from within the pentesting container (internal network access)
- Credential placeholders (`{{TOKEN}}`) are auto-substituted in headers and body
- Commands may require approval based on settings

---

## Pentesting Tools

Specialized wrappers for common security tools.

### `scan`

Run security scans with common tools.

**Scan Types:**

| Type | Tool | Purpose |
|------|------|---------|
| `nmap_quick` | nmap | Fast scan of top ports |
| `nmap_full` | nmap | All ports + version detection |
| `nmap_vuln` | nmap | Vulnerability scripts |
| `gobuster` | gobuster | Directory enumeration |
| `ffuf` | ffuf | Web fuzzing |
| `dirb` | dirb | Directory bruteforce |
| `nikto` | nikto | Web server scanner |

**Wordlist Options:**

| Option | Description |
|--------|-------------|
| `common` | Fast, common paths |
| `medium` | Balanced |
| `large` | Thorough |
| `dirb` | dirb default list |
| `raft-small` | Raft small words |
| `raft-medium` | Raft medium words |

**Examples:**

```python
# Quick nmap scan
scan(type="nmap_quick", target="10.0.0.1")

# Full port scan with version detection
scan(type="nmap_full", target="10.0.0.1", ports="1-65535")

# Directory enumeration
scan(
    type="gobuster",
    target="https://app.acme.com",
    wordlist="medium",
    extensions="php,html,js"
)

# Web fuzzing with custom flags
scan(
    type="ffuf",
    target="https://app.acme.com/FUZZ",
    wordlist="common",
    extra_flags="-mc 200,301,302"
)
```

---

### `subdomain_enum`

Enumerate subdomains for a domain.

**Example:**

```python
subdomain_enum(domain="acme.com")
```

---

### `ssl_analysis`

Analyze SSL/TLS certificate and configuration.

**Examples:**

```python
ssl_analysis(target="acme.com")
ssl_analysis(target="10.0.0.1:8443")
```

**Checks:**
- Certificate validity
- Cipher suites
- Protocol versions
- Known vulnerabilities

---

### `tech_detection`

Detect technology stack of a website.

**Example:**

```python
tech_detection(url="https://app.acme.com")
```

Uses: whatweb, wappalyzer (if available)

---

### `tool_help`

Get help documentation for a tool.

**Example:**

```python
tool_help(tool="sqlmap")
```

Returns: Tool availability and help output

---

## Credentials Management

Store and retrieve discovered credentials.

### `credentials_add`

Add authentication credentials.

**Credential Types:**

| Type | Fields | Use |
|------|--------|-----|
| `bearer_token` | `token` | API bearer tokens |
| `api_key` | `token` | API keys |
| `basic_auth` | `username`, `password` | HTTP basic auth |
| `cookie` | `cookie_value` | Session cookies |
| `ssh` | `username`, `password` | SSH credentials |
| `custom` | `custom_data` | Other formats |

**Examples:**

```python
# Bearer token
credentials_add(
    credential_type="bearer_token",
    name="Admin API Token",
    token="eyJhbGciOiJIUzI1NiIs...",
    service="API",
    target="https://api.acme.com"
)
# Creates placeholder: {{ADMIN_API_TOKEN}}

# SSH credentials
credentials_add(
    credential_type="ssh",
    name="Web Server Root",
    username="root",
    password="admin123",
    target="10.0.0.5"
)
# Creates placeholder: {{WEB_SERVER_ROOT}}

# Cookie
credentials_add(
    credential_type="cookie",
    name="Admin Session",
    cookie_value="session=abc123; admin=true",
    notes="Expires in 24 hours"
)
```

**Placeholder Substitution:**

Once stored, use placeholders in commands:

```python
execute(command="curl -H 'Authorization: Bearer {{ADMIN_API_TOKEN}}' https://api.acme.com/admin")
```

The placeholder is automatically replaced with the actual token.

---

### `credentials_list`

List all stored credentials.

---

## Related Documentation

- [User Guide](USER_GUIDE.md) - How to use the platform
- [Architecture](ARCHITECTURE.md) - Technical deep dive
- [Installation](INSTALLATION.md) - Setup guide
