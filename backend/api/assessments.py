"""
Assessment CRUD API endpoints
"""
from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from database import get_db
from models import Assessment, AssessmentSection, Card, ReconData, Folder, CommandHistory
from schemas.assessment import (
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentResponse,
    AssessmentListResponse,
    DuplicateAssessmentRequest,
)
from services.assessment_service import AssessmentService
from services.scan_importer import ScanImporter, ScanImportError
from services.container_service import ContainerService
from websocket.manager import manager
from websocket.events import event_assessment_created, event_assessment_updated, event_assessment_deleted
from utils.logger import get_logger

logger = get_logger(__name__)




def serialize_for_json(data: dict) -> dict:
    """Convert date/datetime objects to ISO strings for JSON serialization"""
    serialized = {}
    for key, value in data.items():
        if isinstance(value, (date, datetime)):
            serialized[key] = value.isoformat()
        elif isinstance(value, dict):
            serialized[key] = serialize_for_json(value)
        elif isinstance(value, list):
            serialized[key] = [
                serialize_for_json(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            serialized[key] = value
    return serialized

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get("", response_model=List[AssessmentListResponse])
async def list_assessments(
    skip: int = 0,
    limit: int = 100,
    folder_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all assessments with optional filtering

    Status values: 'active', 'completed', 'archived'
    """
    query = db.query(Assessment)

    # Apply filters
    if folder_id is not None:
        if folder_id == "null":
            query = query.filter(Assessment.folder_id.is_(None))
        else:
            try:
                folder_id_int = int(folder_id)
                query = query.filter(Assessment.folder_id == folder_id_int)
            except ValueError:
                # Invalid folder_id, ignore filter
                pass
    
    if status is not None:
        # Validate status against allowed values
        valid_statuses = {'active', 'completed', 'archived', 'draft'}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value. Allowed: {', '.join(sorted(valid_statuses))}"
            )
        query = query.filter(Assessment.status == status)

    assessments = query.offset(skip).limit(limit).all()
    return assessments


@router.get("/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    """Get a single assessment by ID"""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )
    return assessment


@router.get("/{assessment_id}/full")
async def get_assessment_full(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    """Get complete assessment data with sections, cards, and recon data"""
    # Get assessment
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )
    
    # Get sections
    sections = (
        db.query(AssessmentSection)
        .filter(AssessmentSection.assessment_id == assessment_id)
        .order_by(AssessmentSection.section_number)
        .all()
    )
    
    # Get cards
    cards = (
        db.query(Card)
        .filter(Card.assessment_id == assessment_id)
        .order_by(Card.created_at.desc())
        .all()
    )
    
    # Get recon data
    recon_data = (
        db.query(ReconData)
        .filter(ReconData.assessment_id == assessment_id)
        .order_by(ReconData.created_at.desc())
        .all()
    )
    
    return {
        "assessment": assessment,
        "sections": sections,
        "cards": cards,
        "recon_data": recon_data
    }


@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    assessment: AssessmentCreate,
    db: Session = Depends(get_db)
):
    """Create a new assessment"""
    service = AssessmentService(db)

    # Trim name and check if it already exists
    assessment.name = assessment.name.strip()
    existing = db.query(Assessment).filter(Assessment.name == assessment.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Assessment with name '{assessment.name}' already exists"
        )

    # Create assessment and workspace
    new_assessment = await service.create_assessment(assessment)

    # Broadcast WebSocket event
    assessment_dict = AssessmentResponse.model_validate(new_assessment).model_dump(mode='json')
    await manager.broadcast(event_assessment_created(assessment_dict))
    logger.info("Assessment created", assessment_id=new_assessment.id, name=new_assessment.name)

    return new_assessment


@router.put("/{assessment_id}", response_model=AssessmentResponse)
async def update_assessment(
    assessment_id: int,
    assessment_update: AssessmentUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing assessment"""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Update fields
    update_data = assessment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assessment, field, value)

    db.commit()
    db.refresh(assessment)

    # Broadcast WebSocket event (serialize dates to ISO strings for JSON)
    serialized_update_data = serialize_for_json(update_data)
    await manager.broadcast(
        event_assessment_updated(assessment_id, serialized_update_data),
        assessment_id=assessment_id
    )
    logger.info("Assessment updated", assessment_id=assessment_id, fields=list(update_data.keys()))

    return assessment


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assessment(
    assessment_id: int,
    db: Session = Depends(get_db)
):
    """Delete an assessment"""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    db.delete(assessment)
    db.commit()

    # Broadcast WebSocket event
    await manager.broadcast(event_assessment_deleted(assessment_id))
    logger.info("Assessment deleted", assessment_id=assessment_id)

    return None


@router.post("/{assessment_id}/duplicate", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_assessment(
    assessment_id: int,
    options: DuplicateAssessmentRequest = Body(default=DuplicateAssessmentRequest()),
    db: Session = Depends(get_db)
):
    """Duplicate an assessment with a new workspace and optional data copy"""
    original = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Generate unique name for duplicate
    if options.name and options.name.strip():
        duplicate_name = options.name.strip()
        # If the provided name already exists, reject it
        if db.query(Assessment).filter(Assessment.name == duplicate_name).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An assessment with the name '{duplicate_name}' already exists"
            )
    else:
        duplicate_name = f"{original.name} (Copy)"
        counter = 1
        while db.query(Assessment).filter(Assessment.name == duplicate_name).first():
            counter += 1
            duplicate_name = f"{original.name} (Copy {counter})"

    # Create duplicate with new workspace
    service = AssessmentService(db)

    # Create duplicate data
    duplicate_data = AssessmentCreate(
        name=duplicate_name,
        client_name=original.client_name,
        scope=original.scope,
        limitations=original.limitations,
        start_date=original.start_date,
        end_date=original.end_date,
        target_domains=original.target_domains,
        ip_scopes=original.ip_scopes,
        credentials=original.credentials,
        access_info=original.access_info,
        category=original.category,
        environment_notes=original.environment_notes
    )

    # Create assessment with workspace
    duplicate = await service.create_assessment(duplicate_data)

    # Set folder to same as original
    if original.folder_id:
        duplicate.folder_id = original.folder_id
        db.commit()
        db.refresh(duplicate)

    # Conditionally copy related data
    needs_commit = False

    if options.include_cards:
        for card in original.cards:
            db.add(Card(
                assessment_id=duplicate.id,
                card_type=card.card_type,
                title=card.title,
                target_service=card.target_service,
                severity=card.severity,
                status=card.status,
                section_number=card.section_number,
                technical_analysis=card.technical_analysis,
                proof=card.proof,
                notes=card.notes,
                context=card.context,
                cvss_vector=card.cvss_vector,
                cvss_score=card.cvss_score,
            ))
        needs_commit = True

    if options.include_sections:
        for section in original.sections:
            db.add(AssessmentSection(
                assessment_id=duplicate.id,
                section_type=section.section_type,
                section_number=section.section_number,
                title=section.title,
                content=section.content,
            ))
        needs_commit = True

    if options.include_recon:
        for recon in original.recon_data:
            db.add(ReconData(
                assessment_id=duplicate.id,
                data_type=recon.data_type,
                name=recon.name,
                details=recon.details,
                discovered_in_phase=recon.discovered_in_phase,
            ))
        needs_commit = True

    if options.include_commands:
        for cmd in original.command_history:
            db.add(CommandHistory(
                assessment_id=duplicate.id,
                command=cmd.command,
                stdout=cmd.stdout,
                stderr=cmd.stderr,
                returncode=cmd.returncode,
                execution_time=cmd.execution_time,
                success=cmd.success,
                phase=cmd.phase,
                status=cmd.status,
            ))
        needs_commit = True

    if needs_commit:
        db.commit()
        db.refresh(duplicate)

    return duplicate


@router.post("/{assessment_id}/move", response_model=AssessmentResponse)
async def move_assessment(
    assessment_id: int,
    request_data: dict,
    db: Session = Depends(get_db)
):
    """Move an assessment to a folder"""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    folder_id = request_data.get('folder_id')
    
    # Validate folder exists if provided
    if folder_id is not None:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Folder with id {folder_id} not found"
            )

    assessment.folder_id = folder_id
    db.commit()
    db.refresh(assessment)
    return assessment


# ========== Scan Import Endpoints ==========

class ScanImportRequest(BaseModel):
    """Request body for importing parsed scan items"""
    item_ids: List[str] = []  # Empty = import all non-duplicates
    items: dict  # The parsed items from parse-scans endpoint


@router.post("/{assessment_id}/parse-scans")
async def parse_scan_files(
    assessment_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Parse uploaded scan files and return preview with deduplication info
    
    Supported formats:
    - nmap XML (-oX output)
    - nuclei JSON/JSONL (-json output)
    - ffuf JSON (-of json output)
    
    Returns parsed data grouped by type (services, endpoints, findings)
    with duplicate detection against existing assessment data.
    """
    # Check if assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )
    
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files uploaded"
        )
    
    # Read all files
    file_data = []
    for file in files:
        content = await file.read()
        file_data.append((content, file.filename))
    
    # Initialize importer and parse
    importer = ScanImporter(db, assessment_id)
    
    try:
        result = importer.parse_files(file_data)
        return result
    except ScanImportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Scan parse error", error=str(e), assessment_id=assessment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error parsing scan files: {str(e)}"
        )


@router.post("/{assessment_id}/import-scans")
async def import_scan_results(
    assessment_id: int,
    request: ScanImportRequest,
    db: Session = Depends(get_db)
):
    """
    Import selected scan results into the assessment
    
    Creates:
    - ReconData entries for services and endpoints
    - Card entries for findings (from nuclei)
    - ReconData entries for vulnerabilities
    
    Automatically skips duplicates based on dedup_key.
    """
    # Check if assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )
    
    # Initialize importer
    importer = ScanImporter(db, assessment_id)
    
    try:
        stats = importer.import_items(request.item_ids, request.items)
        
        total = stats["services"] + stats["endpoints"] + stats["findings"]
        
        return {
            "success": True,
            "message": f"Successfully imported {total} items",
            "stats": stats
        }
    except ScanImportError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Scan import error", error=str(e), assessment_id=assessment_id)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error importing scan results: {str(e)}"
        )




class ChangeContainerRequest(BaseModel):
    """Request body for changing assessment container"""
    container_name: str


@router.put("/{assessment_id}/container")
async def change_assessment_container(
    assessment_id: int,
    request: ChangeContainerRequest,
    db: Session = Depends(get_db)
):
    """
    Change the container for an assessment

    This will:
    1. Validate the new container exists
    2. Update the assessment's container_name
    3. Recreate the workspace in the new container
    4. Return updated assessment info

    Args:
        assessment_id: ID of the assessment
        container_name: Name of the new container

    Returns:
        Success response with updated workspace info
    """
    container_name = request.container_name

    logger.info(
        "Changing assessment container",
        assessment_id=assessment_id,
        new_container=container_name
    )

    try:
        # Load assessment
        assessment = db.query(Assessment).filter(
            Assessment.id == assessment_id
        ).first()

        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment with id {assessment_id} not found"
            )

        # Validate container exists
        container_service = ContainerService()
        containers = await container_service.discover_containers(force_refresh=True)

        container_exists = any(
            c["name"] == container_name for c in containers
        )

        if not container_exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Container '{container_name}' not found. Available containers: {[c['name'] for c in containers]}"
            )

        # Store old container for logging
        old_container = assessment.container_name

        # Update container and recreate workspace
        # NOTE: Don't pass db to create_workspace() here to prevent it from
        # reloading the default container from database settings
        container_service.current_container = container_name

        workspace_result = await container_service.create_workspace(
            assessment_name=assessment.name
        )

        # Update assessment
        assessment.container_name = workspace_result["container_name"]
        assessment.workspace_path = workspace_result["workspace_path"]
        db.commit()
        db.refresh(assessment)

        logger.info(
            "Successfully changed assessment container",
            assessment_id=assessment_id,
            old_container=old_container,
            new_container=container_name,
            new_workspace=workspace_result["workspace_path"]
        )

        # Broadcast update via WebSocket
        await manager.broadcast(
            event_assessment_updated(assessment_id, {
                "container_name": container_name,
                "workspace_path": workspace_result["workspace_path"]
            }),
            assessment_id=assessment_id
        )

        return {
            "success": True,
            "assessment_id": assessment_id,
            "old_container": old_container,
            "new_container": container_name,
            "workspace_path": workspace_result["workspace_path"],
            "message": f"Container changed from '{old_container}' to '{container_name}' and workspace recreated"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to change assessment container",
            assessment_id=assessment_id,
            container_name=container_name,
            error=str(e)
        )
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change container: {str(e)}"
        )
