#!/usr/bin/env python3
"""
AIDA CLI Launcher - Professional Python Implementation
AI-Driven Security Assessment - Intelligent wrapper for Claude Code, Codex CLI, Kimi Code CLI & Qwen Code
"""
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, Literal


def ensure_cli_dependencies():
    """Ensure CLI dependencies are installed before importing them"""
    AIDA_ROOT = Path(__file__).parent.absolute()
    VENV_DIR = AIDA_ROOT / ".venv"
    REQUIREMENTS_FILE = AIDA_ROOT / "requirements.txt"
    
    # Check if we can import required packages
    try:
        import click
        import httpx
        from rich.console import Console
        return  # All dependencies available
    except ImportError:
        pass  # Need to install
    
    # Try to use venv if it exists
    python_bin = "python3"
    if VENV_DIR.exists():
        venv_python = VENV_DIR / "bin" / "python"
        if venv_python.exists():
            python_bin = str(venv_python)
    
    print("🔧 Installing CLI dependencies...", file=sys.stderr)
    
    # Create venv if it doesn't exist
    if not VENV_DIR.exists():
        print(f"📦 Creating virtual environment at {VENV_DIR}...", file=sys.stderr)
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create venv: {e}", file=sys.stderr)
            print("💡 Install dependencies manually: pip install -r requirements.txt", file=sys.stderr)
            sys.exit(1)
        
        # Update python_bin to use new venv
        python_bin = str(VENV_DIR / "bin" / "python")
    
    # Install dependencies
    if REQUIREMENTS_FILE.exists():
        print(f"📥 Installing from {REQUIREMENTS_FILE.name}...", file=sys.stderr)
        try:
            subprocess.run(
                [python_bin, "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS_FILE)],
                check=True,
                capture_output=True
            )
            print("✅ Dependencies installed successfully", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}", file=sys.stderr)
            print("💡 Try manually: pip install click httpx rich", file=sys.stderr)
            sys.exit(1)
    
    # If we installed in venv, we need to re-execute with that Python
    if python_bin != sys.executable and VENV_DIR.exists():
        venv_python = VENV_DIR / "bin" / "python"
        if venv_python.exists():
            # Re-execute this script with the venv Python
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)


# Ensure dependencies before importing heavy packages
ensure_cli_dependencies()

# Now safe to import
import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from backend.launcher_adapters import (
    _codex_override,
    _toml_value,
    build_codex_command,
    build_codex_mcp_args,
    build_cursor_command,
    build_gemini_command,
    build_qwen_command,
    build_qwen_mcp_servers,
    CLI_CAPABILITIES,
    CLI_PRIORITY,
    detect_available_clis,
)

console = Console()

# Configuration
AIDA_ROOT = Path(__file__).parent.absolute()
AIDA_CONFIG_DIR = AIDA_ROOT / ".aida"
PREPROMPT_FILE = AIDA_ROOT / "Docs" / "PrePrompt.txt"
PREPROMPT_ASVS_FILE = AIDA_ROOT / "Docs" / "PrePrompt-ASVS.txt"
MCP_SERVER_PATH = AIDA_ROOT / "backend" / "mcp" / "aida_mcp_server.py"
MCP_CONFIG_FILE = AIDA_CONFIG_DIR / "mcp-config.json"
SESSION_FILE = AIDA_CONFIG_DIR / "session"
API_KEY_FILE = AIDA_CONFIG_DIR / "api-key"

# Kimi Code CLI project-level config directory, written inside the assessment
# workspace (which becomes the CLI's working directory). The legacy Python
# kimi-cli took a per-launch agent file via --agent-file; the Node.js Kimi Code
# CLI dropped that flag and loads instructions from .kimi-code/AGENTS.md and
# MCP servers from .kimi-code/mcp.json in the working directory instead.
KIMI_WORKSPACE_CONFIG_DIR = ".kimi-code"

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_PERMISSION = "default"
# Dev stack (docker-compose.yml in this checkout): backend on :8001,
# postgres on :5433. The old single-port stack on :8000/:5432 is gone.
DEFAULT_BACKEND = "http://localhost:8001/api"

CONTAINER_PREFS_FILE = AIDA_CONFIG_DIR / "container-preference"

# CLI types
CLIType = Literal["claude", "codex", "kimi", "qwen"]


