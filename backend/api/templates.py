"""
Assessment Templates API endpoints
"""
from fastapi import APIRouter, HTTPException
from services.template_service import get_all_templates, get_template

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates():
    """List all available assessment templates"""
    return get_all_templates()


@router.get("/{template_id}")
def get_template_detail(template_id: str):
    """Get full template details including phases"""
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return template
