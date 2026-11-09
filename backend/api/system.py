"""
System status and information endpoints
"""
import sys
import time
import subprocess
import platform
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
import fastapi

from database import get_db
from config import settings
from schemas.system import SystemStatusResponse, SystemInfoResponse, BackendStatus, DatabaseStatus, ExegolStatus, PlatformSettingResponse, UpdateSettingRequest
from services.container_service import ContainerService
from models.platform_settings import PlatformSettings

router = APIRouter(prefix="/system", tags=["system"])

container_service = ContainerService()




@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(db: Session = Depends(get_db)):
    """
    Get real-time system status for backend, database, and Exegol
    """
    start_time = time.time()

    # Backend status
    backend_latency = int((time.time() - start_time) * 1000)
    backend_status = BackendStatus(
        status="connected",
        latency=backend_latency,
        version=settings.VERSION
    )

    # Database status
    try:
        # Try to query database
        db.execute(text("SELECT 1"))

        # Get PostgreSQL version
        result = db.execute(text("SELECT version()"))
        version_full = result.scalar()
        # Extract version number (e.g., "PostgreSQL 16.1")
        version = version_full.split()[1] if version_full else "Unknown"

        database_status = DatabaseStatus(
            status="connected",
            connected=True,
            version=version
        )
    except Exception:
        database_status = DatabaseStatus(
            status="error",
            connected=False,
            version=""
        )

    # Exegol status
    try:
        containers = await container_service.discover_containers(force_refresh=True)

        if containers:
            # Check if default container is running
            default_container = next(
                (c for c in containers if c["name"] == settings.DEFAULT_CONTAINER_NAME),
                None
            )

            if default_container:
                exegol_status = ExegolStatus(
                    status="connected",
                    running=default_container["status"] == "running",
                    container=default_container["name"]
                )
            else:
                # Use first Exegol container found
                first_container = containers[0]
                exegol_status = ExegolStatus(
                    status="connected",
                    running=first_container["status"] == "running",
                    container=first_container["name"]
                )
        else:
            exegol_status = ExegolStatus(
                status="not_found",
                running=False,
                container=""
            )
    except Exception:
        exegol_status = ExegolStatus(
            status="error",
            running=False,
            container=""
        )

    return SystemStatusResponse(
        backend=backend_status,
        database=database_status,
        exegol=exegol_status
    )


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info():
    """
    Get system configuration and version information
    """
    # Get FastAPI version
    fastapi_version = fastapi.__version__

    # Get Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    return SystemInfoResponse(
        platform_name=settings.PROJECT_NAME,
        tagline=settings.PROJECT_TAGLINE,
        version=settings.VERSION,
        fastapi_version=fastapi_version,
        python_version=python_version,
        workspace_base=settings.CONTAINER_WORKSPACE_BASE,
        container_name=settings.DEFAULT_CONTAINER_NAME,
        environment=settings.ENVIRONMENT
    )


