#!/usr/bin/env python3
"""
AIDA CLI Launcher - Professional Python Implementation
AI-Driven Security Assessment - Intelligent wrapper for Claude Code & Kimi CLI
"""
import os
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

console = Console()

# Configuration
AIDA_ROOT = Path(__file__).parent.absolute()
AIDA_CONFIG_DIR = AIDA_ROOT / ".aida"
PREPROMPT_FILE = AIDA_ROOT / "Docs" / "PrePrompt.txt"
MCP_SERVER_PATH = AIDA_ROOT / "backend" / "mcp" / "aida_mcp_server.py"
MCP_CONFIG_FILE = AIDA_CONFIG_DIR / "mcp-config.json"

# Kimi-specific config files
KIMI_AGENT_FILE = AIDA_CONFIG_DIR / "kimi-agent.yaml"
KIMI_SYSTEM_PROMPT_FILE = AIDA_CONFIG_DIR / "kimi-system.md"

DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_PERMISSION = "default"
DEFAULT_BACKEND = "http://localhost:8001/api"

# CLI types
CLIType = Literal["claude", "kimi"]


def ensure_backend_venv(quiet=False) -> Path:
    """Ensure backend venv exists with MCP dependencies installed"""
    backend_dir = AIDA_ROOT / "backend"
    venv_dir = backend_dir / "venv"
    requirements_file = backend_dir / "requirements.txt"
    
    # Check if venv exists
    if not venv_dir.exists():
        if not quiet:
            console.print("[yellow]⚠ Backend venv not found, creating...[/yellow]")
        
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
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
                        timeout=120
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


def detect_python_bin(quiet=False) -> str:
    """Detect Python binary (prefer venv) - returns absolute path"""
    venv_paths = [
        AIDA_ROOT / "backend" / "venv" / "bin" / "python",
        AIDA_ROOT / ".venv" / "bin" / "python",
    ]
    
    for path in venv_paths:
        if path.exists():
            if not quiet:
                console.print(f"[dim]✓ Using venv Python: {path.name}[/dim]")
            return str(path.absolute())  # Return absolute path
    
    if not quiet:
        console.print("[yellow]⚠ Using system python3[/yellow]")
    return "python3"


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


def generate_mcp_config(db_url: str, quiet=False) -> None:
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
    
    config = {
        "mcpServers": {
            "aida-mcp": {
                "command": python_bin_str,
                "args": [str(MCP_SERVER_PATH.absolute())],
                "env": {
                    "PYTHONPATH": str((AIDA_ROOT / "backend").absolute()),
                    "DATABASE_URL": db_url
                }
            }
        }
    }
    
    MCP_CONFIG_FILE.write_text(json.dumps(config, indent=2))
    if not quiet:
        console.print(f"[dim]✓ MCP config: {MCP_CONFIG_FILE.name}[/dim]")
        console.print(f"[dim]  Python: {python_bin_str}[/dim]")


def generate_kimi_agent_file(preprompt_content: str, assessment_name: Optional[str], 
                             assessment_id: Optional[str], container_name: Optional[str],
                             quiet=False) -> Path:
    """Generate Kimi agent YAML file and system prompt markdown"""
    AIDA_CONFIG_DIR.mkdir(exist_ok=True)
    
    # Enhance preprompt with assessment context for Kimi
    enhanced_prompt = preprompt_content
    if assessment_name:
        enhanced_prompt += f"""

## **Assessment Loaded**

**{assessment_name}** (ID: {assessment_id}) - Container: {container_name}

The assessment workspace is ready. Use your standard tools to work with files and execute commands.
"""
    
    # Write system prompt markdown
    KIMI_SYSTEM_PROMPT_FILE.write_text(enhanced_prompt)
    
    # Write agent YAML file
    agent_yaml = f"""version: 1
agent:
  name: aida-security
  extend: default
  system_prompt_path: {KIMI_SYSTEM_PROMPT_FILE.absolute()}
  # AIDA-specific configuration
  system_prompt_args:
    AIDA_VERSION: "1.0"
    ASSESSMENT_NAME: "{assessment_name or 'None'}"
"""
    
    KIMI_AGENT_FILE.write_text(agent_yaml)
    
    if not quiet:
        console.print(f"[dim]✓ Kimi agent config: {KIMI_AGENT_FILE.name}[/dim]")
    
    return KIMI_AGENT_FILE


def detect_cli() -> CLIType:
    """Detect which CLI is available (claude or kimi)"""
    # Check for Claude
    result = subprocess.run(["which", "claude"], capture_output=True)
    if result.returncode == 0:
        return "claude"
    
    # Check for Kimi
    result = subprocess.run(["which", "kimi"], capture_output=True)
    if result.returncode == 0:
        return "kimi"
    
    return None


