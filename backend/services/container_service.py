"""
Container Service - Docker container management and command execution for pentesting containers
"""
import asyncio
import json
import shlex
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models import CommandHistory, Assessment
from models.platform_settings import PlatformSettings
from config import settings
from utils.logger import get_logger
from utils.log_context import log_context, timed_operation
from websocket.manager import manager
from websocket.events import event_command_completed, event_command_failed, EventType, create_event

logger = get_logger(__name__)


class ContainerService:
    def __init__(self):
        self.current_container: Optional[str] = settings.DEFAULT_CONTAINER_NAME
        self.containers_cache: List[Dict[str, Any]] = []
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 30
        self.container_health_cache: Dict[str, tuple[float, str, bool]] = {}
        self.health_cache_ttl: int = 30
        self.max_health_cache_entries: int = 100

    def _clean_health_cache(self):
        """Remove expired entries from health cache to prevent memory leak"""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, (timestamp, _, _) in self.container_health_cache.items()
            if (current_time - timestamp) > self.health_cache_ttl
        ]
        for key in expired_keys:
            del self.container_health_cache[key]
        
        # If still too many entries, remove oldest
        if len(self.container_health_cache) > self.max_health_cache_entries:
            sorted_items = sorted(
                self.container_health_cache.items(),
                key=lambda x: x[1][0]
            )
            self.container_health_cache = dict(sorted_items[-self.max_health_cache_entries:])

    @staticmethod
    def _sanitize_output(output: str) -> str:
        """Sanitize command output to remove null bytes and invalid UTF-8 characters

        PostgreSQL with UTF-8 encoding cannot store null bytes (0x00) or invalid UTF-8 sequences.
        This function cleans the output to ensure it can be safely stored in the database.

        Args:
            output: Raw command output string

        Returns:
            Sanitized string safe for PostgreSQL UTF-8 storage
        """
        if not output:
            return output

        # Remove null bytes (0x00) - PostgreSQL UTF-8 cannot store them
        sanitized = output.replace('\x00', '')

        # Encode to UTF-8, replacing invalid sequences with replacement character
        # This handles any other encoding issues
        sanitized = sanitized.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

        return sanitized

    async def _run_command(self, command: List[str], timeout: float = 30.0) -> Dict[str, Any]:
        """Run a system command with a timeout to prevent hangs on docker socket issues"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode('utf-8', errors='replace').strip(),
                "stderr": stderr.decode('utf-8', errors='replace').strip(),
            }

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.communicate()
            except Exception:
                pass
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
            }

        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }

    async def discover_containers(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Discover Exegol containers"""
        current_time = time.time()

        if (not force_refresh and
                self.containers_cache and
                (current_time - self.cache_timestamp) < self.cache_ttl):
            return self.containers_cache

        containers = []

        try:
            result = await self._run_command([
                "docker", "ps", "-a",
                "--format", "json"
            ])

            if result["success"] and result["stdout"]:
                for line in result["stdout"].split('\n'):
                    if line.strip():
                        try:
                            container_data = json.loads(line)
                            container_name = container_data.get("Names", "unknown").lstrip('/')
                            image = container_data.get("Image", "")

                            # Accept containers matching any configured prefix (aida-, exegol-, ...)
                            allowed_prefixes = tuple(
                                p.strip() for p in settings.CONTAINER_PREFIX_FILTER.split(",") if p.strip()
                            )
                            if container_name.lower().startswith(allowed_prefixes):
                                containers.append({
                                    "name": container_name,
                                    "image": image,
                                    "status": container_data.get("State", "unknown"),
                                    "id": container_data.get("ID", "unknown")[:12],
                                })
                        except json.JSONDecodeError:
                            continue

        except Exception:
            containers = []

        self.containers_cache = containers
        self.cache_timestamp = current_time
        return containers

    async def select_container(self, container_name: str) -> Dict[str, Any]:
        """Select active container"""
        containers = await self.discover_containers()

        if any(c["name"] == container_name for c in containers):
            self.current_container = container_name
            return {
                "success": True,
                "message": f"Container '{container_name}' selected"
            }
        else:
            return {
                "success": False,
                "error": f"Container '{container_name}' not found"
            }

    async def validate_container_status(self) -> Dict[str, Any]:
        """Validate and potentially start the current container (with 30s cache)"""
        if not self.current_container:
            return {"success": False, "error": "No container selected"}

        # Clean expired cache entries
        self._clean_health_cache()

        # Check cache first - avoid docker inspect overhead
        current_time = time.time()
        if self.current_container in self.container_health_cache:
            cached_time, cached_status, is_running = self.container_health_cache[self.current_container]

            # Cache hit - return cached result
            if (current_time - cached_time) < self.health_cache_ttl:
                if is_running:
                    return {"success": True, "status": "running"}
                else:
                    return {"success": False, "error": f"Container in invalid state: {cached_status}"}

        try:
            # Cache miss/expired - perform docker inspect
            result = await self._run_command([
                "docker", "inspect", self.current_container, "--format", "{{.State.Status}}"
            ])

            if not result["success"]:
                return {"success": False, "error": "Container not found", "details": result["stderr"]}

            status = result["stdout"].strip()

            if status == "running":
                # Cache running state
                self.container_health_cache[self.current_container] = (current_time, status, True)
                return {"success": True, "status": "running"}
            elif status in ["created", "exited"]:
                # Try to start the container
                start_result = await self._run_command([
                    "docker", "start", self.current_container
                ])

                if start_result["success"]:
                    # Cache newly started state
                    self.container_health_cache[self.current_container] = (time.time(), "running", True)
                    return {"success": True, "status": "started"}
                else:
                    # Cache failed state
                    self.container_health_cache[self.current_container] = (current_time, status, False)
                    return {
                        "success": False,
                        "error": f"Failed to start container",
                        "details": start_result["stderr"]
                    }
            else:
                # Cache invalid state
                self.container_health_cache[self.current_container] = (current_time, status, False)
                return {"success": False, "error": f"Container in invalid state: {status}"}

        except Exception as e:
            return {"success": False, "error": f"Container validation failed: {str(e)}"}

    async def execute_container_command(
        self,
        command: str,
        working_directory: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a command in the current pentesting container

        Args:
            command: The command to execute
            working_directory: Optional directory to cd into before executing the command
        """
        if not self.current_container:
            return {
                "success": False,
                "error": "No container selected"
            }

        # Validate container before execution
        validation = await self.validate_container_status()
        if not validation["success"]:
            return {
                "success": False,
                "container": self.current_container,
                "command": command,
                "error": f"Container validation failed: {validation['error']}",
                "stdout": "",
                "stderr": validation.get("details", validation["error"]),
                "returncode": -1,
                "execution_time": 0
            }

        start_time = time.time()

        # If working_directory is specified, cd into it before executing command
        # Disable RVM/chpwd hooks that cause noise in stderr
        if working_directory:
            wrapped_command = f"unset -f cd 2>/dev/null; source /root/.bashrc 2>/dev/null && cd {working_directory} 2>/dev/null && {command}"
        else:
            wrapped_command = f"unset -f cd 2>/dev/null; source /root/.bashrc 2>/dev/null && {command}"

        result = await self._run_command([
            "docker", "exec", self.current_container, "bash", "-c", wrapped_command
        ])

        execution_time = time.time() - start_time

        # Filter out RVM/chpwd noise from stderr
        stderr = result["stderr"]
        if stderr:
            # Remove RVM chpwd errors which are just noise
            stderr_lines = [
                line for line in stderr.split('\n')
                if not ('chpwd' in line or 'rvm/scripts' in line or 'bash_zsh_support' in line)
            ]
            stderr = '\n'.join(stderr_lines).strip()

        # Consider command successful if returncode is 0, regardless of stderr noise
        is_success = result["returncode"] == 0

        return {
            "success": is_success,
            "container": self.current_container,
            "command": command,
            "stdout": result["stdout"],
            "stderr": stderr,
            "returncode": result["returncode"],
            "execution_time": execution_time,
        }

    async def execute_and_log_command(
        self,
        assessment_id: int,
        command: str,
        phase: Optional[str],
        db: AsyncSession,
        timeout: Optional[int] = None
    ) -> CommandHistory:
        """Execute command with timeout and log it to database (async optimized)"""
        # Get timeout from database settings, or fall back to config default
        if timeout is None:
            stmt = select(PlatformSettings).filter(
                PlatformSettings.key == "command_timeout"
            )
            result = await db.execute(stmt)
            timeout_setting = result.scalar_one_or_none()

            if timeout_setting:
                try:
                    timeout = int(timeout_setting.value)
                except ValueError:
                    timeout = settings.COMMAND_TIMEOUT
            else:
                timeout = settings.COMMAND_TIMEOUT

        # Get container name from database settings, or fall back to config default
        stmt = select(PlatformSettings).filter(
            PlatformSettings.key == "container_name"
        )
        result = await db.execute(stmt)
        container_setting = result.scalar_one_or_none()

        if container_setting and container_setting.value:
            self.current_container = container_setting.value
        else:
            self.current_container = settings.DEFAULT_CONTAINER_NAME

        # Get workspace_path from assessment to execute commands in the right directory
        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()

        working_directory = None
        if assessment:
            # If workspace_path doesn't exist in DB, create it
            if not assessment.workspace_path:
                # Create workspace without db parameter to avoid session mixing
                workspace_result = await self.create_workspace(
                    assessment_name=assessment.name,
                    db=None  # Don't pass DB to avoid sync/async mixing
                )
                # Update workspace_path and container_name using async session only
                stmt = (
                    update(Assessment)
                    .where(Assessment.id == assessment_id)
                    .values(
                        workspace_path=workspace_result["workspace_path"],
                        container_name=workspace_result["container_name"]
                    )
                )
                await db.execute(stmt)
                await db.commit()
                # Refresh the assessment object with new values
                await db.refresh(assessment)
                assessment.workspace_path = workspace_result["workspace_path"]
                assessment.container_name = workspace_result["container_name"]
            else:
                # Workspace path exists in DB, but ensure it exists in current container
                # This handles cases where container_name setting changed after workspace creation
                workspace_check = await self._run_command([
                    "docker", "exec", self.current_container, "test", "-d", assessment.workspace_path
                ])

                if workspace_check["returncode"] != 0:
                    # Workspace doesn't exist in current container, create it
                    logger.warning(
                        "Workspace directory missing in container, creating it",
                        workspace_path=assessment.workspace_path,
                        container=self.current_container,
                        assessment_id=assessment_id
                    )
                    # Extract assessment name from path or use existing workspace_path
                    subdirs = ['recon', 'exploits', 'loot', 'notes', 'scripts', 'context']
                    subdir_paths = [f"{assessment.workspace_path}/{subdir}" for subdir in subdirs]
                    all_paths = [assessment.workspace_path] + subdir_paths
                    mkdir_command = f"mkdir -p {' '.join(shlex.quote(p) for p in all_paths)}"

                    await self._run_command([
                        "docker", "exec", self.current_container, "bash", "-c", mkdir_command
                    ])

            working_directory = assessment.workspace_path

        # Create command log entry BEFORE execution (status: running)
        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command=command,
            phase=phase,
            status="running"
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            # Execute command with timeout and in the assessment's workspace
            result = await asyncio.wait_for(
                self.execute_container_command(
                    command=command,
                    working_directory=working_directory
                ),
                timeout=timeout
            )

            # Success - update command log (sanitize output to remove null bytes)
            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)

            # Broadcast WebSocket event
            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            command_dict['assessment_name'] = assessment.name if assessment else None

            if command_log.success:
                await manager.broadcast(
                    event_command_completed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )
            else:
                await manager.broadcast(
                    event_command_failed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )

            return command_log

        except asyncio.TimeoutError:
            # TIMEOUT! Mark as timeout status
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"Command exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout

            await db.commit()
            await db.refresh(command_log)

            # Broadcast WebSocket event for timeout
            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            await manager.broadcast(
                create_event(
                    EventType.COMMAND_TIMEOUT,
                    {"command": command_dict},
                    assessment_id=assessment_id
                ),
                assessment_id=assessment_id
            )

            return command_log

    async def execute_python_stdin(
        self,
        code: str,
        working_directory: Optional[str] = None,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """Execute Python code via stdin to avoid heredoc escaping issues.

        Uses `docker exec -i python3 -` and pipes the code directly via stdin.
        No temp files, no shell escaping required.

        Args:
            code: Python source code to execute
            working_directory: Optional working directory inside the container
            timeout: Execution timeout in seconds

        Returns:
            Dict with success, stdout, stderr, returncode, execution_time, container
        """
        if not self.current_container:
            return {
                "success": False,
                "error": "No container selected",
                "stdout": "",
                "stderr": "No container selected",
                "returncode": -1,
                "execution_time": 0,
            }

        start_time = time.time()

        docker_cmd = ["docker", "exec", "-i"]
        if working_directory:
            docker_cmd += ["-w", working_directory]
        docker_cmd += [
            "-e", "PYTHONUNBUFFERED=1",
            self.current_container,
            "python3", "-"
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=code.encode('utf-8')),
                timeout=timeout
            )

            execution_time = time.time() - start_time

            return {
                "success": process.returncode == 0,
                "stdout": self._sanitize_output(stdout_bytes.decode('utf-8', errors='replace')),
                "stderr": self._sanitize_output(stderr_bytes.decode('utf-8', errors='replace')),
                "returncode": process.returncode,
                "execution_time": execution_time,
                "container": self.current_container,
            }

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.communicate()
            except Exception:
                pass
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Python execution timed out after {timeout}s",
                "returncode": -1,
                "execution_time": timeout,
                "container": self.current_container,
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "execution_time": time.time() - start_time,
                "container": self.current_container,
            }

    async def execute_and_log_python(
        self,
        assessment_id: int,
        code: str,
        phase: Optional[str],
        db: AsyncSession,
        timeout: Optional[int] = None
    ) -> "CommandHistory":
        """Execute Python code via stdin and log it to the database.

        Mirrors execute_and_log_command() but uses execute_python_stdin() and
        stores command_type='python' + source_code=code in CommandHistory.

        Args:
            assessment_id: Assessment to associate the command with
            code: Python source code to execute
            phase: Current assessment phase (for logging)
            db: Async database session
            timeout: Optional execution timeout override

        Returns:
            CommandHistory instance with execution results
        """
        # --- Resolve timeout from DB settings ---
        if timeout is None:
            stmt = select(PlatformSettings).filter(
                PlatformSettings.key == "command_timeout"
            )
            result = await db.execute(stmt)
            timeout_setting = result.scalar_one_or_none()
            try:
                timeout = int(timeout_setting.value) if timeout_setting else settings.COMMAND_TIMEOUT
            except ValueError:
                timeout = settings.COMMAND_TIMEOUT

        # --- Resolve container from DB settings ---
        stmt = select(PlatformSettings).filter(PlatformSettings.key == "container_name")
        result = await db.execute(stmt)
        container_setting = result.scalar_one_or_none()
        self.current_container = (
            container_setting.value if (container_setting and container_setting.value)
            else settings.DEFAULT_CONTAINER_NAME
        )

        # --- Resolve workspace path from assessment ---
        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()

        working_directory = None
        if assessment:
            if not assessment.workspace_path:
                workspace_result = await self.create_workspace(
                    assessment_name=assessment.name,
                    db=None
                )
                stmt = (
                    update(Assessment)
                    .where(Assessment.id == assessment_id)
                    .values(
                        workspace_path=workspace_result["workspace_path"],
                        container_name=workspace_result["container_name"]
                    )
                )
                await db.execute(stmt)
                await db.commit()
                await db.refresh(assessment)
                assessment.workspace_path = workspace_result["workspace_path"]
            else:
                workspace_check = await self._run_command([
                    "docker", "exec", self.current_container, "test", "-d", assessment.workspace_path
                ])
                if workspace_check["returncode"] != 0:
                    subdirs = ['recon', 'exploits', 'loot', 'notes', 'scripts', 'context']
                    subdir_paths = [f"{assessment.workspace_path}/{subdir}" for subdir in subdirs]
                    all_paths = [assessment.workspace_path] + subdir_paths
                    mkdir_command = f"mkdir -p {' '.join(shlex.quote(p) for p in all_paths)}"
                    await self._run_command([
                        "docker", "exec", self.current_container, "bash", "-c", mkdir_command
                    ])

            working_directory = assessment.workspace_path

        # --- Create log entry (status: running) ---
        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command="python3 -",
            phase=phase,
            status="running",
            command_type="python",
            source_code=code,
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            result = await asyncio.wait_for(
                self.execute_python_stdin(
                    code=code,
                    working_directory=working_directory,
                    timeout=timeout
                ),
                timeout=timeout + 5  # small buffer around inner timeout
            )

            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)

            # WebSocket broadcast
            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            command_dict['assessment_name'] = assessment.name if assessment else None
            if command_log.success:
                await manager.broadcast(
                    event_command_completed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )
            else:
                await manager.broadcast(
                    event_command_failed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )

            return command_log

        except asyncio.TimeoutError:
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"Python execution exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout

            await db.commit()
            await db.refresh(command_log)

            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            await manager.broadcast(
                create_event(
                    EventType.COMMAND_TIMEOUT,
                    {"command": command_dict},
                    assessment_id=assessment_id
                ),
                assessment_id=assessment_id
            )

            return command_log

    def _generate_http_python_script(self, params) -> str:
        """Generate a Python requests script from HttpRequestRequest params.

        The script is designed to be piped via stdin to `python3 -` inside Exegol.
        Produces human-readable output: status line, headers, optional cookies, body.

        Args:
            params: HttpRequestRequest instance (already credential-substituted)

        Returns:
            Python source code as a string (no shell escaping needed)
        """
        import json as _json

        method = params.method.upper()
        url = params.url
        headers = params.headers or {}
        query_params = params.params or {}
        cookies = params.cookies or {}
        timeout = params.timeout
        follow_redirects = params.follow_redirects
        verify_ssl = params.verify_ssl

        # Build auth tuple representation
        if params.auth and len(params.auth) >= 2:
            auth_repr = repr(tuple(params.auth[:2]))
        else:
            auth_repr = "None"

        # Build proxy dict from single string
        if params.proxy:
            proxy_repr = repr({"http": params.proxy, "https": params.proxy})
        else:
            proxy_repr = "None"

        # Build body line: json_body takes priority over data
        if params.json_body is not None:
            body_line = f"    json={_json.dumps(params.json_body)!r},"
        elif params.data is not None:
            body_line = f"    data={params.data!r},"
        else:
            body_line = "    data=None,"

        script = f"""\
import requests, json as _json, time, sys

_start = time.time()
_session = requests.Session()
_session.verify = {verify_ssl!r}

try:
    _resp = _session.request(
        method={method!r},
        url={url!r},
        headers={headers!r},
        params={query_params!r},
{body_line}
        cookies={cookies!r},
        auth={auth_repr},
        proxies={proxy_repr},
        timeout={timeout!r},
        allow_redirects={follow_redirects!r},
    )
    _ms = int((time.time() - _start) * 1000)

    # Try to parse JSON response body
    try:
        _body = _json.dumps(_resp.json(), indent=2, ensure_ascii=False)
        _is_json = True
    except Exception:
        _body = _resp.text
        _is_json = False

    print(f"HTTP {{_resp.status_code}} {{_resp.reason}}  [{{_ms}}ms]")
    print(f"URL: {{_resp.url}}")

    if _resp.history:
        _chain = " -> ".join(str(r.status_code) for r in _resp.history)
        print(f"Redirects: {{_chain}} -> {{_resp.status_code}}")

    print("\\n--- Response Headers ---")
    for _k, _v in _resp.headers.items():
        print(f"  {{_k}}: {{_v}}")

    if _resp.cookies:
        print("\\n--- Cookies Set ---")
        for _k, _v in _resp.cookies.items():
            print(f"  {{_k}}: {{_v}}")

    _label = " (JSON)" if _is_json else ""
    print(f"\\n--- Body{{_label}} ---")
    print(_body[:20000])

except requests.exceptions.SSLError as _e:
    print(f"SSL Error: {{_e}}", file=sys.stderr)
    print("Hint: use verify_ssl=false to disable certificate verification", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.ConnectionError as _e:
    print(f"Connection Error: {{_e}}", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.Timeout:
    print(f"Request timed out after {timeout}s", file=sys.stderr)
    sys.exit(1)
except Exception as _e:
    print(f"Error: {{_e}}", file=sys.stderr)
    sys.exit(1)
"""
        return script

    async def execute_and_log_http_request(
        self,
        assessment_id: int,
        params,
        db: AsyncSession,
        timeout: Optional[int] = None
    ) -> "CommandHistory":
        """Execute an HTTP request via Python requests inside Exegol and log it.

        Generates a Python script from the structured HttpRequestRequest params,
        then pipes it via stdin to `python3 -` inside the container (same mechanism
        as execute_and_log_python). Stores command_type='http' in CommandHistory
        with a human-readable command field ('HTTP POST http://target') and the
        generated Python script in source_code.

        Args:
            assessment_id: Assessment to associate with
            params: HttpRequestRequest (already credential-substituted)
            db: Async database session
            timeout: Optional override (defaults to DB command_timeout setting)

        Returns:
            CommandHistory instance with execution results
        """
        # --- Resolve timeout ---
        if timeout is None:
            stmt = select(PlatformSettings).filter(
                PlatformSettings.key == "command_timeout"
            )
            result = await db.execute(stmt)
            timeout_setting = result.scalar_one_or_none()
            try:
                timeout = int(timeout_setting.value) if timeout_setting else settings.COMMAND_TIMEOUT
            except ValueError:
                timeout = settings.COMMAND_TIMEOUT

        # --- Resolve container ---
        stmt = select(PlatformSettings).filter(PlatformSettings.key == "container_name")
        result = await db.execute(stmt)
        container_setting = result.scalar_one_or_none()
        self.current_container = (
            container_setting.value if (container_setting and container_setting.value)
            else settings.DEFAULT_CONTAINER_NAME
        )

        # --- Resolve workspace path ---
        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()

        working_directory = None
        if assessment:
            if not assessment.workspace_path:
                workspace_result = await self.create_workspace(
                    assessment_name=assessment.name,
                    db=None
                )
                stmt = (
                    update(Assessment)
                    .where(Assessment.id == assessment_id)
                    .values(
                        workspace_path=workspace_result["workspace_path"],
                        container_name=workspace_result["container_name"]
                    )
                )
                await db.execute(stmt)
                await db.commit()
                await db.refresh(assessment)
                assessment.workspace_path = workspace_result["workspace_path"]
            else:
                workspace_check = await self._run_command([
                    "docker", "exec", self.current_container, "test", "-d", assessment.workspace_path
                ])
                if workspace_check["returncode"] != 0:
                    subdirs = ['recon', 'exploits', 'loot', 'notes', 'scripts', 'context']
                    subdir_paths = [f"{assessment.workspace_path}/{subdir}" for subdir in subdirs]
                    all_paths = [assessment.workspace_path] + subdir_paths
                    mkdir_command = f"mkdir -p {' '.join(shlex.quote(p) for p in all_paths)}"
                    await self._run_command([
                        "docker", "exec", self.current_container, "bash", "-c", mkdir_command
                    ])

            working_directory = assessment.workspace_path

        # --- Generate Python script ---
        code = self._generate_http_python_script(params)
        display_command = f"HTTP {params.method.upper()} {params.url}"

        # --- Create log entry (status: running) ---
        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command=display_command,
            phase=params.phase,
            status="running",
            command_type="http",
            source_code=code,
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            result = await asyncio.wait_for(
                self.execute_python_stdin(
                    code=code,
                    working_directory=working_directory,
                    timeout=timeout
                ),
                timeout=timeout + 5
            )

            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)

            # WebSocket broadcast
            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            command_dict['assessment_name'] = assessment.name if assessment else None
            if command_log.success:
                await manager.broadcast(
                    event_command_completed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )
            else:
                await manager.broadcast(
                    event_command_failed(assessment_id, command_dict),
                    assessment_id=assessment_id
                )

            return command_log

        except asyncio.TimeoutError:
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"HTTP request exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout

            await db.commit()
            await db.refresh(command_log)

            from schemas.command import CommandResponse
            command_dict = CommandResponse.model_validate(command_log).model_dump(mode='json')
            await manager.broadcast(
                create_event(
                    EventType.COMMAND_TIMEOUT,
                    {"command": command_dict},
                    assessment_id=assessment_id
                ),
                assessment_id=assessment_id
            )

            return command_log

    async def create_workspace(self, assessment_name: str, db: Session = None) -> Dict[str, str]:
        """Create workspace folder in pentesting container with subdirectories

        Creates the directory structure:
        /workspace/{assessment_name}/
        ├── recon/
        ├── exploits/
        ├── loot/
        ├── notes/
        └── scripts/

        Args:
            assessment_name: Name of the assessment
            db: Optional database session to load container_name from PlatformSettings

        Returns:
            Dict with workspace_path and container_name
        """
        # Load container name from database if session provided
        if db:
            container_setting = db.query(PlatformSettings).filter(
                PlatformSettings.key == "container_name"
            ).first()

            if container_setting and container_setting.value:
                self.current_container = container_setting.value
            else:
                self.current_container = settings.DEFAULT_CONTAINER_NAME

        # Sanitize assessment name for filesystem
        safe_name = assessment_name.replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c in ('_', '-'))

        workspace_path = f"{settings.CONTAINER_WORKSPACE_BASE}/{safe_name}"

        # Create main directory and subdirectories in one command
        subdirs = ['recon', 'exploits', 'loot', 'notes', 'scripts', 'context']
        subdir_paths = [f"{workspace_path}/{subdir}" for subdir in subdirs]
        all_paths = [workspace_path] + subdir_paths

        mkdir_command = f"mkdir -p {' '.join(shlex.quote(p) for p in all_paths)}"

        # Create directories in container
        await self.execute_container_command(mkdir_command)

        # Store current container name for return
        current_container = self.current_container

        return {
            "workspace_path": workspace_path,
            "container_name": current_container
        }
