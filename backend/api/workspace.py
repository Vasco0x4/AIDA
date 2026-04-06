"""
Workspace API - Endpoints for opening workspace folders on host filesystem
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Assessment
from models.platform_settings import PlatformSettings
from services.workspace_service import workspace_service
from services.container_service import ContainerService
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.post("/open")
async def open_root_workspace(db: Session = Depends(get_db)):
    """
    Open /workspace root folder in host file explorer

    Used by Settings → Tools tab

    Returns:
        Dict with success status, paths, and OS info
    """
    logger.info("Opening root workspace")

    try:
        # Get current container from PlatformSettings
        container_setting = db.query(PlatformSettings).filter(
            PlatformSettings.key == "container_name"
        ).first()

        container_name = (
            container_setting.value
            if container_setting
            else settings.DEFAULT_CONTAINER_NAME
        )

        logger.debug("Using container", container_name=container_name)

        # Validate workspace exists inside container (not on host)
        container_path = "/workspace"
        workspace_exists = await workspace_service.validate_workspace_in_container(
            container_path=container_path,
            container_name=container_name
        )

        if not workspace_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Workspace not found in container '{container_name}'. Is the container running?"
            )

        # Get host path for opening in explorer
        host_path = await workspace_service.get_host_workspace_path(
            container_path=container_path,
            container_name=container_name
        )

        if not host_path:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resolve host path for container '{container_name}'"
            )

        # Try to open in explorer (may fail if running in Docker)
        result = await workspace_service.open_folder_in_explorer(host_path)

        # Even if open fails (Docker env), return success with path info
        # The frontend can display the path to the user
        if result["success"]:
            logger.info("Successfully opened root workspace", host_path=host_path)
        else:
            logger.info(
                "Could not open folder (likely running in Docker), returning path info",
                host_path=host_path,
                error=result.get("error")
            )

        return {
            "success": True,
            "opened": result["success"],
            "container_name": container_name,
            "container_path": container_path,
            "host_path": host_path,
            "os": result["os"],
            "message": "Folder opened" if result["success"] else f"Path: {host_path} (copy to open manually)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to open workspace", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assessments/{assessment_id}/open")
async def open_assessment_workspace(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    """
    Open assessment-specific workspace folder

    Uses the container specified in assessment.container_name
    to open the workspace. This is the source of truth.

    Args:
        assessment_id: ID of the assessment

    Returns:
        Success response with paths
    """
    logger.info("Opening assessment workspace", assessment_id=assessment_id)

    try:
        # Load assessment
        assessment = db.query(Assessment).filter(
            Assessment.id == assessment_id
        ).first()

        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found")

        if not assessment.workspace_path:
            raise HTTPException(
                status_code=400,
                detail="Assessment has no workspace. Create one first."
            )

        # Use assessment's container (not global default)
        # This is the source of truth
        container_name = assessment.container_name or settings.DEFAULT_CONTAINER_NAME

        logger.debug(
            "Using assessment container",
            assessment_id=assessment_id,
            container_name=container_name,
            workspace_path=assessment.workspace_path
        )

        # First, try to resolve host path (works even if container is stopped)
        host_path = await workspace_service.get_host_workspace_path(
            container_path=assessment.workspace_path,
            container_name=container_name
        )

        if not host_path:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resolve host path for container '{container_name}'"
            )

        # Check if the workspace exists on the host filesystem
        # This allows opening even when container is stopped (Exegol mounts are persistent)
        import os
        host_exists = os.path.exists(host_path) and os.path.isdir(host_path)

        if host_exists:
            logger.info(
                "Workspace found on host filesystem, opening directly",
                assessment_id=assessment_id,
                host_path=host_path
            )
        else:
            # Workspace not on host - try to validate/create in container
            # (requires container to be running)
            logger.info(
                "Workspace not found on host, checking container",
                assessment_id=assessment_id,
                host_path=host_path
            )
            
            workspace_exists = await workspace_service.validate_workspace_in_container(
                container_path=assessment.workspace_path,
                container_name=container_name
            )

            if not workspace_exists:
                # Workspace missing in container - auto-recreate it
                logger.warning(
                    "Workspace missing in container, attempting auto-recreation",
                    assessment_id=assessment_id,
                    container_name=container_name,
                    workspace_path=assessment.workspace_path
                )

                # Create workspace subdirectories
                subdirs = ['recon', 'exploits', 'loot', 'notes', 'scripts', 'context']
                subdir_paths = [f"{assessment.workspace_path}/{subdir}" for subdir in subdirs]
                all_paths = [assessment.workspace_path] + subdir_paths
                mkdir_command = f"mkdir -p {' '.join(all_paths)}"

                mkdir_result = await workspace_service._run_command([
                    "docker", "exec", container_name, "bash", "-c", mkdir_command
                ])

                if mkdir_result["returncode"] != 0:
                    logger.error(
                        "Failed to recreate workspace",
                        assessment_id=assessment_id,
                        error=mkdir_result["stderr"]
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to recreate workspace in container '{container_name}': {mkdir_result['stderr']}"
                    )

                logger.info(
                    "Successfully auto-recreated workspace",
                    assessment_id=assessment_id,
                    container_name=container_name,
                    workspace_path=assessment.workspace_path
                )

        # Try to open in explorer (may fail if running in Docker)
        result = await workspace_service.open_folder_in_explorer(host_path)

        # Even if open fails (Docker env), return success with path info
        if result["success"]:
            logger.info(
                "Successfully opened assessment workspace",
                assessment_id=assessment_id,
                host_path=host_path
            )
        else:
            logger.info(
                "Could not open folder (likely running in Docker), returning path info",
                assessment_id=assessment_id,
                host_path=host_path,
                error=result.get("error")
            )

        return {
            "success": True,
            "opened": result["success"],
            "assessment_id": assessment_id,
            "container_name": container_name,
            "container_path": assessment.workspace_path,
            "host_path": host_path,
            "os": result["os"],
            "message": "Folder opened" if result["success"] else f"Path: {host_path} (copy to open manually)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to open assessment workspace",
            assessment_id=assessment_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assessments/{assessment_id}/recreate")
async def recreate_assessment_workspace(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    """
    Recreate workspace in current container after container switch

    Creates a new workspace folder in the currently active container and
    updates the assessment's workspace_path and container_name.

    Args:
        assessment_id: ID of the assessment

    Returns:
        Dict with new workspace paths
    """
    logger.info("Recreating assessment workspace", assessment_id=assessment_id)

    try:
        # Load assessment
        assessment = db.query(Assessment).filter(
            Assessment.id == assessment_id
        ).first()

        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found")

        # Get current container
        container_setting = db.query(PlatformSettings).filter(
            PlatformSettings.key == "container_name"
        ).first()

        current_container = (
            container_setting.value
            if container_setting
            else settings.DEFAULT_CONTAINER_NAME
        )

        # Create new workspace using ContainerService
        container_service = ContainerService()
        container_service.current_container = current_container

        workspace_result = await container_service.create_workspace(
            assessment_name=assessment.name,
            db=db
        )

        # Update assessment
        assessment.workspace_path = workspace_result["workspace_path"]
        assessment.container_name = workspace_result["container_name"]
        db.commit()
        db.refresh(assessment)

        logger.info(
            "Successfully recreated workspace",
            assessment_id=assessment_id,
            workspace_path=workspace_result["workspace_path"],
            container_name=workspace_result["container_name"]
        )

        return {
            "success": True,
            "assessment_id": assessment_id,
            "workspace_path": workspace_result["workspace_path"],
            "container_name": workspace_result["container_name"],
            "message": f"Workspace recreated in container '{current_container}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to recreate workspace",
            assessment_id=assessment_id,
            error=str(e)
        )
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolve")
async def resolve_workspace_path(
    assessment_id: int = None,
    assessment_name: str = None,
    container: str = None,
    db: Session = Depends(get_db)
):
    """
    Resolve assessment workspace container path to host filesystem path
    
    Used by AIDA CLI launcher to determine where to launch Claude Code from.
    
    Query params:
        assessment_id: Assessment ID (optional)
        assessment_name: Assessment name (optional, case-insensitive)
        container: Container name override (optional, uses assessment's container if not provided)
    
    Returns:
        Dict with:
        - assessment_id: ID of the assessment
        - assessment_name: Name of the assessment
        - container_name: Container name used
        - container_path: Path inside container (e.g., /workspace/MyAssessment)
        - host_path: Resolved host filesystem path (e.g., ~/.exegol/workspaces/exegol-aida/MyAssessment)
        - exists: Whether the workspace exists (checked in container)
        - container_running: Whether the container is running
    """
    logger.info(
        "Resolving workspace path",
        assessment_id=assessment_id,
        assessment_name=assessment_name,
        container=container
    )
    
    try:
        # Get assessment
        if assessment_name:
            assessment = db.query(Assessment).filter(
                func.trim(Assessment.name).ilike(assessment_name.strip())
            ).first()
        elif assessment_id:
            assessment = db.query(Assessment).filter(
                Assessment.id == assessment_id
            ).first()
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either assessment_id or assessment_name"
            )
        
        if not assessment:
            raise HTTPException(
                status_code=404,
                detail=f"Assessment not found: {assessment_name or assessment_id}"
            )
        
        # Get container name (priority: param > assessment.container_name > default)
        container_name = container or assessment.container_name or settings.DEFAULT_CONTAINER_NAME
        
        # Use workspace_path from assessment if available, otherwise construct it
        if assessment.workspace_path:
            container_path = assessment.workspace_path
        else:
            # Construct default path
            container_path = f"{settings.CONTAINER_WORKSPACE_BASE}/{assessment.name}"
        
        logger.debug(
            "Using container and path",
            container_name=container_name,
            container_path=container_path
        )
        
        # Check if container is running
        container_status_result = await workspace_service._run_command([
            "docker", "inspect", container_name, "--format", "{{.State.Status}}"
        ])
        
        container_running = (
            container_status_result["returncode"] == 0 and
            container_status_result["stdout"].strip() == "running"
        )
        
        # Resolve to host path
        host_path = await workspace_service.get_host_workspace_path(
            container_path=container_path,
            container_name=container_name
        )
        
        if not host_path:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resolve host path for container '{container_name}'. "
                       f"Is the container configured correctly?"
            )
        
        # Check if workspace exists (only if container is running)
        exists = False
        if container_running:
            exists = await workspace_service.validate_workspace_in_container(
                container_path=container_path,
                container_name=container_name
            )
        else:
            # If container is not running, check if host path exists
            import os
            exists = os.path.exists(host_path) and os.path.isdir(host_path)
        
        logger.info(
            "Resolved workspace path",
            assessment_id=assessment.id,
            host_path=host_path,
            exists=exists,
            container_running=container_running
        )
        
        return {
            "success": True,
            "assessment_id": assessment.id,
            "assessment_name": assessment.name,
            "container_name": container_name,
            "container_path": container_path,
            "host_path": host_path,
            "exists": exists,
            "container_running": container_running
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to resolve workspace path", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