@router.get("/settings/{key}", response_model=PlatformSettingResponse)
async def get_platform_setting(key: str, db: Session = Depends(get_db)):
    """
    Get a specific platform setting by key
    """
    setting = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()

    if not setting:
        # Return default values for known keys
        if key == "command_timeout":
            return PlatformSettingResponse(
                key=key,
                value=str(settings.COMMAND_TIMEOUT),
                description="Maximum execution time for commands in seconds"
            )
        if key == "output_max_length":
            return PlatformSettingResponse(
                key=key,
                value="5000",
                description="Maximum length of command output before truncation (-1 for unlimited)"
            )
        if key == "python_exec_output_max_length":
            return PlatformSettingResponse(
                key=key,
                value="5000",
                description="Maximum length of python_exec output before truncation (-1 for unlimited)"
            )
        if key == "http_request_output_max_length":
            return PlatformSettingResponse(
                key=key,
                value="5000",
                description="Maximum length of http_request output before truncation (-1 for unlimited)"
            )
        if key == "command_history_limit":
            return PlatformSettingResponse(
                key=key,
                value="10",
                description="Number of recent commands to include in load_assessment (range: 5-100)"
            )
        if key == "max_context_file_size":
            return PlatformSettingResponse(
                key=key,
                value=str(settings.MAX_CONTEXT_FILE_SIZE // (1024 * 1024)),
                description="Maximum size (MB) for a single file uploaded to /context"
            )
        if key == "max_source_zip_size":
            return PlatformSettingResponse(
                key=key,
                value=str(settings.MAX_SOURCE_ZIP_SIZE // (1024 * 1024)),
                description="Maximum size (MB) for a source-code ZIP uploaded to /source"
            )
        if key == "theme":
            return PlatformSettingResponse(
                key=key, value="light", description="UI theme: light / dark"
            )
        if key == "primary_color":
            return PlatformSettingResponse(
                key=key, value="cyan", description="UI accent color preset"
            )
        if key == "telegram_bot_enabled":
            return PlatformSettingResponse(
                key=key, value="false", description="Enable the inbound Telegram bot (default: off)"
            )
        if key == "mcp_http_enabled":
            return PlatformSettingResponse(
                key=key,
                value="false",
                description="Expose the MCP server over HTTP at /mcp (default: off)"
            )
        if key == "mcp_http_network_policy":
            return PlatformSettingResponse(
                key=key,
                value="localhost",
                description="Allowed clients for /mcp: localhost / lan / any"
            )
        raise fastapi.HTTPException(status_code=404, detail=f"Setting '{key}' not found")

    return PlatformSettingResponse(
        key=setting.key,
        value=setting.value,
        description=setting.description
    )


@router.put("/settings/{key}", response_model=PlatformSettingResponse)
async def update_platform_setting(
    key: str,
    request: UpdateSettingRequest,
    db: Session = Depends(get_db)
):
    """
    Update a platform setting
    """
    # Validate timeout value if updating command_timeout
    if key == "command_timeout":
        try:
            timeout_value = int(request.value)
            if timeout_value < 30 or timeout_value > 1800:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail="Command timeout must be between 30 and 1800 seconds (30s to 30min)"
                )
        except ValueError:
            raise fastapi.HTTPException(status_code=400, detail="Timeout value must be a valid integer")

    # Validate output_max_length variants
    if key in ("output_max_length", "python_exec_output_max_length", "http_request_output_max_length"):
        try:
            max_length = int(request.value)
            if max_length != -1 and (max_length < 500 or max_length > 100000):
                raise fastapi.HTTPException(
                    status_code=400,
                    detail="Output max length must be between 500 and 100000 characters, or -1 for unlimited"
                )
        except ValueError:
            raise fastapi.HTTPException(status_code=400, detail="Output max length must be a valid integer")

    # Validate command_history_limit if updating command_history_limit
    if key == "command_history_limit":
        try:
            limit_value = int(request.value)
            if limit_value < 0 or limit_value > 100:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail="Command history limit must be between 0 and 100"
                )
        except ValueError:
            raise fastapi.HTTPException(
                status_code=400,
                detail="Command history limit must be a valid integer"
            )

    # Validate MCP HTTP settings
    if key == "mcp_http_enabled":
        if request.value.lower() not in ("true", "false"):
            raise fastapi.HTTPException(
                status_code=400,
                detail="mcp_http_enabled must be 'true' or 'false'"
            )
        request.value = request.value.lower()
    if key == "mcp_http_network_policy":
        if request.value not in ("localhost", "lan", "any"):
            raise fastapi.HTTPException(
                status_code=400,
                detail="mcp_http_network_policy must be 'localhost', 'lan', or 'any'"
            )

    # Validate file size limits (stored in MB, 1–2000)
    if key in ("max_context_file_size", "max_source_zip_size"):
        try:
            mb_value = int(request.value)
            if mb_value < 1 or mb_value > 2000:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail=f"{key} must be between 1 and 2000 MB"
                )
        except ValueError:
            raise fastapi.HTTPException(status_code=400, detail=f"{key} must be a valid integer (MB)")

    # Validate container_name if updating container_name
    if key == "container_name":
        container_name = request.value.strip()
        if not container_name:
            raise fastapi.HTTPException(status_code=400, detail="Container name cannot be empty")

        # Verify container exists
        containers = await container_service.discover_containers(force_refresh=True)
        if not any(c["name"] == container_name for c in containers):
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found in available Exegol containers"
            )

        # Update the service's current container
        await container_service.select_container(container_name)

        # Also update the settings default
        settings.DEFAULT_CONTAINER_NAME = container_name

    # Check if setting exists
    setting = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()

    if setting:
        # Update existing setting
        setting.value = request.value
    else:
        # Create new setting
        setting = PlatformSettings(
            key=key,
            value=request.value,
            description=f"Setting for {key}"
        )
        db.add(setting)

    db.commit()
    db.refresh(setting)

    return PlatformSettingResponse(
        key=setting.key,
        value=setting.value,
        description=setting.description
    )


