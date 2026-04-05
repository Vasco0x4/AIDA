"""
Timeline service - manages attack timeline events
Supports manual creation and auto-generation from existing data
"""
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.timeline_event import TimelineEvent
from models.command_history import CommandHistory
from models.card import Card
from models.recon_data import ReconData


# Mapping of command prefixes to phases
COMMAND_PHASE_MAP = {
    "nmap": "recon",
    "dig": "recon",
    "whois": "recon",
    "subfinder": "recon",
    "amass": "recon",
    "theHarvester": "recon",
    "dnsrecon": "recon",
    "ffuf": "scanning",
    "gobuster": "scanning",
    "dirb": "scanning",
    "dirsearch": "scanning",
    "nikto": "scanning",
    "nuclei": "scanning",
    "wpscan": "scanning",
    "sqlmap": "exploitation",
    "hydra": "exploitation",
    "john": "exploitation",
    "hashcat": "exploitation",
    "msfconsole": "exploitation",
    "metasploit": "exploitation",
    "burpsuite": "exploitation",
    "curl": "scanning",
    "wget": "scanning",
    "ssh": "post_exploitation",
    "scp": "post_exploitation",
    "nc": "exploitation",
    "netcat": "exploitation",
    "linpeas": "post_exploitation",
    "winpeas": "post_exploitation",
    "mimikatz": "post_exploitation",
    "bloodhound": "post_exploitation",
}


def _guess_phase_from_command(command: str) -> str:
    """Guess the attack phase from a command string"""
    cmd_lower = command.strip().lower()
    for prefix, phase in COMMAND_PHASE_MAP.items():
        if cmd_lower.startswith(prefix):
            return phase
    return "recon"


def _guess_phase_from_card(card: Card) -> str:
    """Guess the attack phase from a card type/severity"""
    if card.card_type == "finding":
        if card.severity in ("CRITICAL", "HIGH"):
            return "exploitation"
        return "scanning"
    if card.card_type == "observation":
        return "scanning"
    return "recon"


class TimelineService:
    def __init__(self, db: Session):
        self.db = db

    def get_events(
        self,
        assessment_id: int,
        phase: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 200
    ) -> List[TimelineEvent]:
        q = self.db.query(TimelineEvent).filter(
            TimelineEvent.assessment_id == assessment_id
        )
        if phase:
            q = q.filter(TimelineEvent.phase == phase)
        if event_type:
            q = q.filter(TimelineEvent.event_type == event_type)
        return q.order_by(TimelineEvent.created_at.asc()).limit(limit).all()

    def get_phase_counts(self, assessment_id: int) -> Dict[str, int]:
        rows = (
            self.db.query(TimelineEvent.phase, func.count(TimelineEvent.id))
            .filter(TimelineEvent.assessment_id == assessment_id)
            .group_by(TimelineEvent.phase)
            .all()
        )
        return {phase: count for phase, count in rows}

    def create_event(self, assessment_id: int, **kwargs) -> TimelineEvent:
        event = TimelineEvent(assessment_id=assessment_id, **kwargs)
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def delete_event(self, event_id: int, assessment_id: int) -> bool:
        event = self.db.query(TimelineEvent).filter(
            TimelineEvent.id == event_id,
            TimelineEvent.assessment_id == assessment_id
        ).first()
        if not event:
            return False
        self.db.delete(event)
        self.db.commit()
        return True

    def auto_generate(self, assessment_id: int) -> int:
        """
        Auto-generate timeline events from existing commands, cards, and recon data.
        Skips entities that already have linked timeline events.
        Returns count of generated events.
        """
        generated = 0

        # Get existing linked IDs to avoid duplicates
        existing_cmd_ids = set(
            r[0] for r in self.db.query(TimelineEvent.command_id)
            .filter(TimelineEvent.assessment_id == assessment_id, TimelineEvent.command_id.isnot(None))
            .all()
        )
        existing_card_ids = set(
            r[0] for r in self.db.query(TimelineEvent.card_id)
            .filter(TimelineEvent.assessment_id == assessment_id, TimelineEvent.card_id.isnot(None))
            .all()
        )
        existing_recon_ids = set(
            r[0] for r in self.db.query(TimelineEvent.recon_id)
            .filter(TimelineEvent.assessment_id == assessment_id, TimelineEvent.recon_id.isnot(None))
            .all()
        )

        # Generate from commands
        commands = self.db.query(CommandHistory).filter(
            CommandHistory.assessment_id == assessment_id
        ).order_by(CommandHistory.created_at.asc()).all()

        for cmd in commands:
            if cmd.id in existing_cmd_ids:
                continue
            phase = cmd.phase or _guess_phase_from_command(cmd.command)
            cmd_short = cmd.command[:80] + "..." if len(cmd.command) > 80 else cmd.command
            event = TimelineEvent(
                assessment_id=assessment_id,
                phase=phase,
                event_type="command",
                title=cmd_short,
                description=f"Exit code: {cmd.returncode}" if cmd.returncode is not None else None,
                command_id=cmd.id,
                severity="INFO",
                icon="terminal",
                created_at=cmd.created_at,
            )
            self.db.add(event)
            generated += 1

        # Generate from cards (findings/observations)
        cards = self.db.query(Card).filter(
            Card.assessment_id == assessment_id
        ).order_by(Card.created_at.asc()).all()

        for card in cards:
            if card.id in existing_card_ids:
                continue
            phase = _guess_phase_from_card(card)
            event = TimelineEvent(
                assessment_id=assessment_id,
                phase=phase,
                event_type=card.card_type,
                title=card.title,
                description=card.target_service,
                card_id=card.id,
                severity=card.severity or "INFO",
                icon="shield" if card.card_type == "finding" else "eye",
                created_at=card.created_at,
            )
            self.db.add(event)
            generated += 1

        # Generate from recon data
        recon_items = self.db.query(ReconData).filter(
            ReconData.assessment_id == assessment_id
        ).order_by(ReconData.created_at.asc()).all()

        for item in recon_items:
            if item.id in existing_recon_ids:
                continue
            event = TimelineEvent(
                assessment_id=assessment_id,
                phase="recon",
                event_type="recon",
                title=f"{item.data_type}: {item.name}",
                recon_id=item.id,
                severity="INFO",
                icon="target",
                created_at=item.created_at,
            )
            self.db.add(event)
            generated += 1

        if generated > 0:
            self.db.commit()

        return generated
