"""
Workspace Service - Host filesystem path resolution and folder opening
"""
import asyncio
import json
import os
import platform
from typing import Dict, Any, Optional

from models import Assessment
from utils.logger import get_logger

logger = get_logger(__name__)


class WorkspaceService:
    """Service for managing workspace folder access on host filesystem"""

    def __init__(self):
        self.os_name = platform.system()

    async def _run_command(self, command: list[str], timeout: float = 10.0) -> Dict[str, Any]:
        """
        Execute a system command asynchronously

        Args:
            command: Command and arguments as list
            timeout: Max seconds to wait for the command (default 10s).
                     Prevents hangs when docker socket is slow or unresponsive.

        Returns:
            Dict with stdout, stderr, and returncode
        """
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
                "stdout": stdout.decode('utf-8').strip() if stdout else "",
                "stderr": stderr.decode('utf-8').strip() if stderr else "",
                "returncode": process.returncode
            }
        except asyncio.TimeoutError:
            # Kill the hanging process so it doesn't linger
            try:
                process.kill()
                await process.communicate()
            except Exception:
                pass
            logger.warning("Command timed out", command=" ".join(command), timeout=timeout)
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "returncode": -1
            }
        except Exception as e:
            logger.error("Failed to run command", command=" ".join(command), error=str(e))
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }

    async def get_container_workspace_mount(self, container_name: str) -> Optional[Dict[str, str]]:
        """
        Get workspace mount information from Docker container

        Executes: docker inspect {container_name} --format '{{json .Mounts}}'
        Finds the mount with Destination="/workspace" and Type="bind"

        Args:
            container_name: Name of the Exegol container (e.g., "exegol-claude")

        Returns:
            Dict with host_path and container_path, or None if not found
            Example: {"host_path": "~/.exegol/workspaces/exegol-aida", "container_path": "/workspace"}
        """
        logger.info("Getting workspace mount for container", container_name=container_name)

        result = await self._run_command([
            "docker", "inspect", container_name,
            "--format", "{{json .Mounts}}"
        ])

        if result["returncode"] != 0:
            logger.error(
                "Failed to inspect container",
                container_name=container_name,
                error=result["stderr"]
            )
            return None

        try:
            mounts = json.loads(result["stdout"])

            # Find the workspace mount
            workspace_mount = next(
                (m for m in mounts
                 if m.get("Destination") == "/workspace" and m.get("Type") == "bind"),
                None
            )

            if not workspace_mount:
                logger.warning(
                    "No workspace mount found in container",
                    container_name=container_name
                )
                return None

            host_path = workspace_mount.get("Source")
            container_path = workspace_mount.get("Destination")

            logger.info(
                "Found workspace mount",
                container_name=container_name,
                host_path=host_path,
                container_path=container_path
            )

            return {
                "host_path": host_path,
                "container_path": container_path
            }

        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                "Failed to parse container mounts",
                container_name=container_name,
                error=str(e)
            )
            return None

    async def get_host_workspace_path(
        self,
        container_path: str,
        container_name: str
    ) -> Optional[str]:
        """
        Resolve container workspace path to host filesystem path

        Example:
            container_path="/workspace/assessment-1", container_name="exegol-aida"
            → "~/.exegol/workspaces/exegol-aida/assessment-1"

        Args:
            container_path: Path inside container (e.g., "/workspace/assessment-1")
            container_name: Name of the Exegol container

        Returns:
            Host filesystem path, or None if resolution fails
        """
        mount_info = await self.get_container_workspace_mount(container_name)

        if not mount_info:
            return None

        host_base_path = mount_info["host_path"]
        container_base_path = mount_info["container_path"]

        # Replace container base path with host base path
        if container_path.startswith(container_base_path):
            relative_path = container_path[len(container_base_path):].lstrip("/")
            host_path = os.path.join(host_base_path, relative_path) if relative_path else host_base_path
        else:
            logger.warning(
                "Container path does not start with workspace base",
                container_path=container_path,
                container_base_path=container_base_path
            )
            return None

        logger.info(
            "Resolved host path",
            container_path=container_path,
            host_path=host_path
        )

        return host_path

    async def validate_workspace_in_container(
        self,
        container_path: str,
        container_name: str
    ) -> bool:
        """
        Check if workspace folder exists inside the Exegol container.

        This is the preferred method when backend runs in Docker, as it
        cannot directly access host filesystem paths.

        Args:
            container_path: Path inside the container (e.g., "/workspace/assessment-1")
            container_name: Name of the Exegol container

        Returns:
            True if path exists and is a directory inside the container
        """
        result = await self._run_command([
            "docker", "exec", container_name, "test", "-d", container_path
        ])

        exists = result["returncode"] == 0

        logger.debug(
            "Validated workspace existence in container",
            container_name=container_name,
            container_path=container_path,
            exists=exists
        )

        return exists

    async def open_folder_in_explorer(self, host_path: str) -> Dict[str, Any]:
        """
        Attempt to open folder in OS file explorer/finder.

        NOTE: This method will FAIL when backend runs in Docker container
        because xdg-open/open commands cannot access host GUI.
        The frontend uses the local tools/helper.py service instead.
        This method is kept as fallback for non-Docker deployments.

        Supports:
        - macOS: open command
        - Linux: xdg-open command
        - Windows: explorer command

        Args:
            host_path: Host filesystem path to open

        Returns:
            Dict with success, os, path, and error (if any)
        """
        logger.info("Attempting to open folder in explorer", host_path=host_path, os=self.os_name)

        # Determine OS-specific command
        if self.os_name == "Darwin":  # macOS
            command = ["open", host_path]
        elif self.os_name == "Linux":
            command = ["xdg-open", host_path]
        elif self.os_name == "Windows":
            command = ["explorer", host_path]
        else:
            error_msg = f"Unsupported operating system: {self.os_name}"
            logger.error(error_msg)
            return {
                "success": False,
                "os": self.os_name,
                "path": host_path,
                "error": error_msg
            }

        # Execute command
        result = await self._run_command(command)

        success = result["returncode"] == 0

        if success:
            logger.info("Successfully opened folder", host_path=host_path)
        else:
            logger.debug(
                "Could not open folder (expected in Docker environment)",
                host_path=host_path,
                error=result["stderr"]
            )

        return {
            "success": success,
            "os": self.os_name,
            "path": host_path,
            "error": result["stderr"] if not success else None
        }

    async def detect_container_switch(
        self,
        assessment: Assessment,
        current_container: str
    ) -> Dict[str, Any]:
        """
        Detect if assessment's container differs from current container

        Args:
            assessment: Assessment ORM model
            current_container: Current active container name

        Returns:
            Dict with mismatch info:
            - mismatch: bool - True if containers differ
            - assessment_container: str - Container stored in assessment
            - current_container: str - Current active container
            - warning: str - Human-readable warning message
        """
        assessment_container = assessment.container_name

        # No container stored in assessment yet
        if not assessment_container:
            logger.debug(
                "Assessment has no container_name set",
                assessment_id=assessment.id
            )
            return {
                "mismatch": False,
                "assessment_container": None,
                "current_container": current_container,
                "warning": None
            }

        # Check for mismatch
        mismatch = assessment_container != current_container

        if mismatch:
            warning = (
                f"Workspace was created in container '{assessment_container}' "
                f"but current container is '{current_container}'"
            )
            logger.warning(
                "Container mismatch detected",
                assessment_id=assessment.id,
                assessment_container=assessment_container,
                current_container=current_container
            )
        else:
            warning = None

        return {
            "mismatch": mismatch,
            "assessment_container": assessment_container,
            "current_container": current_container,
            "warning": warning
        }


# Singleton instance
workspace_service = WorkspaceService()