@router.get("/exegol/containers")
async def list_exegol_containers():
    """
    List all available Exegol containers
    """
    try:
        containers = await container_service.discover_containers(force_refresh=True)

        return {
            "containers": containers,
            "count": len(containers),
            "current": container_service.current_container
        }
    except Exception as e:
        raise fastapi.HTTPException(
            status_code=500,
            detail=f"Failed to list Exegol containers: {str(e)}"
        )


@router.get("/tool-usage-stats")
async def get_tool_usage_stats(
    assessment_id: int = None,
    since_days: int = None,
    include_failed: bool = True,
    top_n: int = 20,
    db: Session = Depends(get_db)
):
    """
    Analyze tool usage from execute() commands
    
    Dynamically extracts tool names from CommandHistory and provides:
    - Top N most used tools
    - Tool usage by category (recon, web, exploitation, etc.)
    - Breakdown by assessment
    - Success rates per tool
    
    Query Parameters:
    - assessment_id: Filter by specific assessment (optional)
    - since_days: Analyze commands from last N days (optional, default: all time)
    - include_failed: Include failed commands in stats (default: true)
    - top_n: Number of top tools to return (default: 20, max: 100)
    """
    from datetime import datetime, timedelta
    from models import CommandHistory, Assessment
    from schemas.tool_stats import (
        ToolUsageStatsResponse, ToolUsage, ToolCategoryStats, AssessmentToolUsage
    )
    from utils.tool_analyzer import (
        extract_tool_name, categorize_tool, get_tool_counts_by_category
    )
    
    # Validate top_n
    if top_n > 100:
        top_n = 100
    if top_n < 1:
        top_n = 1
    
    # Build base query
    query = db.query(CommandHistory)
    
    # Filter by assessment if specified
    if assessment_id:
        query = query.filter(CommandHistory.assessment_id == assessment_id)
    
    # Filter by date if specified
    date_range_str = None
    if since_days:
        cutoff_date = datetime.now() - timedelta(days=since_days)
        query = query.filter(CommandHistory.created_at >= cutoff_date)
        date_range_str = f"Last {since_days} days (since {cutoff_date.strftime('%Y-%m-%d')})"
    
    # Filter by success if needed
    if not include_failed:
        query = query.filter(CommandHistory.success == True)
    
    # Get all commands
    commands = query.all()
    
    if not commands:
        # Return empty stats
        return ToolUsageStatsResponse(
            total_commands=0,
            total_assessments=0,
            date_range=date_range_str,
            most_used_tools=[],
            tool_categories={},
            by_assessment=[],
            unknown_tools=[]
        )
    
    # Extract tool names and count usage
    tool_counts = {}
    tool_success_counts = {}  # Track successes per tool
    tool_total_counts = {}    # Track total attempts per tool
    
    for cmd in commands:
        tool = extract_tool_name(cmd.command)
        
        # Count total usage
        if tool not in tool_counts:
            tool_counts[tool] = 0
            tool_success_counts[tool] = 0
            tool_total_counts[tool] = 0
        
        tool_counts[tool] += 1
        tool_total_counts[tool] += 1
        
        # Count successes
        if cmd.success:
            tool_success_counts[tool] += 1
    
    # Calculate total commands
    total_commands = len(commands)
    
    # Get unique assessment count
    unique_assessment_ids = set(cmd.assessment_id for cmd in commands)
    total_assessments = len(unique_assessment_ids)
    
    # Sort tools by usage
    sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Build most_used_tools list with success rates
    most_used_tools = []
    unknown_tools = []
    
    for tool, count in sorted_tools[:top_n]:
        # Calculate success rate
        success_rate = 0.0
        if tool_total_counts[tool] > 0:
            success_rate = (tool_success_counts[tool] / tool_total_counts[tool]) * 100
        
        percentage = (count / total_commands) * 100
        
        most_used_tools.append(
            ToolUsage(
                tool=tool,
                count=count,
                percentage=round(percentage, 2),
                success_rate=round(success_rate, 2)
            )
        )
        
        # Track unknown tools
        if categorize_tool(tool) == "other" and tool != "unknown":
            unknown_tools.append(tool)
    
    # Group by categories
    category_data = get_tool_counts_by_category(tool_counts)
    
    tool_categories = {}
    for category, data in category_data.items():
        if data["count"] > 0:  # Only include categories with usage
            percentage = (data["count"] / total_commands) * 100
            tool_categories[category] = ToolCategoryStats(
                count=data["count"],
                percentage=round(percentage, 2),
                tools=data["tools"]
            )
    
    # Break down by assessment
    by_assessment = []
    
    # Group commands by assessment
    assessment_commands = {}
    for cmd in commands:
        if cmd.assessment_id not in assessment_commands:
            assessment_commands[cmd.assessment_id] = []
        assessment_commands[cmd.assessment_id].append(cmd)
    
    # Get assessment names
    assessment_map = {}
    for assess_id in assessment_commands.keys():
        assessment = db.query(Assessment).filter(Assessment.id == assess_id).first()
        if assessment:
            assessment_map[assess_id] = assessment.name
    
    # Calculate top tools per assessment
    for assess_id, assess_commands in assessment_commands.items():
        assess_tool_counts = {}
        
        for cmd in assess_commands:
            tool = extract_tool_name(cmd.command)
            if tool not in assess_tool_counts:
                assess_tool_counts[tool] = 0
            assess_tool_counts[tool] += 1
        
        # Sort and get top 5 tools for this assessment
        sorted_assess_tools = sorted(
            assess_tool_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:5]
        
        from schemas.tool_stats import ToolCount
        
        top_tools = [
            ToolCount(tool=tool, count=count)
            for tool, count in sorted_assess_tools
        ]
        
        by_assessment.append(
            AssessmentToolUsage(
                assessment_id=assess_id,
                assessment_name=assessment_map.get(assess_id, f"Assessment {assess_id}"),
                total_commands=len(assess_commands),
                top_tools=top_tools
            )
        )
    
    # Sort by_assessment by total_commands descending
    by_assessment.sort(key=lambda x: x.total_commands, reverse=True)
    
    return ToolUsageStatsResponse(
        total_commands=total_commands,
        total_assessments=total_assessments,
        date_range=date_range_str,
        most_used_tools=most_used_tools,
        tool_categories=tool_categories,
        by_assessment=by_assessment,
        unknown_tools=unknown_tools
    )


