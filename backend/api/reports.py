"""
Report generation API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Assessment
from services.report_service import generate_pdf_report
from middleware.rate_limit import limiter
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/assessments/{assessment_id}/report", tags=["reports"])


@router.get("/pdf")
@limiter.limit("5/minute")
async def download_pdf_report(
    request: Request,
    assessment_id: int,
    db: Session = Depends(get_db),
):
    """Generate and download a PDF pentest report for the assessment."""

    # Verify assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found",
        )

    try:
        pdf_buffer = generate_pdf_report(db, assessment_id)
    except Exception as e:
        logger.error("Report generation failed", assessment_id=assessment_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}",
        )

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in assessment.name)
    filename = f"AIDA_Report_{safe_name}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
