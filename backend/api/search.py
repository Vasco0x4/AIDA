"""
Unified Search API endpoint
"""
import time
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.search import SearchResponse, SearchRequest
from services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    types: Optional[str] = Query(None, description="Comma-separated types: assessment,command,finding,observation,info,recon"),
    assessment_id: Optional[int] = Query(None, description="Filter by assessment ID"),
    severity: Optional[str] = Query(None, description="Comma-separated severities: CRITICAL,HIGH,MEDIUM,LOW,INFO"),
    status: Optional[str] = Query(None, description="Comma-separated statuses: confirmed,potential,untested"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    db: Session = Depends(get_db)
):
    """
    Unified search endpoint across all entities

    Supports filtering by severity, status, and date range in addition to text search.
    """
    start_time = time.time()

    # Parse types filter
    type_list = None
    if types:
        type_list = [t.strip() for t in types.split(',')]

    severity_list = None
    if severity:
        severity_list = [s.strip().upper() for s in severity.split(',')]

    status_list = None
    if status:
        status_list = [s.strip() for s in status.split(',')]

    # Execute search
    search_service = SearchService(db)
    results = search_service.search_all(
        query=q,
        types=type_list,
        assessment_id=assessment_id,
        severity=severity_list,
        status=status_list,
        date_from=date_from,
        date_to=date_to,
        limit=limit
    )

    # Group results by type
    grouped = {}
    for result in results:
        result_type = result.type
        if result_type not in grouped:
            grouped[result_type] = []
        grouped[result_type].append(result)

    execution_time = time.time() - start_time

    return SearchResponse(
        results=results,
        total=len(results),
        query=q,
        execution_time=round(execution_time, 3),
        grouped=grouped
    )
