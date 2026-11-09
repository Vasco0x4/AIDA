"""
Report generation API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Assessment
from services.report_service import generate_pdf_report, generate_markdown_report
from middleware.rate_limit import limiter
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/assessments/{assessment_id}/report", tags=["reports"])


@router.get("/pdf")
@limiter.limit("5/minute")
async def download_pdf_report(
    request: Request,
    assessment_id: int,
    include_secrets: bool = False,
    template: str = "default",
    db: Session = Depends(get_db),
):
    """Generate and download a PDF pentest report for the assessment.

    Query params:
        include_secrets: When true, credential secrets (password, token,
            cookie, custom JSON) are embedded in clear text. Defaults to
            false — secrets are masked so the PDF is safe to share. The
            filename also gains a ``_with_creds`` suffix when secrets are
            included, so a reviewer can spot the variant at a glance.
        template: Report template (E4) — "default", or "owasp"/"pci"/"nist"
            for the compliance-mapping appendix of that framework.
    """
    if template not in ("default", "owasp", "pci", "nist"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="template must be one of: default, owasp, pci, nist")

    # Verify assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found",
        )

    try:
        pdf_buffer = await generate_pdf_report(
            db, assessment_id, include_secrets=include_secrets, template=template
        )
    except Exception as e:
        logger.error("Report generation failed", assessment_id=assessment_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}",
        )

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in assessment.name)
    suffix = "_with_creds" if include_secrets else ""
    if template != "default":
        suffix += f"_{template}"
    filename = f"AIDA_Report_{safe_name}{suffix}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/markdown")
@limiter.limit("10/minute")
async def download_markdown_report(
    request: Request,
    assessment_id: int,
    include_secrets: bool = False,
    template: str = "default",
    db: Session = Depends(get_db),
):
    """Generate a machine-readable Markdown report for the assessment."""
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found",
        )
    if template not in ("default", "owasp", "pci", "nist"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="template must be one of: default, owasp, pci, nist")
    try:
        md = generate_markdown_report(
            db, assessment_id, include_secrets=include_secrets, template=template)
    except Exception as e:
        logger.error("Markdown report failed", assessment_id=assessment_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in assessment.name)
    filename = f"AIDA_Report_{safe_name}.md"
    return PlainTextResponse(
        md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
