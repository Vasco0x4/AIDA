"""
MCP Classes - AIDA MCP Service with structured logging
"""
import asyncio
import time
import json
import re
import sys
from typing import Any, Dict, List, Optional
from pathlib import Path
import httpx

# Add parent directories to path for utils import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.logger import get_logger
from utils.log_context import set_assessment_id, set_container_name

# Global structured logger
logger = get_logger(__name__)
file_log = logger  # Alias for backward compatibility
log = logger  # Alias for backward compatibility


class AidaMCPService:
    """AIDA MCP service with backend integration and container management"""

    def __init__(self, backend_url: str = None):
        # Load backend URL from environment or use default
        import os
        self.backend_url = backend_url or os.getenv("BACKEND_API_URL", "http://localhost:8001/api")
        self.current_assessment_id: Optional[int] = None
        self.current_assessment_name: Optional[str] = None
        self.http_client: Optional[httpx.AsyncClient] = None

        # Docker/Container management
        self.current_container: Optional[str] = None
        self.claude_container_name: str = os.getenv("DEFAULT_CONTAINER_NAME", "aida-test-pentest")
        self.containers_cache: List[Dict[str, Any]] = []
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 30
        self.command_history: List[Dict[str, Any]] = []
        self.max_history: int = 50
        self.is_initialized: bool = False
        self.tool_cache: Dict[str, bool] = {}
        self.current_target: Optional[str] = None

        # Output formatting settings
        self.output_max_length: int = 5000  # Default value
        self.output_max_length_cache_time: float = 0
        self.output_max_length_cache_ttl: int = 60  # Cache for 60 seconds

        self.python_exec_output_max_length: int = 5000
        self.python_exec_output_max_length_cache_time: float = 0
        self.python_exec_output_max_length_cache_ttl: int = 60

        self.http_request_output_max_length: int = 5000
        self.http_request_output_max_length_cache_time: float = 0
        self.http_request_output_max_length_cache_ttl: int = 60

        # Command history settings
        self.command_history_limit: int = 10  # Default value
        self.command_history_limit_cache_time: float = 0
        self.command_history_limit_cache_ttl: int = 60  # Cache for 60 seconds

    async def initialize(self):
        """Initialize HTTP client and auto-detect containers"""
        self.http_client = httpx.AsyncClient(timeout=120.0)

        if not self.is_initialized:
            file_log.info("Auto-detecting Exegol containers...")
            containers = await self.discover_containers()

            # Look for existing Claude container
            claude_container = next(
                (c for c in containers if c["name"] == self.claude_container_name),
                None
            )

            if claude_container:
                self.current_container = self.claude_container_name
                file_log.info(f"Auto-selected Claude container: {self.claude_container_name}")
            else:
                # Look for running containers first
                running_containers = [c for c in containers if "running" in c["status"].lower()]
                if running_containers:
                    self.current_container = running_containers[0]["name"]
                    file_log.info(f"Auto-selected running container: {self.current_container}")
                elif containers:
                    self.current_container = containers[0]["name"]
                    file_log.info(f"Auto-selected first available container: {self.current_container}")

            self.is_initialized = True

        log.info("MCP initialized with backend connection and Docker capabilities")

    async def cleanup(self):
        """Cleanup resources"""
        if self.http_client:
            await self.http_client.aclose()

    # ========== Backend Integration Methods ==========

    async def get_assessment_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get assessment data by name"""
        try:
            # First get the list to find the ID
            response = await self.http_client.get(f"{self.backend_url}/assessments")
            response.raise_for_status()
            assessments = response.json()

            # Find assessment by name (case-insensitive and trim whitespace)
            assessment_id = None
            for assessment in assessments:
                if assessment["name"].strip().lower() == name.strip().lower():
                    assessment_id = assessment["id"]
                    break

            if not assessment_id:
                return None

            # Get full assessment data
            detail_response = await self.http_client.get(f"{self.backend_url}/assessments/{assessment_id}")
            detail_response.raise_for_status()
            return detail_response.json()

        except Exception as e:
            log.error(f"Error fetching assessment: {e}")
            return None

    async def get_assessment_full_data(self, assessment_id: int) -> Dict[str, Any]:
        """Get complete assessment data with all related info"""
        try:
            response = await self.http_client.get(
                f"{self.backend_url}/assessments/{assessment_id}/full"
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            log.error(f"Error fetching full assessment data: {e}")
            raise

    async def add_recon_data(
        self,
        assessment_id: int,
        data_type: str,
        name: str,
        details: Optional[Dict[str, Any]],
        discovered_in_phase: Optional[str]
    ) -> Dict[str, Any]:
        """Add recon data (endpoint, technology, service, subdomain)"""
        try:
            response = await self.http_client.post(
                f"{self.backend_url}/assessments/{assessment_id}/recon",
                json={
                    "data_type": data_type,
                    "name": name,
                    "details": details,
                    "discovered_in_phase": discovered_in_phase
                }
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            log.error(f"Error adding recon data: {e}")
            raise

    async def add_card(
        self,
        assessment_id: int,
        card_type: str,
        title: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Add a card (finding, observation, info) - section_number removed"""
        try:
            card_data = {
                "card_type": card_type,
                "title": title,
                **kwargs
            }

            response = await self.http_client.post(
                f"{self.backend_url}/assessments/{assessment_id}/cards",
                json=card_data
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            log.error(f"Error adding card: {e}")
            raise

    async def update_section(
        self,
        assessment_id: int,
        section_type: str,
        section_number: float,
        title: Optional[str],
        content: str
    ) -> Dict[str, Any]:
        """Update or create a section (phase)"""
        try:
            response = await self.http_client.post(
                f"{self.backend_url}/assessments/{assessment_id}/sections",
                json={
                    "section_type": section_type,
                    "section_number": section_number,
                    "title": title,
                    "content": content
                }
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            log.error(f"Error updating section: {e}")
            raise

    async def execute_command_backend(
        self,
        assessment_id: int,
        command: str,
        phase: Optional[str]
    ) -> Dict[str, Any]:
        """Execute command and auto-log to database via backend API"""
        try:
            response = await self.http_client.post(
                f"{self.backend_url}/assessments/{assessment_id}/commands/execute",
                json={
                    "command": command,
                    "phase": phase
                }
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            log.error(f"Error executing command: {e}")
            raise

    # ========== Docker/Container Methods ==========

    async def _run_command(self, command: List[str], timeout: float = 30.0) -> Dict[str, Any]:
        """Run a system command with timeout to prevent hangs on docker socket issues.

        Timeout is generous (30s) because this is also used for docker exec of
        pentesting tools via execute_container_command. Short docker management
        commands (inspect, ps) will complete well under that.
        """
        try:
            file_log.debug(f"Executing command: {' '.join(command)}")

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
                "command": ' '.join(command),
                "error_type": self._classify_error(process.returncode, stderr.decode('utf-8', errors='replace'))
            }

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.communicate()
            except Exception:
                pass
            file_log.warning(f"Command timed out after {timeout}s: {' '.join(command)}")
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "command": ' '.join(command),
                "error_type": "timeout",
                "raw_error": f"Timed out after {timeout}s"
            }

        except FileNotFoundError as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command not found: {command[0]}",
                "command": ' '.join(command),
                "error_type": "command_not_found",
                "raw_error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Execution failed: {str(e)}",
                "command": ' '.join(command),
                "error_type": "execution_failed",
                "raw_error": str(e)
            }

    def _classify_error(self, returncode: int, stderr: str) -> str:
        """Classify the type of error based on return code and stderr"""
        if returncode == 127:
            return "command_not_found"
        elif returncode == 126:
            return "permission_denied"
        elif returncode == 2:
            return "invalid_arguments"
        elif "not found" in stderr.lower():
            return "command_not_found"
        elif "permission denied" in stderr.lower():
            return "permission_denied"
        elif "invalid" in stderr.lower() or "usage:" in stderr.lower():
            return "invalid_command"
        elif returncode != 0:
            return "command_failed"
        else:
            return "success"

    async def check_tool_availability(self, tool_name: str) -> bool:
        """Check if a tool is available in the container"""
        if not self.current_container:
            return False

        # Use cache if available
        cache_key = f"{self.current_container}:{tool_name}"
        if cache_key in self.tool_cache:
            return self.tool_cache[cache_key]

        try:
            result = await self._run_command([
                "docker", "exec", self.current_container, "bash", "-c",
                f"source /root/.bashrc 2>/dev/null && which {tool_name}"
            ])

            available = result["success"]
            self.tool_cache[cache_key] = available
            return available

        except Exception:
            self.tool_cache[cache_key] = False
            return False

    async def validate_container_status(self) -> Dict[str, Any]:
        """Validate and potentially start the current container"""
        if not self.current_container:
            return {"success": False, "error": "No container selected"}

        try:
            # Check container status
            result = await self._run_command([
                "docker", "inspect", self.current_container, "--format", "{{.State.Status}}"
            ])

            if not result["success"]:
                return {"success": False, "error": "Container not found", "details": result["stderr"]}

            status = result["stdout"].strip()

            if status == "running":
                return {"success": True, "status": "running"}
            elif status in ["created", "exited"]:
                # Try to start the container
                file_log.info(f"Starting container {self.current_container}...")
                start_result = await self._run_command([
                    "docker", "start", self.current_container
                ])

                if start_result["success"]:
                    return {"success": True, "status": "started"}
                else:
                    return {
                        "success": False,
                        "error": f"Failed to start container",
                        "details": start_result["stderr"]
                    }
            else:
                return {"success": False, "error": f"Container in invalid state: {status}"}

        except Exception as e:
            return {"success": False, "error": f"Container validation failed: {str(e)}"}

    async def get_output_max_length(self) -> int:
        """Get output_max_length setting from backend (with cache)"""
        current_time = time.time()

        # Return cached value if still valid
        if (current_time - self.output_max_length_cache_time) < self.output_max_length_cache_ttl:
            return self.output_max_length

        # Fetch from backend
        try:
            response = await self.http_client.get(f"{self.backend_url}/system/settings/output_max_length")
            if response.status_code == 200:
                data = response.json()
                self.output_max_length = int(data["value"])
                self.output_max_length_cache_time = current_time
                file_log.debug(f"Loaded output_max_length setting: {self.output_max_length}")
            else:
                file_log.warning(f"Failed to load output_max_length setting, using default: {self.output_max_length}")
        except Exception as e:
            file_log.warning(f"Error fetching output_max_length setting: {e}, using default: {self.output_max_length}")

        return self.output_max_length

    async def get_python_exec_output_max_length(self) -> int:
        """Get python_exec_output_max_length setting from backend (with cache)"""
        current_time = time.time()

        if (current_time - self.python_exec_output_max_length_cache_time) < self.python_exec_output_max_length_cache_ttl:
            return self.python_exec_output_max_length

        try:
            response = await self.http_client.get(f"{self.backend_url}/system/settings/python_exec_output_max_length")
            if response.status_code == 200:
                data = response.json()
                self.python_exec_output_max_length = int(data["value"])
                self.python_exec_output_max_length_cache_time = current_time
            else:
                file_log.warning(f"Failed to load python_exec_output_max_length setting, using default: {self.python_exec_output_max_length}")
        except Exception as e:
            file_log.warning(f"Error fetching python_exec_output_max_length setting: {e}, using default: {self.python_exec_output_max_length}")

        return self.python_exec_output_max_length

    async def get_http_request_output_max_length(self) -> int:
        """Get http_request_output_max_length setting from backend (with cache)"""
        current_time = time.time()

        if (current_time - self.http_request_output_max_length_cache_time) < self.http_request_output_max_length_cache_ttl:
            return self.http_request_output_max_length

        try:
            response = await self.http_client.get(f"{self.backend_url}/system/settings/http_request_output_max_length")
            if response.status_code == 200:
                data = response.json()
                self.http_request_output_max_length = int(data["value"])
                self.http_request_output_max_length_cache_time = current_time
            else:
                file_log.warning(f"Failed to load http_request_output_max_length setting, using default: {self.http_request_output_max_length}")
        except Exception as e:
            file_log.warning(f"Error fetching http_request_output_max_length setting: {e}, using default: {self.http_request_output_max_length}")

        return self.http_request_output_max_length

    async def get_command_history_limit(self) -> int:
        """Get command_history_limit setting from backend (with cache)"""
        current_time = time.time()

        # Return cached value if still valid
        if (current_time - self.command_history_limit_cache_time) < self.command_history_limit_cache_ttl:
            return self.command_history_limit

        # Fetch from backend
        try:
            response = await self.http_client.get(f"{self.backend_url}/system/settings/command_history_limit")
            if response.status_code == 200:
                data = response.json()
                self.command_history_limit = int(data["value"])
                self.command_history_limit_cache_time = current_time
                file_log.debug(f"Loaded command_history_limit setting: {self.command_history_limit}")
            else:
                file_log.warning(f"Failed to load command_history_limit setting, using default: {self.command_history_limit}")
        except Exception as e:
            file_log.warning(f"Error fetching command_history_limit setting: {e}, using default: {self.command_history_limit}")

        return self.command_history_limit

    def format_output(self, output: str, max_length: Optional[int] = None) -> str:
        """Format and truncate output for display

        Args:
            output: The output string to format
            max_length: Optional max length override. If None, uses self.output_max_length
        """
        if not output:
            return output

        # Use provided max_length or fall back to instance variable
        if max_length is None:
            max_length = self.output_max_length

        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_output = ansi_escape.sub('', output)

        # Truncate if too long (skip if max_length is -1 for unlimited)
        if max_length != -1 and len(clean_output) > max_length:
            return clean_output[:max_length] + f"\n\n...(output truncated - showing {max_length}/{len(clean_output)} chars)"

        return clean_output

    async def discover_containers(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Discover Exegol containers with intelligent caching"""
        current_time = time.time()

        if (not force_refresh and
                self.containers_cache and
                (current_time - self.cache_timestamp) < self.cache_ttl):
            file_log.debug("Using cached container list")
            return self.containers_cache

        file_log.info("Discovering Exegol containers...")
        containers = []

        try:
            # Try Docker approach first
            result = await self._run_command([
                "docker", "ps", "-a",
                "--format", "json"
            ])

            if result["success"] and result["stdout"]:
                for line in result["stdout"].split('\n'):
                    if line.strip():
                        try:
                            container_data = json.loads(line)
                            image = container_data.get("Image", "")

                            if ("exegol" in image.lower() or
                                    "nwodtuhs/exegol" in image.lower()):
                                containers.append({
                                    "name": container_data.get("Names", "unknown").lstrip('/'),
                                    "image": image,
                                    "status": container_data.get("State", "unknown"),
                                    "id": container_data.get("ID", "unknown")[:12],
                                    "created": container_data.get("CreatedAt", "unknown"),
                                    "ports": [],
                                    "source": "docker"
                                })
                        except (json.JSONDecodeError, KeyError, AttributeError) as e:
                            file_log.debug(f"Error parsing container data: {e}")
                            continue

        except Exception as e:
            log.error(f"Docker discovery failed: {e}")
            containers = []

        self.containers_cache = containers
        self.cache_timestamp = current_time
        file_log.info(f"Discovered {len(containers)} containers")
        return containers

    async def execute_container_command(self, container_name: str, command: str) -> Dict[str, Any]:
        """Execute a command in a pentesting container with improved error handling"""
        file_log.info(f"Executing in {container_name}: {command[:50]}...")

        # Validate container first
        validation = await self.validate_container_status()
        if not validation["success"]:
            return {
                "success": False,
                "container": container_name,
                "command": command,
                "error": f"Container validation failed: {validation['error']}",
                "details": validation.get("details", ""),
                "execution_time": 0
            }

        start_time = time.time()

        try:
            # Properly source the environment before executing commands
            wrapped_command = f"source /root/.bashrc 2>/dev/null && {command}"

            result = await self._run_command([
                "docker", "exec", container_name, "bash", "-c", wrapped_command
            ])

            execution_time = time.time() - start_time

            # Add to history
            if len(self.command_history) >= self.max_history:
                self.command_history = self.command_history[-25:]

            self.command_history.append({
                "timestamp": start_time,
                "container": container_name,
                "command": command[:100] + "..." if len(command) > 100 else command,
                "success": result["success"],
                "execution_time": execution_time
            })

            # Refresh output_max_length setting from backend
            await self.get_output_max_length()

            # Format outputs - preserve raw error messages
            formatted_stdout = self.format_output(result["stdout"]) if result["stdout"] else ""
            formatted_stderr = result["stderr"] if result["stderr"] else ""

            return {
                "success": result["success"],
                "container": container_name,
                "command": command,
                "stdout": formatted_stdout,
                "stderr": formatted_stderr,
                "returncode": result["returncode"],
                "execution_time": execution_time,
                "error_type": result.get("error_type", "success"),
                "raw_error": result.get("raw_error", ""),
                "method": "docker"
            }

        except Exception as e:
            execution_time = time.time() - start_time

            self.command_history.append({
                "timestamp": start_time,
                "container": container_name,
                "command": command[:100] + "..." if len(command) > 100 else command,
                "success": False,
                "execution_time": execution_time,
                "error": str(e)
            })

            return {
                "success": False,
                "container": container_name,
                "command": command,
                "error": str(e),
                "execution_time": execution_time,
                "error_type": "execution_failed"
            }

    async def subdomain_enumeration(self, domain: str) -> Dict[str, Any]:
        """Perform subdomain enumeration using available tools"""
        if not self.current_container:
            return {"success": False, "error": "No container selected"}

        commands = []
        results = []

        # Check for subfinder
        if await self.check_tool_availability("subfinder"):
            commands.append(f"subfinder -d {domain} -silent")

        # Check for amass
        if await self.check_tool_availability("amass"):
            commands.append(f"amass enum -passive -d {domain}")

        # Fallback to basic DNS techniques
        if not commands:
            commands.append(f"dig +short {domain} ANY")
            commands.append(f"dig +short www.{domain}")
            commands.append(f"dig +short mail.{domain}")
            commands.append(f"dig +short ftp.{domain}")

        for cmd in commands:
            result = await self.execute_container_command(self.current_container, cmd)
            results.append({
                "command": cmd,
                "success": result["success"],
                "output": result.get("stdout", ""),
                "error": result.get("stderr", ""),
                "error_type": result.get("error_type", "")
            })

        return {"success": True, "results": results}

    async def ssl_analysis(self, target: str) -> Dict[str, Any]:
        """Perform SSL certificate analysis"""
        if not self.current_container:
            return {"success": False, "error": "No container selected"}

        # Parse target to get host and port
        if ":" in target:
            host, port = target.split(":", 1)
        else:
            host, port = target, "443"

        commands = [
            f"openssl s_client -connect {host}:{port} -servername {host} </dev/null 2>/dev/null | openssl x509 -noout -text",
            f"openssl s_client -connect {host}:{port} -servername {host} </dev/null 2>/dev/null | openssl x509 -noout -dates",
            f"openssl s_client -connect {host}:{port} -servername {host} </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer"
        ]

        results = []
        for cmd in commands:
            result = await self.execute_container_command(self.current_container, cmd)
            results.append({
                "command": cmd.split(" | ")[-1],
                "success": result["success"],
                "output": result.get("stdout", ""),
                "error": result.get("stderr", ""),
                "error_type": result.get("error_type", "")
            })

        return {"success": True, "results": results}

    async def tech_stack_detection(self, url: str) -> Dict[str, Any]:
        """Detect technology stack of a website"""
        if not self.current_container:
            return {"success": False, "error": "No container selected"}

        # Ensure URL has protocol
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        commands = [
            f"curl -I {url} 2>/dev/null | head -20",
            f"curl -s {url} 2>/dev/null | grep -i 'generator\\|powered\\|built\\|framework' | head -10",
            f"whatweb {url}" if await self.check_tool_availability("whatweb") else f"curl -s {url} 2>/dev/null | head -50"
        ]

        results = []
        for cmd in commands:
            if cmd:
                result = await self.execute_container_command(self.current_container, cmd)
                results.append({
                    "command": cmd.split(" | ")[0],
                    "success": result["success"],
                    "output": result.get("stdout", ""),
                    "error": result.get("stderr", ""),
                    "error_type": result.get("error_type", "")
                })

        return {"success": True, "results": results}