def ensure_backend_venv(quiet=False) -> Path:
    """Ensure backend venv exists with MCP dependencies installed"""
    backend_dir = AIDA_ROOT / "backend"
    venv_dir = backend_dir / "venv"
    requirements_file = backend_dir / "requirements.txt"
    python_bin = venv_dir / "bin" / "python"

    # A venv dir without a working bin/python (interrupted creation, or a
    # system python old enough that pip failed) is a broken stub — recreate.
    if venv_dir.exists() and not python_bin.exists():
        if not quiet:
            console.print("[yellow]⚠ Broken backend venv stub (no bin/python), recreating...[/yellow]")
        import shutil
        shutil.rmtree(venv_dir, ignore_errors=True)

    # Check if venv exists
    if not venv_dir.exists():
        if not quiet:
            console.print("[yellow]⚠ Backend venv not found, creating...[/yellow]")

        # requirements.txt needs Python >= 3.10; prefer a Homebrew python when
        # the interpreter running this script is older (macOS ships 3.9).
        venv_python = sys.executable
        if sys.version_info < (3, 10):
            for candidate in ("/opt/homebrew/bin/python3.14", "/opt/homebrew/bin/python3.13", "/opt/homebrew/bin/python3.12", "/opt/homebrew/bin/python3.11"):
                if Path(candidate).exists():
                    venv_python = candidate
                    break

        try:
            subprocess.run(
                [venv_python, "-m", "venv", str(venv_dir)],
                check=True,
                capture_output=True
            )
            if not quiet:
                console.print("[green]✓ Created backend venv[/green]")
        except subprocess.CalledProcessError as e:
            if not quiet:
                console.print(f"[red]✗ Failed to create backend venv: {e}[/red]")
            raise
    
    # Install backend dependencies if requirements.txt exists
    python_bin = venv_dir / "bin" / "python"
    if requirements_file.exists():
        # Check if MCP is installed
        try:
            result = subprocess.run(
                [str(python_bin), "-c", "import mcp"],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                # MCP not installed, install dependencies
                if not quiet:
                    console.print("[yellow]Installing backend dependencies (including MCP)...[/yellow]")
                
                try:
                    result = subprocess.run(
                        [str(python_bin), "-m", "pip", "install", "-r", str(requirements_file)],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=900
                    )
                    if not quiet:
                        console.print("[green]✓ Backend dependencies installed[/green]")
                except subprocess.CalledProcessError as e:
                    if not quiet:
                        console.print(f"[yellow]⚠ Could not install backend dependencies[/yellow]")
                        if e.stderr and not quiet:
                            # Show the actual error from pip
                            console.print(f"[dim]Error details:[/dim]")
                            for line in e.stderr.strip().split('\n')[-5:]:  # Last 5 lines
                                console.print(f"[dim]  {line}[/dim]")
                        console.print("[yellow]→ MCP server may not work. Install manually if needed:[/yellow]")
                        console.print(f"[dim]  cd {backend_dir} && source venv/bin/activate && pip install -r requirements.txt[/dim]")
                except subprocess.TimeoutExpired:
                    if not quiet:
                        console.print("[yellow]⚠ Backend dependency installation timed out[/yellow]")
        except Exception as e:
            if not quiet:
                console.print(f"[yellow]⚠ Could not verify MCP installation: {e}[/yellow]")
    
    return python_bin


def check_exegol_installed() -> bool:
    """Check if Exegol containers exist on the system (doesn't need to be running)"""
    try:
        # Check by container name starting with 'exegol-'
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            containers = result.stdout.strip().split('\n')
            for container in containers:
                if container.lower().startswith('exegol-'):
                    return True
            
        return False
        
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def generate_mcp_config(db_url: str, token: str = "", backend_url: str = "", quiet=False) -> None:
    """Generate MCP configuration file with proper backend venv"""
    AIDA_CONFIG_DIR.mkdir(exist_ok=True)

    # Ensure backend venv exists with MCP dependencies
    try:
        python_bin = ensure_backend_venv(quiet)
        python_bin_str = str(python_bin.absolute())
    except Exception as e:
        if not quiet:
            console.print(f"[red]✗ Could not setup backend venv: {e}[/red]")
            console.print("[yellow]Falling back to system Python[/yellow]")
        python_bin_str = "python3"

    # The MCP handlers call the backend REST API; without BACKEND_API_URL they
    # fall back to the default :8000, which is not this stack's backend.
    mcp_env = {
        "PYTHONPATH": str((AIDA_ROOT / "backend").absolute()),
        "DATABASE_URL": db_url,
        "AIDA_TOKEN": token,
    }
    if backend_url:
        mcp_env["BACKEND_API_URL"] = backend_url

    config = {
        "mcpServers": {
            "aida-mcp": {
                "command": python_bin_str,
                "args": [str(MCP_SERVER_PATH.absolute())],
                "env": mcp_env
            }
        }
    }
    
    MCP_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    # Token is embedded in plaintext — restrict to owner only.
    MCP_CONFIG_FILE.chmod(0o600)
    if not quiet:
        console.print(f"[dim]✓ MCP config: {MCP_CONFIG_FILE.name}[/dim]")
        console.print(f"[dim]  Python: {python_bin_str}[/dim]")


def generate_mcp_http_config(url: str, api_key: str, quiet=False) -> None:
    """Generate an HTTP Streamable-HTTP MCP config for remote servers."""
    AIDA_CONFIG_DIR.mkdir(exist_ok=True)
    config = {
        "mcpServers": {
            "aida-mcp": {
                "url": url,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }
        }
    }
    MCP_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    MCP_CONFIG_FILE.chmod(0o600)
    if not quiet:
        console.print(f"[dim]✓ MCP config (HTTP): {MCP_CONFIG_FILE.name}[/dim]")
        console.print(f"[dim]  Endpoint: {url}[/dim]")


def generate_kimi_workspace_config(preprompt_content: str, assessment_name: Optional[str],
                                   assessment_id: Optional[str], container_name: Optional[str],
                                   workspace_path: str, quiet=False) -> Path:
    """Write Kimi Code CLI project instructions (AGENTS.md) into the workspace"""
    kimi_dir = Path(workspace_path) / KIMI_WORKSPACE_CONFIG_DIR

    # Like the Qwen branch, config must live in the workspace: there is no
    # per-launch flag to point Kimi Code CLI at a file elsewhere, and we
    # don't touch ~/.kimi-code/ to avoid cross-assessment config pollution.
    try:
        kimi_dir.mkdir(parents=True, exist_ok=True)
        test_file = kimi_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except (PermissionError, OSError) as e:
        if not quiet:
            console.print("[red]✗ Cannot write to workspace configuration directory[/red]")
            console.print(f"[dim]  Error: {e}[/dim]")
            console.print("\n[yellow]Troubleshooting:[/yellow]")
            console.print("  • Check workspace permissions:")
            console.print(f"    [cyan]ls -la {workspace_path}[/cyan]")
            console.print("  • Fix ownership:")
            console.print(f"    [cyan]sudo chown -R $USER:$USER {workspace_path}[/cyan]\n")
        sys.exit(1)

    # Enhance preprompt with assessment context for Kimi
    enhanced_prompt = preprompt_content
    if assessment_name:
        enhanced_prompt += f"""

## **Assessment Loaded**

**{assessment_name}** (ID: {assessment_id}) - Container: {container_name}

The assessment workspace is ready. Use your standard tools to work with files and execute commands.
"""

    agents_file = kimi_dir / "AGENTS.md"
    agents_file.write_text(enhanced_prompt)

    if not quiet:
        console.print(f"[dim]✓ Kimi instructions: {agents_file}[/dim]")

    return agents_file


def generate_scoped_client_config(
    cli_type: str,
    *,
    workspace_path: str,
    preprompt_content: str,
    no_mcp: bool,
    http_url: Optional[str],
    mcp_api_key: str,
    token: str,
    backend_url: str,
    db_url: str,
    quiet: bool,
) -> None:
    """Write native Gemini/Cursor project config, preserving other servers."""
    workspace = Path(workspace_path)
    config_dir = workspace / (".gemini" if cli_type == "gemini" else ".cursor")
    config_dir.mkdir(parents=True, exist_ok=True)

    if cli_type == "gemini":
        instruction_file = config_dir / "AIDA.md"
        instruction_file.write_text(preprompt_content)
        settings_file = config_dir / "settings.json"
        settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        context = settings.setdefault("context", {})
        filenames = context.get("fileName", "GEMINI.md")
        filenames = filenames if isinstance(filenames, list) else [filenames]
        if ".gemini/AIDA.md" not in filenames:
            filenames.append(".gemini/AIDA.md")
        context["fileName"] = filenames
    else:
        instruction_file = config_dir / "rules" / "aida.mdc"
        instruction_file.parent.mkdir(parents=True, exist_ok=True)
        instruction_file.write_text(
            "---\ndescription: AIDA assessment instructions\nalwaysApply: true\n---\n\n"
            + preprompt_content
        )
        settings_file = config_dir / "mcp.json"
        settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}

    if not no_mcp:
        python_bin = "python3"
        if not http_url:
            try:
                python_bin = str(ensure_backend_venv(quiet).absolute())
            except Exception:
                # The stdio server can still use an already provisioned Python.
                pass
        servers = build_qwen_mcp_servers(
            token=token,
            backend_url=backend_url,
            db_url=db_url,
            http_url=http_url,
            mcp_api_key=mcp_api_key,
            python_bin=python_bin,
        )
        settings.setdefault("mcpServers", {}).update(servers)

    # Gemini needs settings for context even with --no-mcp. Cursor has no
    # reason to create an empty MCP file in that mode.
    if cli_type == "gemini" or not no_mcp:
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        # HTTP bearer/session values can be present in this project file.
        settings_file.chmod(0o600)
        if not quiet:
            console.print(f"[dim]✓ {cli_type.title()} scoped config: {settings_file}[/dim]")


