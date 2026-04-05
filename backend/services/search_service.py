"""
Unified search service with fuzzy matching and scoring
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, case
from datetime import datetime, timedelta

from models import Assessment, CommandHistory, Card, ReconData
from schemas.search import SearchResult


class SearchService:
    """Service for unified search across all entities"""

    def __init__(self, db: Session):
        self.db = db

    def search_all(
        self,
        query: str,
        types: Optional[List[str]] = None,
        assessment_id: Optional[int] = None,
        severity: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50
    ) -> List[SearchResult]:
        """
        Unified search across all entities with scoring, ranking, and advanced filters.
        """
        results = []
        query_lower = query.lower()

        # Parse date filters
        from_dt = None
        to_dt = None
        if date_from:
            try:
                from_dt = datetime.fromisoformat(date_from)
            except ValueError:
                pass
        if date_to:
            try:
                to_dt = datetime.fromisoformat(date_to)
            except ValueError:
                pass

        # Search in each entity type if not filtered
        if not types or 'assessment' in types:
            results.extend(self._search_assessments(query_lower, assessment_id, limit, from_dt, to_dt))

        if not types or 'command' in types:
            results.extend(self._search_commands(query_lower, assessment_id, limit, from_dt, to_dt))

        if not types or any(t in ['finding', 'observation', 'info'] for t in (types or [])):
            results.extend(self._search_cards(query_lower, assessment_id, limit, types, severity, status, from_dt, to_dt))

        if not types or 'recon' in types:
            results.extend(self._search_recon(query_lower, assessment_id, limit, from_dt, to_dt))

        # Post-filter by severity/status for non-card results (cards already filtered in query)
        if severity:
            results = [r for r in results if r.type not in ('finding', 'observation', 'info') or (r.metadata and r.metadata.get('severity') in severity)]
        if status:
            results = [r for r in results if r.type not in ('finding', 'observation', 'info') or (r.metadata and r.metadata.get('status') in status)]

        # Sort by score (descending) and take top results
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def _calculate_score(
        self,
        text: str,
        query: str,
        field_weight: float = 1.0,
        is_recent: bool = False
    ) -> float:
        """
        Calculate relevance score for a text match

        Scoring factors:
        - Exact match: +100
        - Starts with query: +50
        - Contains query: +30
        - Word match: +20
        - Fuzzy match: +10
        - Recent (< 7 days): +15
        """
        score = 0.0
        text_lower = text.lower()
        query_lower = query.lower()

        # Exact match
        if text_lower == query_lower:
            score += 100

        # Starts with
        elif text_lower.startswith(query_lower):
            score += 50

        # Contains as substring
        elif query_lower in text_lower:
            score += 30

        # Word match (any word in query matches any word in text)
        else:
            query_words = set(query_lower.split())
            text_words = set(text_lower.split())
            matching_words = query_words & text_words
            if matching_words:
                score += 20 * len(matching_words)

            # Fuzzy match (simple implementation)
            else:
                # Check if most characters from query appear in text
                query_chars = set(query_lower)
                text_chars = set(text_lower)
                match_ratio = len(query_chars & text_chars) / len(query_chars) if query_chars else 0
                if match_ratio > 0.7:
                    score += 10

        # Recency bonus
        if is_recent:
            score += 15

        # Apply field weight
        return score * field_weight

    def _search_assessments(
        self,
        query: str,
        assessment_id: Optional[int],
        limit: int,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """Search in assessments"""
        query_filter = or_(
            Assessment.name.ilike(f'%{query}%'),
            Assessment.client_name.ilike(f'%{query}%'),
            Assessment.scope.ilike(f'%{query}%'),
            Assessment.category.ilike(f'%{query}%')
        )

        q = self.db.query(Assessment).filter(query_filter)

        if assessment_id:
            q = q.filter(Assessment.id == assessment_id)
        if from_dt:
            q = q.filter(Assessment.created_at >= from_dt)
        if to_dt:
            q = q.filter(Assessment.created_at <= to_dt)

        assessments = q.limit(limit * 2).all()  # Get more for scoring

        results = []
        for assessment in assessments:
            # Check recency (created in last 7 days)
            is_recent = False
            if assessment.created_at:
                is_recent = assessment.created_at > datetime.now() - timedelta(days=7)

            # Calculate score (check all fields)
            score = max(
                self._calculate_score(assessment.name, query, 2.0, is_recent),
                self._calculate_score(assessment.client_name or '', query, 1.5, is_recent),
                self._calculate_score(assessment.scope or '', query, 1.0, is_recent),
                self._calculate_score(assessment.category or '', query, 1.0, is_recent)
            )

            if score > 0:
                results.append(SearchResult(
                    type='assessment',
                    id=assessment.id,
                    title=assessment.name,
                    subtitle=assessment.client_name or 'No client',
                    description=assessment.scope[:100] + '...' if assessment.scope else None,
                    url=f'/assessments/{assessment.id}',
                    icon='FileText',
                    score=score,
                    metadata={
                        'status': assessment.status,
                        'category': assessment.category
                    }
                ))

        return results

    def _search_commands(
        self,
        query: str,
        assessment_id: Optional[int],
        limit: int,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """Search in commands with assessment name"""
        query_filter = or_(
            CommandHistory.command.ilike(f'%{query}%'),
            CommandHistory.stdout.ilike(f'%{query}%'),
            CommandHistory.stderr.ilike(f'%{query}%'),
            CommandHistory.phase.ilike(f'%{query}%')
        )

        # Join with Assessment to get assessment name
        q = self.db.query(
            CommandHistory,
            Assessment.name.label('assessment_name')
        ).join(
            Assessment,
            CommandHistory.assessment_id == Assessment.id
        ).filter(query_filter)

        if assessment_id:
            q = q.filter(CommandHistory.assessment_id == assessment_id)
        if from_dt:
            q = q.filter(CommandHistory.created_at >= from_dt)
        if to_dt:
            q = q.filter(CommandHistory.created_at <= to_dt)

        commands = q.limit(limit * 2).all()

        results = []
        for cmd, assessment_name in commands:
            # Check recency
            is_recent = False
            if cmd.created_at:
                is_recent = cmd.created_at > datetime.now() - timedelta(days=7)

            # Calculate score
            score = max(
                self._calculate_score(cmd.command, query, 2.0, is_recent),
                self._calculate_score(cmd.stdout or '', query, 0.8, is_recent),
                self._calculate_score(cmd.phase or '', query, 1.2, is_recent)
            )

            if score > 0:
                results.append(SearchResult(
                    type='command',
                    id=cmd.id,
                    title=cmd.command[:80] + '...' if len(cmd.command) > 80 else cmd.command,
                    subtitle=f'{assessment_name} • {cmd.phase or "No phase"}',
                    description=cmd.stdout[:100] + '...' if cmd.stdout else None,
                    url=f'/assessments/{cmd.assessment_id}#command-{cmd.id}',
                    icon='Terminal',
                    score=score,
                    metadata={
                        'success': cmd.success,
                        'executionTime': cmd.execution_time,
                        'phase': cmd.phase
                    }
                ))

        return results

    def _search_cards(
        self,
        query: str,
        assessment_id: Optional[int],
        limit: int,
        types: Optional[List[str]] = None,
        severity: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """Search in cards (findings, observations, info)"""
        query_filter = or_(
            Card.title.ilike(f'%{query}%'),
            Card.technical_analysis.ilike(f'%{query}%'),
            Card.notes.ilike(f'%{query}%'),
            Card.context.ilike(f'%{query}%')
        )

        # Join with Assessment
        q = self.db.query(
            Card,
            Assessment.name.label('assessment_name')
        ).join(
            Assessment,
            Card.assessment_id == Assessment.id
        ).filter(query_filter)

        # Filter by card types if specified
        if types:
            card_types = []
            if 'finding' in types:
                card_types.append('finding')
            if 'observation' in types:
                card_types.append('observation')
            if 'info' in types:
                card_types.append('info')
            if card_types:
                q = q.filter(Card.card_type.in_(card_types))

        if assessment_id:
            q = q.filter(Card.assessment_id == assessment_id)
        if severity:
            q = q.filter(Card.severity.in_(severity))
        if status:
            q = q.filter(Card.status.in_(status))
        if from_dt:
            q = q.filter(Card.created_at >= from_dt)
        if to_dt:
            q = q.filter(Card.created_at <= to_dt)

        cards = q.limit(limit * 2).all()

        results = []
        for card, assessment_name in cards:
            # Check recency
            is_recent = False
            if card.created_at:
                is_recent = card.created_at > datetime.now() - timedelta(days=7)

            # Calculate score
            score = max(
                self._calculate_score(card.title, query, 2.5, is_recent),
                self._calculate_score(card.technical_analysis or '', query, 1.0, is_recent),
                self._calculate_score(card.notes or '', query, 0.8, is_recent)
            )

            # Boost score for high severity findings
            if card.card_type == 'finding' and card.severity in ['CRITICAL', 'HIGH']:
                score *= 1.3

            if score > 0:
                icon = 'Shield' if card.card_type == 'finding' else 'Eye' if card.card_type == 'observation' else 'Info'

                results.append(SearchResult(
                    type=card.card_type,
                    id=card.id,
                    title=card.title,
                    subtitle=f'{assessment_name} • {card.card_type}',
                    description=card.technical_analysis or card.notes or card.context,
                    url=f'/assessments/{card.assessment_id}#card-{card.id}',
                    icon=icon,
                    score=score,
                    metadata={
                        'severity': card.severity,
                        'cardType': card.card_type,
                        'status': card.status
                    }
                ))

        return results

    def _search_recon(
        self,
        query: str,
        assessment_id: Optional[int],
        limit: int,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> List[SearchResult]:
        """Search in recon data"""
        query_filter = or_(
            ReconData.name.ilike(f'%{query}%'),
            ReconData.data_type.ilike(f'%{query}%')
            # Note: details is JSONB, searching it would need more complex query
        )

        # Join with Assessment
        q = self.db.query(
            ReconData,
            Assessment.name.label('assessment_name')
        ).join(
            Assessment,
            ReconData.assessment_id == Assessment.id
        ).filter(query_filter)

        if assessment_id:
            q = q.filter(ReconData.assessment_id == assessment_id)
        if from_dt:
            q = q.filter(ReconData.created_at >= from_dt)
        if to_dt:
            q = q.filter(ReconData.created_at <= to_dt)

        recon_items = q.limit(limit * 2).all()

        results = []
        for item, assessment_name in recon_items:
            # Check recency
            is_recent = False
            if item.created_at:
                is_recent = item.created_at > datetime.now() - timedelta(days=7)

            # Calculate score
            score = max(
                self._calculate_score(item.name, query, 2.0, is_recent),
                self._calculate_score(item.data_type, query, 1.5, is_recent)
            )

            if score > 0:
                # Format details for display
                details_str = ''
                if item.details:
                    details_str = ', '.join(f'{k}: {v}' for k, v in list(item.details.items())[:3])

                results.append(SearchResult(
                    type='recon',
                    id=item.id,
                    title=item.name,
                    subtitle=f'{assessment_name} • {item.data_type}',
                    description=details_str or None,
                    url=f'/assessments/{item.assessment_id}#recon-{item.id}',
                    icon='Target',
                    score=score,
                    metadata={
                        'dataType': item.data_type,
                        'phase': item.discovered_in_phase
                    }
                ))

        return results