class OpenFolderRequest(BaseModel):
    """Request body for opening a folder"""
    path: str


@router.post("/open-folder")
async def open_folder(request: OpenFolderRequest):
    """
    Open a folder in the native file manager (Finder on macOS)
    
    This is used by the frontend to open the Exegol workspaces folder
    """
    import os

    folder_path = request.path

    # Security: Only allow opening paths under known safe directories
    home_dir = os.path.expanduser("~")
    allowed_prefixes = [
        f"{home_dir}/.exegol/workspaces",
        "/workspace",
        settings.CONTAINER_WORKSPACE_BASE
    ]
    
    is_allowed = any(folder_path.startswith(prefix) for prefix in allowed_prefixes)
    
    if not is_allowed:
        raise fastapi.HTTPException(
            status_code=403,
            detail="Access denied: Cannot open paths outside of allowed directories"
        )
    
    # Check if path exists (on host or just return success for container paths)
    if folder_path.startswith("/workspace"):
        # Container path - just return info, user will access via mounted volume
        return {
            "success": True,
            "message": f"Container path: {folder_path}",
            "note": "This path is inside the Exegol container"
        }
    
    if not os.path.exists(folder_path):
        raise fastapi.HTTPException(
            status_code=404,
            detail=f"Path does not exist: {folder_path}"
        )
    
    try:
        # Open folder based on OS
        current_os = platform.system()
        
        if current_os == "Darwin":  # macOS
            subprocess.Popen(["open", folder_path])
        elif current_os == "Windows":
            subprocess.Popen(["explorer", folder_path])
        else:  # Linux
            subprocess.Popen(["xdg-open", folder_path])
        
        return {
            "success": True,
            "message": f"Opened folder: {folder_path}",
            "path": folder_path
        }
    except Exception as e:
        raise fastapi.HTTPException(
            status_code=500,
            detail=f"Failed to open folder: {str(e)}"
        )

