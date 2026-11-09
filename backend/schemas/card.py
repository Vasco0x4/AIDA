"""
Card Pydantic schemas
"""
from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, ConfigDict


class CardBase(BaseModel):
    card_type: str  # finding, observation, info
    section_number: Optional[str] = None  # Now optional - auto-managed globally
    title: str
    target_service: Optional[str] = None
    status: Optional[str] = None  # confirmed, potential, untested
    severity: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    cvss_vector: Optional[str] = None  # CVSS 4.0 vector string
    cvss_score: Optional[float] = None  # Calculated CVSS 4.0 score
    technical_analysis: Optional[str] = None
    notes: Optional[str] = None
    proof: Optional[str] = None
    context: Optional[str] = None
    # E4 compliance mapping override: {"owasp": ["A03:2021"], ...}
    compliance_refs: Optional[Dict[str, List[str]]] = None


class CardCreate(CardBase):
    """Schema for creating a new card"""
    pass


class CardUpdate(BaseModel):
    """Schema for updating a card (all fields optional)"""
    card_type: Optional[str] = None
    section_number: Optional[str] = None
    title: Optional[str] = None
    target_service: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    cvss_vector: Optional[str] = None
    cvss_score: Optional[float] = None
    technical_analysis: Optional[str] = None
    notes: Optional[str] = None
    proof: Optional[str] = None
    context: Optional[str] = None
    compliance_refs: Optional[Dict[str, List[str]]] = None


class CardResponse(CardBase):
    """Schema for card response"""
    id: int
    assessment_id: int
    created_at: datetime
    updated_at: datetime
    fingerprint: Optional[str] = None
    lifecycle_status: Optional[str] = "new"
    first_seen_run_id: Optional[int] = None
    last_seen_run_id: Optional[int] = None
    last_seen_at: Optional[datetime] = None
    seen_count: Optional[int] = 0

    model_config = ConfigDict(from_attributes=True)


class GlobalFindingResponse(CardResponse):
    """Schema for a finding enriched with cross-assessment context"""
    assessment_name: str
    serial_number: str   # e.g. AIDA-3-001
    finding_number: int


class FindingsPaginatedResponse(BaseModel):
    """Paginated list of global findings"""
    findings: List[GlobalFindingResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class FindingsStatsResponse(BaseModel):
    """Aggregate statistics across all findings"""
    total_findings: int
    by_severity: Dict[str, int]
    by_status: Dict[str, int]
    unique_assessments: int