def detect_cli() -> CLIType:
    """Select the first installed CLI from the shared capability registry."""
    detected = detect_available_clis()
    return next((name for name in CLI_PRIORITY if detected[name]["installed"]), None)


def _read_file_token(path: Path) -> Optional[str]:
    """Read a token from a chmod-600 file, return None if missing/empty."""
    if path.exists():
        try:
            return path.read_text().strip() or None
        except OSError:
            pass
    return None


def _write_file_token(path: Path, token: str) -> None:
    """Write token to path with owner-only permissions."""
    AIDA_CONFIG_DIR.mkdir(exist_ok=True)
    path.write_text(token)
    path.chmod(0o600)


def _validate_token(backend_url: str, token: str) -> bool:
    """Return True if token is accepted by /auth/me."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{backend_url}/auth/me",
                           headers={"Authorization": f"Bearer {token}"})
        return r.status_code == 200
    except httpx.ConnectError:
        console.print("[red]✗ Cannot reach backend — is it running?[/red]\n")
        console.print("  → [cyan]docker-compose up -d[/cyan]\n")
        sys.exit(1)


def _do_login(backend_url: str) -> str:
    """Prompt for credentials, call /auth/login, return short-lived token."""
    import getpass
    console.print("[bold]AIDA Backend Login[/bold]")
    username = console.input("  Username: ")
    password = getpass.getpass("  Password: ")

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{backend_url}/auth/login",
                json={"username": username, "password": password},
            )
            if response.status_code == 200 and response.json().get("otp_required"):
                challenge_id = response.json()["challenge_id"]
                code = getpass.getpass("  Authenticator or recovery code: ")
                response = client.post(
                    f"{backend_url}/auth/otp/verify",
                    json={"challenge_id": challenge_id, "code": code},
                )
        if response.status_code == 200:
            return response.json()["access_token"]
        elif response.status_code == 401:
            console.print("[red]✗ Invalid credentials[/red]\n")
            sys.exit(1)
        else:
            console.print(f"[red]✗ Login failed ({response.status_code})[/red]\n")
            sys.exit(1)
    except httpx.ConnectError:
        console.print("[red]✗ Cannot reach backend — is it running?[/red]\n")
        console.print("  → [cyan]docker-compose up -d[/cyan]\n")
        sys.exit(1)


def _fetch_api_key(backend_url: str, session_token: str) -> Optional[str]:
    """Exchange a valid session token for a long-lived API key (1 year)."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(
                f"{backend_url}/auth/api-token",
                headers={"Authorization": f"Bearer {session_token}"},
            )
        if r.status_code == 200:
            return r.json().get("api_token")
    except Exception:
        pass
    return None


def authenticate(backend_url: str) -> str:
    """Return a valid token for backend API calls.

    Priority:
      1. AIDA_TOKEN env var (CI / scripting)
      2. .aida/api-key  — long-lived (1 year), never prompts once set
      3. .aida/session  — 24h token from a previous login
      4. Interactive login → issues api-key stored in .aida/api-key
    """
    # 1. Env var override (CI / scripting)
    token = os.getenv("AIDA_TOKEN")
    if token:
        return token

    # 2. Long-lived API key — valid for 1 year, silently reused
    token = _read_file_token(API_KEY_FILE)
    if token and _validate_token(backend_url, token):
        return token
    if token:
        API_KEY_FILE.unlink(missing_ok=True)  # expired, remove

    # 3. Short-lived session token from a previous login
    token = _read_file_token(SESSION_FILE)
    if token and _validate_token(backend_url, token):
        # Upgrade to a long-lived API key while the session is still valid
        api_key = _fetch_api_key(backend_url, token)
        if api_key:
            _write_file_token(API_KEY_FILE, api_key)
            SESSION_FILE.unlink(missing_ok=True)
            return api_key
        return token
    if token:
        SESSION_FILE.unlink(missing_ok=True)

    # 4. Interactive login — first time or after key revocation
    session_token = _do_login(backend_url)
    api_key = _fetch_api_key(backend_url, session_token)
    if api_key:
        _write_file_token(API_KEY_FILE, api_key)
        console.print("[green]✓ Authenticated[/green]\n")
        return api_key
    # Fallback: api-token endpoint unavailable, cache the session token
    _write_file_token(SESSION_FILE, session_token)
    console.print("[green]✓ Authenticated[/green]\n")
    return session_token