def resolve_workspace(assessment_name: str, backend_url: str) -> Optional[dict]:
    """Resolve assessment workspace via API, with retry on transient network errors"""
    import time

    max_retries = 3
    retry_delays = [1, 2, 4]  # exponential backoff in seconds

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{backend_url}/workspace/resolve",
                    params={"assessment_name": assessment_name}
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
    
    # Check if Exegol is installed
    if not check_exegol_installed():
        console.print("[yellow]⚠ Exegol container not detected on this system[/yellow]\n")
        console.print("[bold]AIDA requires Exegol to execute pentesting commands.[/bold]")
        console.print("Without Exegol, the AI cannot run security tools.\n")
    
    sys.exit(1)


def show_cli_not_found():
    """Display error when neither Claude nor Kimi CLI is found"""
    console.print("[red]✗ No compatible AI CLI found[/red]\n")
    console.print("Please install one of the following:\n")
    console.print("[bold]Claude Code:[/bold]")
    console.print("  [cyan]curl -fsSL https://claude.ai/install.sh | bash[/cyan]\n")
    console.print("[bold]Kimi CLI:[/bold]")
    console.print("  [cyan]pip install kimi-cli[/cyan]")
    console.print("  or")
    console.print("  [cyan]uv tool install kimi-cli[/cyan]\n")
    sys.exit(1)


@click.command()
@click.option("-a", "--assessment", help="Load specific assessment")
@click.option("-m", "--model", default=None, help="Model to use (optional, uses CLI default if not specified)")
@click.option("--permission-mode", default=None, help=f"Permission mode for Claude Code: auto, default, dontAsk, acceptEdits, bypassPermissions, plan (default: {DEFAULT_PERMISSION})")
@click.option("--preprompt", type=click.Path(exists=False), help="Path to custom preprompt file (default: Docs/PrePrompt.txt)")
@click.option("--base-url", help="Custom API base URL (Claude Code only)")
@click.option("--api-key", help="API authentication token (Claude Code only)")
@click.option("--no-mcp", is_flag=True, help="Disable MCP server")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (minimal output)")
@click.option("--cli", "cli_choice", type=click.Choice(["claude", "kimi", "auto"]), default="auto",
              help="Which CLI to use (default: auto-detect)")
