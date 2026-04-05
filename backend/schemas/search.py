"""
Search Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class SearchResult(BaseModel):
    """Single search result item"""
    type: str  # 'assessment', 'command', 'finding', 'observation', 'info', 'recon'
    id: int
    title: str
    subtitle: str
    description: Optional[str] = None
    url: str
    icon: str
    score: float = 0.0  # Relevance score
    metadata: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    """Search API response"""
    results: List[SearchResult]
    total: int
    query: str
    execution_time: float  # in seconds
    grouped: Optional[Dict[str, List[SearchResult]]] = None  # Results grouped by type


class SearchRequest(BaseModel):
    """Search API request"""
    query: str
    types: Optional[List[str]] = None  # Filter by types
    assessment_id: Optional[int] = None  # Filter by assessment
    severity: Optional[List[str]] = None  # Filter by severity: CRITICAL, HIGH, MEDIUM, LOW, INFO
    status: Optional[List[str]] = None  # Filter by status: confirmed, potential, untested
    date_from: Optional[str] = None  # ISO date string
    date_to: Optional[str] = None  # ISO date string
    limit: int = 50