# --- Host path translation (WSL / Docker Desktop on Windows) ---

_WIN_PATH_RE = re.compile(r"^([A-Za-z]):[\\/]")


def _is_wsl() -> bool:
    """Return True if running inside WSL (Windows Subsystem for Linux)."""
    if os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def translate_host_path(path: str) -> str:
    """Translate a Docker-reported host path so it is usable from this process.

    Docker Desktop on Windows reports bind-mount Sources as Windows paths
    (e.g. ``C:/Users/foo/.exegol/workspaces/default/X``). When the AIDA
    launcher runs inside WSL, those paths must be rewritten to their WSL
    equivalent (``/mnt/c/Users/foo/...``) before ``os.chdir`` or any
    filesystem operation can succeed.

    Returns the path unchanged if no translation is needed.
    """
    if not path or not _WIN_PATH_RE.match(path):
        return path
    if not _is_wsl():
        return path  # native Windows Python — caller handles Windows paths natively

    # Prefer wslpath: respects custom mount roots from /etc/wsl.conf.
    try:
        result = subprocess.run(
            ["wslpath", "-u", path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: manual C:/foo/bar  ->  /mnt/c/foo/bar
    drive = path[0].lower()
    rest = path[2:].lstrip("/\\").replace("\\", "/")
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"


def fetch_assessment_methodology(assessment_id: int, backend_url: str, token: str = "") -> str:
    """Return an assessment's methodology ('standard' | 'asvs'); 'standard' on any error."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{backend_url}/assessments/{assessment_id}", headers=headers)
            if response.status_code == 200:
                return response.json().get("methodology") or "standard"
    except Exception:
        pass
    return "standard"


def resolve_workspace(assessment_name: str, backend_url: str, token: str = "") -> Optional[dict]:
    """Resolve assessment workspace via API, with retry on transient network errors"""
    import time

    max_retries = 3
    retry_delays = [1, 2, 4]  # exponential backoff in seconds

    for attempt in range(max_retries):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{backend_url}/workspace/resolve",
                    params={"assessment_name": assessment_name},
                    headers=headers,
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    # Non-retryable HTTP error, will be handled by caller
                    return None

        except httpx.ConnectError:
            # Backend is not reachable at all — don't retry, fail fast
            console.print("\n[red]✗ Failed to connect to AIDA backend[/red]\n")
            console.print("[yellow]Troubleshooting:[/yellow]")
            console.print("  1. Check: [cyan]docker-compose ps[/cyan]")
            console.print("  2. Start: [cyan]docker-compose up -d[/cyan]")
            console.print("  3. Test:  [cyan]curl http://localhost:8001/health[/cyan]\n")
            sys.exit(1)

        except (httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            # Transient network error (e.g. "Connection reset by peer") — retry
            if attempt < max_retries - 1:
                console.print(f"[yellow]⚠ Backend connection dropped ({type(e).__name__}), retrying in {retry_delays[attempt]}s...[/yellow]")
                time.sleep(retry_delays[attempt])
            else:
                console.print(f"\n[red]✗ Backend connection failed after {max_retries} attempts: {e}[/red]\n")
                console.print("[yellow]Troubleshooting:[/yellow]")
                console.print("  1. Check: [cyan]docker-compose ps[/cyan]")
                console.print("  2. Restart backend: [cyan]docker-compose restart backend[/cyan]")
                console.print("  3. Check logs: [cyan]docker-compose logs backend --tail=50[/cyan]\n")
                sys.exit(1)

    return None


def show_assessment_not_found(assessment_name: str, backend_url: str):
    """Display detailed error when assessment workspace cannot be resolved"""
    console.print(f"\n[red]✗ Cannot load assessment '{assessment_name}'[/red]\n")

    container_pref = CONTAINER_PREFS_FILE.read_text().strip() if CONTAINER_PREFS_FILE.exists() else "aida-dev-pentest"

    if container_pref == "exegol" and not check_exegol_installed():
        console.print("[yellow]⚠ No Exegol container detected on this system[/yellow]\n")
        console.print("[bold]Start an Exegol container before using AIDA:[/bold]")
        console.print("  [cyan]exegol start <name>[/cyan]\n")

    sys.exit(1)


def show_cli_not_found():
    """Display error when no supported AI CLI is found."""
    console.print("[red]✗ No compatible AI CLI found[/red]\n")
    console.print("Please install one of the following:\n")
    console.print("[bold]Claude Code:[/bold]")
    console.print("  [cyan]curl -fsSL https://claude.ai/install.sh | bash[/cyan]\n")
    console.print("[bold]OpenAI Codex CLI:[/bold]")
    console.print("  [cyan]npm install -g @openai/codex[/cyan]")
    console.print("  then")
    console.print("  [cyan]codex login[/cyan]\n")
    console.print("[bold]Kimi Code CLI:[/bold]")
    console.print("  [cyan]curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash[/cyan]")
    console.print("  or")
    console.print("  [cyan]npm install -g @moonshot-ai/kimi-code[/cyan]\n")
    console.print("[bold]Qwen Code CLI:[/bold]")
    console.print("  [cyan]npm install -g @qwen-code/qwen-code@latest[/cyan]")
    console.print("  or")
    console.print("  [cyan]bash -c \"$(curl -fsSL https://qwen-code-assets.oss-cn-hangzhou.aliyuncs.com/installation/install-qwen.sh)\"[/cyan]\n")
    console.print("[bold]Gemini CLI:[/bold]")
    console.print("  [cyan]npm install -g @google/gemini-cli[/cyan]\n")
    console.print("[bold]Cursor Agent CLI:[/bold]")
    console.print("  [cyan]https://cursor.com/docs/cli/installation[/cyan]")
    console.print("  The executable is [cyan]agent[/cyan], not the Cursor editor binary.\n")
    sys.exit(1)


def show_cli_capabilities():
    """Print installation and capability diagnostics without requiring login."""
    detected = detect_available_clis()
    table = Table(title="AIDA AI client capabilities", box=box.ROUNDED)
    for column in ("CLI", "Executable", "Installed", "Scoped configuration", "Transports", "Verification"):
        table.add_column(column)
    for name in CLI_PRIORITY:
        item = detected[name]
        table.add_row(
            name,
            item["executable"],
            "[green]yes[/green]" if item["installed"] else "[dim]no[/dim]",
            item["config"],
            ", ".join(item["transports"]),
            item.get("verified", "launcher integration"),
        )
    console.print(table)
    console.print("[dim]Installation detection does not check provider authentication or model access.[/dim]")


@click.command()
@click.option("-a", "--assessment", help="Load specific assessment")
@click.option("-m", "--model", default=None, help="Model to use (optional, uses CLI default if not specified)")
@click.option("--permission-mode", default=None, help=f"Permission mode for Claude Code: auto, default, dontAsk, acceptEdits, bypassPermissions, plan (default: {DEFAULT_PERMISSION})")
@click.option("--preprompt", type=click.Path(exists=False), help="Path to custom preprompt file (default: Docs/PrePrompt.txt)")
@click.option("--base-url", help="Custom API base URL (Claude Code only)")
@click.option("--api-key", help="API authentication token (Claude Code only)")
@click.option("--no-mcp", is_flag=True, help="Disable MCP server")
@click.option("--http", "http_url", default=None,
              help="Use the HTTP MCP transport at the given URL (e.g. http://localhost:8000/mcp) instead of stdio")
@click.option("--mcp-api-key", default=None,
              help="Bearer API key for the HTTP MCP transport (env: AIDA_MCP_API_KEY)")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (minimal output)")
@click.option("--cli", "cli_choice", type=click.Choice([*CLI_PRIORITY, "auto"]), default="claude",
              show_default=True, help="Which CLI to use; use auto for fallback detection")
@click.option("--clients", is_flag=True, help="Show the client capability/install matrix and exit")
@click.option(
    "-y", "--yes",
    is_flag=True,
    help="Auto-approve all actions (Codex/Kimi/Qwen/Gemini/Cursor: full-access/yolo/force, Claude: permission-mode=accept)",
)
@click.argument("prompt", nargs=-1)
def main(assessment, model, permission_mode, preprompt, base_url, api_key, no_mcp, http_url, mcp_api_key, debug, quiet, cli_choice, clients, yes, prompt):
    """AIDA CLI Launcher - AI-Driven Security Assessment

    Supports Claude, Codex, Kimi, Qwen, Gemini and native Cursor Agent CLIs.
    """
    if clients:
        show_cli_capabilities()
        return

    # Clear terminal for clean start
    os.system('clear' if os.name != 'nt' else 'cls')
    
    # Detect which CLI to use
    detected_cli = detect_cli()
    
    if cli_choice == "auto":
        if detected_cli is None:
            show_cli_not_found()
        cli_type = detected_cli
    else:
        # User specified a CLI, check if it's available
        executable = CLI_CAPABILITIES[cli_choice]["executable"]
        result = subprocess.run(["which", executable], capture_output=True)
        if result.returncode != 0:
            console.print(f"[red]✗ {cli_choice.title()} CLI not found in PATH (expected: {executable})[/red]")
            console.print(f"Install {cli_choice} or use --cli auto to use available CLI\n")
            sys.exit(1)
        cli_type = cli_choice
    
    # Configuration with env var fallbacks
    explicit_model = model or os.getenv("AIDA_MODEL")
    base_url = base_url or os.getenv("ANTHROPIC_BASE_URL")
    api_key = api_key or os.getenv("ANTHROPIC_AUTH_TOKEN")
    
    # If using external API but no model specified, use default (Claude only)
    if cli_type == "claude" and (base_url or api_key) and not explicit_model:
        explicit_model = DEFAULT_MODEL
    
    permission_mode = permission_mode or os.getenv("AIDA_PERMISSION_MODE", DEFAULT_PERMISSION)
    backend_url = os.getenv("BACKEND_API_URL", DEFAULT_BACKEND)
    db_url = os.getenv("DATABASE_URL", "postgresql://aida:aida@localhost:5433/aida_assessments")

    # Authenticate once — all subsequent API calls use this token.
    # The token is also forwarded to the MCP server via AIDA_TOKEN env var.
    token = authenticate(backend_url)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Interactive assessment selection if none provided
    if not assessment:
        console.print()
        console.print("[bold cyan]AIDA Security Assessment Assistant[/bold cyan]")
        console.print(f"[dim]Using CLI: {cli_type.title()}[/dim]\n")
        
        # Fetch available assessments
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{backend_url}/assessments", headers=auth_headers)
                
                if response.status_code != 200:
                    console.print("[red]Failed to fetch assessments from backend[/red]\n")
                    sys.exit(1)
                
                assessments = response.json()
                
                # Display selection menu
                console.print("[bold]Select an assessment:[/bold]\n")

                table = Table(show_header=False, box=None, padding=(0, 2))
                table.add_column(style="cyan bold", justify="right", width=4)
                table.add_column()
                table.add_column(style="dim", no_wrap=True)

                if assessments:
                    for i, a in enumerate(assessments, 1):
                        container = a.get('container_name', 'N/A')
                        table.add_row(f"{i}.", a['name'], f"({container})")
                else:
                    console.print("[dim]No assessments yet — the AI can create one for you.[/dim]\n")

                console.print(table)
                console.print()

                # Get user input
                try:
                    choice = console.input("[bold]Enter number (or 'q' to quit): [/bold]")

                    if choice.lower() == 'q':
                        console.print("\nCancelled.\n")
                        sys.exit(0)

                    # Empty input or "0" = skip (no assessment, AI can create one)
                    if choice == '' or choice == '0':
                        assessment = None
                        console.print("\n[green]✓[/green] [dim]No assessment selected — AI can create one with create_assessment()[/dim]\n")
                    else:
                        idx = int(choice) - 1
                        if 0 <= idx < len(assessments):
                            assessment = assessments[idx]['name']
                            console.print(f"\n[green]✓[/green] Selected: [cyan]{assessment}[/cyan]\n")
                        else:
                            console.print("\n[red]Invalid selection[/red]\n")
                            sys.exit(1)

                except (ValueError, KeyboardInterrupt):
                    console.print("\n\nCancelled.\n")
                    sys.exit(0)
                    
        except httpx.ConnectError:
            console.print("[red]✗ Failed to connect to AIDA backend[/red]")
            console.print("\nStart the backend:")
            console.print("  → [cyan]docker-compose up -d[/cyan]\n")
            sys.exit(1)
        except (httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            console.print(f"[red]✗ Backend connection dropped: {e}[/red]")
            console.print("\nThe backend reset the connection. Try restarting it:")
            console.print("  → [cyan]docker-compose restart backend[/cyan]\n")
            sys.exit(1)
    
    # Load PrePrompt (custom or default)
    if preprompt:
        # Custom preprompt specified
        custom_preprompt_path = Path(preprompt).expanduser().resolve()
        
        if not custom_preprompt_path.exists():
            console.print(f"[red]✗ Custom preprompt file not found: {custom_preprompt_path}[/red]\n")
            console.print("[yellow]Troubleshooting:[/yellow]")
            console.print(f"  • Check the path is correct")
            console.print(f"  • Use absolute path or path relative to current directory")
            console.print(f"  • Default preprompt: {PREPROMPT_FILE}\n")
            sys.exit(1)
        
        if not custom_preprompt_path.is_file():
            console.print(f"[red]✗ Path is not a file: {custom_preprompt_path}[/red]\n")
            sys.exit(1)
        
        try:
            preprompt_content = custom_preprompt_path.read_text()
            if not quiet:
                console.print(f"[green]✓ Using custom preprompt:[/green] [cyan]{custom_preprompt_path.name}[/cyan]")
                console.print(f"[dim]  Path: {custom_preprompt_path}[/dim]\n")
        except Exception as e:
            console.print(f"[red]✗ Failed to read preprompt file: {e}[/red]\n")
            sys.exit(1)
    else:
        # Use default preprompt
        if not PREPROMPT_FILE.exists():
            console.print(f"[red]✗ Default preprompt not found: {PREPROMPT_FILE}[/red]\n")
            console.print("[yellow]Create the file or specify a custom preprompt with --preprompt[/yellow]\n")
            sys.exit(1)
        
        try:
            preprompt_content = PREPROMPT_FILE.read_text()
            if not quiet and debug:
                console.print(f"[dim]✓ Using default preprompt: {PREPROMPT_FILE.name}[/dim]\n")
        except Exception as e:
            console.print(f"[red]✗ Failed to read default preprompt: {e}[/red]\n")
            sys.exit(1)
    
    # MCP Configuration
    codex_mcp_python = None
    if not no_mcp:
        if http_url or os.getenv("AIDA_MCP_HTTP_URL"):
            # HTTP transport — don't spawn a subprocess, point the client at the URL.
            url = http_url or os.getenv("AIDA_MCP_HTTP_URL")
            key = mcp_api_key or os.getenv("AIDA_MCP_API_KEY", "")
            if not key:
                console.print(
                    "[red]✗ HTTP MCP requires a Bearer key. "
                    "Pass --mcp-api-key or set AIDA_MCP_API_KEY.[/red]\n"
                )
                sys.exit(1)
            # Codex receives ephemeral overrides; Gemini and Cursor build their
            # native scoped config after workspace resolution.
            if cli_type not in ("codex", "gemini", "cursor"):
                generate_mcp_http_config(url, key, quiet)
        else:
            if not MCP_SERVER_PATH.exists():
                console.print(f"[red]✗ MCP server not found: {MCP_SERVER_PATH}[/red]\n")
                sys.exit(1)
            if cli_type == "codex":
                try:
                    codex_mcp_python = str(ensure_backend_venv(quiet).absolute())
                except Exception as e:
                    if not quiet:
                        console.print(f"[yellow]⚠ Could not setup backend venv: {e}[/yellow]")
                        console.print("[yellow]Falling back to system Python[/yellow]")
                    codex_mcp_python = "python3"
            elif cli_type not in ("gemini", "cursor"):
                generate_mcp_config(db_url, token, backend_url, quiet)
    
    # Workspace resolution
    workspace_path = str(AIDA_ROOT)
    assessment_id = None
    container_name = None
    
    if assessment:
        if not quiet and debug:
            console.print(f"[dim]Resolving workspace for: {assessment}[/dim]")
        
        result = resolve_workspace(assessment, backend_url, token)
        
        if not result or not result.get("success"):
            show_assessment_not_found(assessment, backend_url)
        
        # Extract workspace info
        raw_host_path = result["host_path"]
        workspace_path = translate_host_path(raw_host_path)
        assessment_id = result["assessment_id"]
        container_name = result["container_name"]

        if workspace_path != raw_host_path and not quiet:
            console.print(
                f"[dim]↪ Translated host path for local env:[/dim] "
                f"[yellow]{raw_host_path}[/yellow] → [green]{workspace_path}[/green]"
            )

        if not quiet and debug:
            console.print(f"[dim]✓ Container: {container_name}[/dim]")
            console.print(f"[dim]✓ Workspace: {workspace_path}[/dim]\n")

        # ASVS assessments use a methodology-specific preprompt (grid-walking loop).
        # A user-supplied --preprompt always wins.
        if not preprompt:
            methodology = fetch_assessment_methodology(assessment_id, backend_url, token)
            if methodology == "asvs" and PREPROMPT_ASVS_FILE.exists():
                try:
                    preprompt_content = PREPROMPT_ASVS_FILE.read_text()
                    if not quiet:
                        console.print(
                            f"[green]✓ ASVS assessment — using methodology preprompt:[/green] "
                            f"[cyan]{PREPROMPT_ASVS_FILE.name}[/cyan]\n"
                        )
                except Exception as e:
                    console.print(f"[yellow]⚠ Failed to read ASVS preprompt, using default: {e}[/yellow]\n")

        # Enhance preprompt with assessment context for all CLI types
        preprompt_content += f"""

## **Assessment Loaded**

**{assessment}** (ID: {assessment_id}) - Container: {container_name}

The assessment workspace is ready. Use your standard tools to work with files and execute commands.
Before using assessment-scoped AIDA MCP tools, call `load_assessment(name="{assessment}")`.
"""
    
    # Build CLI command based on selected CLI type
    if cli_type == "claude":
        # Build Claude Code command
        cli_args = [
            "claude",
            "--system-prompt", preprompt_content,
            "--permission-mode", permission_mode,
        ]

        # Only add model if explicitly specified (for external APIs)
        if explicit_model:
            cli_args.extend(["--model", explicit_model])

        if not no_mcp:
            cli_args.extend(["--mcp-config", str(MCP_CONFIG_FILE)])

        if debug:
            cli_args.append("--debug")

        # Add AIDA project to accessible dirs if in workspace
        if workspace_path != str(AIDA_ROOT):
            cli_args.extend(["--add-dir", str(AIDA_ROOT)])

        # Add prompt args
        if prompt:
            cli_args.extend(prompt)

        # Set API env vars
        env = os.environ.copy()

        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            # For disable prompt caching for external API change 0 to 1
            env["DISABLE_PROMPT_CACHING"] = "0"
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key

        # Handle --yes flag for Claude (maps to auto permission mode)
        if yes and permission_mode == DEFAULT_PERMISSION:
            cli_args[cli_args.index("--permission-mode") + 1] = "auto"

        cli_name = "Claude Code"

    elif cli_type == "codex":
        env = os.environ.copy()
        cli_args, codex_env = build_codex_command(
            workspace_path=workspace_path,
            preprompt_content=preprompt_content,
            explicit_model=explicit_model,
            no_mcp=no_mcp,
            http_url=http_url or os.getenv("AIDA_MCP_HTTP_URL"),
            mcp_api_key=mcp_api_key or os.getenv("AIDA_MCP_API_KEY", ""),
            db_url=db_url,
            backend_url=backend_url,
            token=token,
            codex_mcp_python=codex_mcp_python or "python3",
            project_root=str(AIDA_ROOT),
            prompt=prompt,
            yes=yes,
        )
        env.update(codex_env)
        cli_name = "OpenAI Codex CLI"

    elif cli_type == "kimi":
        # Build Kimi Code CLI command (Node.js successor of the legacy Python
        # kimi-cli). The old flags --agent-file, --work-dir, --mcp-config-file
        # and --debug no longer exist:
        # - instructions go to <workspace>/.kimi-code/AGENTS.md
        # - MCP servers go to <workspace>/.kimi-code/mcp.json
        # - the working directory is set via chdir before exec
        generate_kimi_workspace_config(
            preprompt_content, assessment, assessment_id, container_name,
            workspace_path, quiet
        )

        # Same mcpServers JSON format AIDA already generates for the other CLIs;
        # Kimi Code CLI picks it up from the project-level mcp.json.
        if not no_mcp and MCP_CONFIG_FILE.exists():
            kimi_mcp_file = Path(workspace_path) / KIMI_WORKSPACE_CONFIG_DIR / "mcp.json"
            kimi_mcp_file.write_text(MCP_CONFIG_FILE.read_text())
            # Token is embedded in plaintext — restrict to owner only.
            kimi_mcp_file.chmod(0o600)
            if not quiet:
                console.print(f"[dim]✓ Kimi MCP config: {kimi_mcp_file}[/dim]")

        cli_args = ["kimi"]

        # Add model if specified
        if explicit_model:
            cli_args.extend(["--model", explicit_model])

        if prompt:
            # Non-interactive mode auto-approves tool calls by default and
            # rejects --yolo, so the two must stay mutually exclusive.
            cli_args.extend(["--prompt", " ".join(prompt)])
        elif yes:
            # Add yolo mode for auto-approval (--yes flag or explicitly requested)
            cli_args.append("--yolo")

        # Kimi doesn't need the env vars for API (uses its own config)
        env = os.environ.copy()

        cli_name = "Kimi Code CLI"

    elif cli_type in ("gemini", "cursor"):
        generate_scoped_client_config(
            cli_type,
            workspace_path=workspace_path,
            preprompt_content=preprompt_content,
            no_mcp=no_mcp,
            http_url=http_url or os.getenv("AIDA_MCP_HTTP_URL"),
            mcp_api_key=mcp_api_key or os.getenv("AIDA_MCP_API_KEY", ""),
            token=token,
            backend_url=backend_url,
            db_url=db_url,
            quiet=quiet,
        )
        if cli_type == "gemini":
            cli_args = build_gemini_command(
                explicit_model=explicit_model, prompt=prompt, yes=yes,
            )
            cli_name = "Gemini CLI"
        else:
            cli_args = build_cursor_command(
                workspace_path=workspace_path,
                explicit_model=explicit_model,
                prompt=prompt,
                yes=yes,
            )
            cli_name = "Cursor Agent CLI"
        env = os.environ.copy()

    else:  # cli_type == "qwen"
        # Build Qwen Code CLI command
        # Qwen uses TWO config files:
        # 1. .qwen/settings.json - MCP servers, models, API keys
        # 2. QWEN.md - System prompt (markdown file)
        # Config can be in workspace (project) or ~/.qwen (global)
        
        # Create Qwen settings content
        def create_qwen_settings():
            # Determine auth type: use qwen-oauth by default, openai if API key/base URL provided
            auth_type = "qwen-oauth"
            if api_key or base_url:
                auth_type = "openai"
            
            settings = {
                "modelProviders": {
                    "openai": [
                        {
                            "id": explicit_model if explicit_model else "coder-model",
                            "name": explicit_model if explicit_model else "Qwen Coder",
                        }
                    ]
                },
                "security": {
                    "auth": {
                        "selectedType": auth_type
                    }
                }
            }
            
            # Add API key if provided (for openai auth)
            if api_key:
                settings["modelProviders"]["openai"][0]["apiKey"] = api_key
            
            if base_url:
                settings["modelProviders"]["openai"][0]["baseUrl"] = base_url
            
            # Scope all MCP credentials to this assessment workspace.
            python_bin_str = "python3"
            if not no_mcp and not (http_url or os.getenv("AIDA_MCP_HTTP_URL")):
                try:
                    python_bin_str = str(ensure_backend_venv(quiet=True).absolute())
                except Exception:
                    pass
            settings["mcpServers"] = build_qwen_mcp_servers(
                token=token,
                backend_url=backend_url,
                db_url=db_url,
                no_mcp=no_mcp,
                http_url=http_url or os.getenv("AIDA_MCP_HTTP_URL"),
                mcp_api_key=mcp_api_key or os.getenv("AIDA_MCP_API_KEY"),
                python_bin=python_bin_str,
            )
            
            return settings
        
        qwen_settings = create_qwen_settings()

        # Determine config location
        # Qwen reads QWEN.md from workspace root, and .qwen/settings.json from workspace
        workspace_qwen_dir = Path(workspace_path) / ".qwen"
        
        # Try to create config in workspace
        config_dir = None
        config_location = ""
        
        try:
            workspace_qwen_dir.mkdir(parents=True, exist_ok=True)
            # Test if we can write to it
            test_file = workspace_qwen_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            config_dir = workspace_qwen_dir
            config_location = "workspace"
        except (PermissionError, OSError) as e:
            # Can't write to workspace - this is a critical error
            # We don't fallback to ~/.qwen/ to avoid cross-assessment config pollution
            if not quiet:
                console.print("[red]✗ Cannot write to workspace configuration directory[/red]")
                console.print(f"[dim]  Error: {e}[/dim]")
                console.print("\n[yellow]Troubleshooting:[/yellow]")
                console.print("  • Check workspace permissions:")
                console.print(f"    [cyan]ls -la {workspace_path}[/cyan]")
                console.print("  • Fix ownership:")
                console.print(f"    [cyan]sudo chown -R $USER:$USER {workspace_path}[/cyan]\n")
            sys.exit(1)

        if not quiet:
            console.print(f"[dim]✓ Qwen config: {config_location} directory[/dim]")
            console.print(f"[dim]  Path: {config_dir}[/dim]")

        # Write settings.json
        settings_file = config_dir / "settings.json"
        settings_file.write_text(json.dumps(qwen_settings, indent=2))
        # The file may contain a provider key or HTTP MCP bearer.
        settings_file.chmod(0o600)

        # Write QWEN.md at workspace ROOT (not in .qwen/)
        # Qwen Code reads QWEN.md from project root, like CLAUDE.md for Claude Code
        qwen_md_file = Path(workspace_path) / "QWEN.md"
        qwen_md_file.write_text(preprompt_content)
        
        if not quiet and debug:
            console.print(f"[dim]✓ System prompt: {qwen_md_file.name} (workspace root)[/dim]\n")

        # Qwen CLI command (validated against Qwen Code 0.26).
        cli_args = build_qwen_command(explicit_model=explicit_model, prompt=prompt, yes=yes)

        env = os.environ.copy()
        cli_name = "Qwen Code CLI"

    # Display launch banner
    if not quiet:
        console.print()

        # Determine permission display text
        if cli_type == "claude":
            permission_text = "accept (auto)" if yes else permission_mode
        elif cli_type == "codex":
            permission_text = "full access (auto)" if yes else "workspace-write / on-request"
        else:
            permission_text = "yolo (auto)" if yes else "interactive"

        # Build panel content
        if explicit_model:
            panel_content = f"""[bold cyan]AIDA Security Assessment Assistant[/bold cyan]

[dim]CLI:[/dim]            {cli_name}
[dim]Model:[/dim]        {explicit_model}
[dim]Permission:[/dim]   {permission_text}
[dim]MCP Server:[/dim]   {"[green]Enabled[/green]" if not no_mcp else "[yellow]Disabled[/yellow]"}
[dim]Directory:[/dim]    {workspace_path}"""
        else:
            panel_content = f"""[bold cyan]AIDA Security Assessment Assistant[/bold cyan]

[dim]CLI:[/dim]            {cli_name}
[dim]Permission:[/dim]   {permission_text}
[dim]MCP Server:[/dim]   {"[green]Enabled[/green]" if not no_mcp else "[yellow]Disabled[/yellow]"}
[dim]Directory:[/dim]    {workspace_path}"""

        if assessment:
            panel_content += f"\n[dim]Assessment:[/dim]  [cyan]{assessment}[/cyan] [dim](ID: {assessment_id})[/dim]"

        if cli_type == "claude" and base_url:
            panel_content += f"\n[dim]API:[/dim]         {base_url}"

        panel = Panel(panel_content, border_style="blue", box=box.DOUBLE, padding=(1, 2))
        console.print(panel)
        console.print()

    # Launch CLI
    if not quiet:
        console.print(f"[dim]Starting {cli_name}...[/dim]\n")
    else:
        console.print(f"[cyan]AIDA[/cyan] → {assessment or 'AIDA Project'} ({cli_name})\n")

    try:
        if cli_type == "claude":
            os.chdir(workspace_path)
            os.execvpe("claude", cli_args, env)
        elif cli_type == "codex":
            os.execvpe("codex", cli_args, env)
        elif cli_type == "kimi":
            # Kimi Code CLI has no --work-dir flag: it runs in the cwd
            os.chdir(workspace_path)
            os.execvpe("kimi", cli_args, env)
        elif cli_type in ("gemini", "cursor"):
            os.chdir(workspace_path)
            executable = CLI_CAPABILITIES[cli_type]["executable"]
            os.execvpe(executable, cli_args, env)
        else:  # qwen
            os.chdir(workspace_path)
            os.execvpe("qwen", cli_args, env)
    except FileNotFoundError as e:
        console.print(f"[red]Failed to launch {cli_name}: {e}[/red]")
        # Most common cause: backend returned a host path that doesn't exist
        # on this machine (e.g. Docker Desktop on Windows reported a Windows
        # path while we're running in WSL, or the assessment dir was deleted).
        if workspace_path and not Path(workspace_path).exists():
            console.print(
                f"\n[yellow]The workspace directory does not exist on this host:[/yellow] "
                f"{workspace_path}"
            )
            if _WIN_PATH_RE.match(workspace_path):
                console.print(
                    "[yellow]This looks like a Windows path. If you are running "
                    "AIDA from WSL, ensure `wslpath` is available "
                    "(it ships with WSL by default) and that the C: drive is "
                    "mounted under /mnt/c.[/yellow]"
                )
            elif _is_wsl():
                console.print(
                    "[yellow]Verify the Exegol container's workspace mount with:[/yellow]\n"
                    f"  [cyan]docker inspect {container_name} --format "
                    "'{{json .Mounts}}'[/cyan]"
                )
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to launch {cli_name}: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