@click.option("-y", "--yes", is_flag=True, help="Auto-approve all actions (Kimi: --yolo, Claude: permission-mode=auto)")
@click.argument("prompt", nargs=-1)
def main(assessment, model, permission_mode, preprompt, base_url, api_key, no_mcp, debug, quiet, cli_choice, yes, prompt):
    """AIDA CLI Launcher - AI-Driven Security Assessment
    
    Supports both Claude Code and Kimi CLI as underlying AI agents.
    """
    
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
        result = subprocess.run(["which", cli_choice], capture_output=True)
        if result.returncode != 0:
            console.print(f"[red]✗ {cli_choice.title()} CLI not found in PATH[/red]")
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
    db_url = os.getenv("DATABASE_URL", "postgresql://aida:aida@localhost:5434/aida_assessments")
    
    # Interactive assessment selection if none provided
    if not assessment:
        console.print()
        console.print("[bold cyan]AIDA Security Assessment Assistant[/bold cyan]")
        console.print(f"[dim]Using CLI: {cli_type.title()}[/dim]\n")
        
        # Fetch available assessments
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{backend_url}/assessments")
                
                if response.status_code != 200:
                    console.print("[red]Failed to fetch assessments from backend[/red]\n")
                    sys.exit(1)
                
                assessments = response.json()
                
                if not assessments:
                    console.print("[yellow]No assessments found![/yellow]\n")
                    console.print("Create your first assessment:")
                    console.print("  → Open [link=http://localhost:5174]http://localhost:5174[/link]")
                    console.print('  → Click "New Assessment"\n')
                    sys.exit(1)
                
                # Display selection menu
                console.print("[bold]Select an assessment:[/bold]\n")
                
                table = Table(show_header=False, box=None, padding=(0, 2))
                table.add_column(style="cyan bold", justify="right", width=4)
                table.add_column()
                table.add_column(style="dim", no_wrap=True)
                
                for i, a in enumerate(assessments, 1):
                    container = a.get('container_name', 'N/A')
                    table.add_row(f"{i}.", a['name'], f"({container})")
                
                console.print(table)
                console.print()
                
                # Get user input
                try:
                    choice = console.input("[bold]Enter number (or 'q' to quit): [/bold]")
                    
                    if choice.lower() == 'q':
                        console.print("\nCancelled.\n")
                        sys.exit(0)
                    
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
    if not no_mcp:
        if not MCP_SERVER_PATH.exists():
            console.print(f"[red]✗ MCP server not found: {MCP_SERVER_PATH}[/red]\n")
            sys.exit(1)
        generate_mcp_config(db_url, quiet)
    
    # Workspace resolution
    workspace_path = str(AIDA_ROOT)
    assessment_id = None
    container_name = None
    
    if assessment:
        if not quiet and debug:
            console.print(f"[dim]Resolving workspace for: {assessment}[/dim]")
        
        result = resolve_workspace(assessment, backend_url)
        
        if not result or not result.get("success"):
            show_assessment_not_found(assessment, backend_url)
        
        # Extract workspace info
        workspace_path = result["host_path"]
        assessment_id = result["assessment_id"]
        container_name = result["container_name"]
        
        if not quiet and debug:
            console.print(f"[dim]✓ Container: {container_name}[/dim]")
            console.print(f"[dim]✓ Workspace: {workspace_path}[/dim]\n")
        
        # For Claude: enhance preprompt with assessment context
        if cli_type == "claude":
            preprompt_content += f"""

## **Assessment Loaded**

**{assessment}** (ID: {assessment_id}) - Container: {container_name}

The assessment workspace is ready. Use your standard tools to work with files and execute commands.
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

        # 🔧 FIX: Force disable prompt caching for Vertex AI compatibility
        env["DISABLE_PROMPT_CACHING"] = "1"

        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key

        # Handle --yes flag for Claude (maps to auto permission mode)
        if yes and permission_mode == DEFAULT_PERMISSION:
            cli_args[cli_args.index("--permission-mode") + 1] = "auto"

        cli_name = "Claude Code"

    else:  # cli_type == "kimi"
        # Build Kimi CLI command
        # Generate agent file for Kimi
        agent_file = generate_kimi_agent_file(
            preprompt_content, assessment, assessment_id, container_name, quiet
        )

        cli_args = [
            "kimi",
            "--agent-file", str(agent_file),
            "--work-dir", workspace_path,
        ]

        # Add model if specified
        if explicit_model:
            cli_args.extend(["--model", explicit_model])

        # Add MCP config
        if not no_mcp:
            cli_args.extend(["--mcp-config-file", str(MCP_CONFIG_FILE)])

        if debug:
            cli_args.append("--debug")

        # Add yolo mode for auto-approval (--yes flag or explicitly requested)
        if yes:
            cli_args.append("--yolo")

        # Add prompt if provided
        if prompt:
            cli_args.extend(["--prompt", " ".join(prompt)])

        # Kimi doesn't need the env vars for API (uses its own config)
        env = os.environ.copy()

        cli_name = "Kimi CLI"
    
    # Display launch banner
    if not quiet:
        console.print()
        
        # Main info panel
        panel_content = f"""[bold cyan]AIDA Security Assessment Assistant[/bold cyan]

[dim]CLI:[/dim]            {cli_name}
[dim]Permission:[/dim]   {"accept (auto)" if yes else permission_mode if cli_type == "claude" else "interactive"}
[dim]MCP Server:[/dim]   {"[green]Enabled[/green]" if not no_mcp else "[yellow]Disabled[/yellow]"}
[dim]Directory:[/dim]    {workspace_path}"""
        
        if explicit_model:
            panel_content = f"""[bold cyan]AIDA Security Assessment Assistant[/bold cyan]

[dim]CLI:[/dim]            {cli_name}
[dim]Model:[/dim]        {explicit_model}
[dim]Permission:[/dim]   {"accept (auto)" if yes else permission_mode if cli_type == "claude" else "interactive"}
[dim]MCP Server:[/dim]   {"[green]Enabled[/green]" if not no_mcp else "[yellow]Disabled[/yellow]"}
[dim]Directory:[/dim]    {workspace_path}"""
        
        if assessment:
            panel_content += f"\n[dim]Assessment:[/dim]  [cyan]{assessment}[/cyan] [dim](ID: {assessment_id})[/dim]"
        
        if cli_type == "claude" and base_url:
            panel_content += f"\n[dim]API:[/dim]         {base_url}"
        
        panel = Panel(
            panel_content,
            border_style="blue",
            box=box.DOUBLE,
            padding=(1, 2)
        )
        console.print(panel)
        console.print()
    
    # Launch CLI
    if not quiet:
        console.print(f"[dim]Starting {cli_name}...[/dim]\n")
    else:
        # Minimal output in quiet mode
        console.print(f"[cyan]AIDA[/cyan] → {assessment or 'AIDA Project'} ({cli_name})\n")
    
    try:
        if cli_type == "claude":
            # Claude requires changing to workspace dir
            os.chdir(workspace_path)
            os.execvpe("claude", cli_args, env)
        else:
            # Kimi handles work-dir via flag, no need to chdir
            os.execvpe("kimi", cli_args, env)
    except Exception as e:
        console.print(f"[red]Failed to launch {cli_name}: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
