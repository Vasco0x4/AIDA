"""
Submission-ready report generator.

Turns a finding (Card) into a polished, platform-formatted bug-bounty report
(HackerOne / Bugcrowd / generic) — Title, Severity+CVSS, Summary, Steps to
Reproduce, Impact, Remediation, References — grounded by a similar DISCLOSED
report from the knowledge base so the tone/structure match what triage expects.
"""
from __future__ import annotations


from sqlalchemy.orm import Session

from models.card import Card
from models.assessment import Assessment
from models.artifact import Artifact
from services.ai_model_service import AIModelService
from services.knowledge_service import KnowledgeService
from services.llm import LLMError
from utils.logger import get_logger

logger = get_logger(__name__)

PLATFORM_HINTS = {
    "hackerone": ("HackerOne. Use their expected structure: a concise Title, Severity with a CVSS 3.1 "
                  "vector, Summary, Steps To Reproduce (numbered, exact), Impact, Supporting "
                  "Material/References, and Remediation. Professional, factual, no hype."),
    "bugcrowd": ("Bugcrowd (VRT-aware). Title, Priority (P1-P5) + CVSS, Description, Steps to Reproduce, "
                 "Impact, Remediation, References. Map to a VRT category if obvious."),
    "generic": ("A generic responsible-disclosure report: Title, Severity+CVSS, Summary, Steps to "
                "Reproduce, Impact, Remediation, References."),
}


async def generate_submission(db: Session, card_id: int, platform: str = "hackerone") -> dict:
    card = db.query(Card).filter(Card.id == card_id).first()
    if not card:
        raise ValueError("Finding not found")
    assessment = db.query(Assessment).filter(Assessment.id == card.assessment_id).first()

    ai = AIModelService(db)
    cfg = ai.get_default()
    if not cfg or not cfg.api_key_encrypted:
        raise RuntimeError("No AI model configured (Settings → AI Models).")

    # Ground with the most similar disclosed report(s).
    ks = KnowledgeService(db)
    query = f"{card.title} {card.target_service or ''}".strip()
    precedents = [e for e in ks.search(query=query, limit=6)
                  if e.source in ("bugbounty", "h1report")][:2]
    prec_txt = "\n".join(
        f"- {p.title} ({(p.references or ['n/a'])[0]}) — {(p.description or '')[:180]}"
        for p in precedents) or "(no close precedent found)"

    artifacts = db.query(Artifact).filter(Artifact.card_id == card_id).order_by(Artifact.id).all()
    images = [a for a in artifacts if (a.content_type or "").startswith("image/")]
    videos = [a for a in artifacts if (a.content_type or "").startswith("video/")]
    if images:
        figs = "; ".join(f"Figure {i} — {(a.caption or a.filename)}"
                         for i, a in enumerate(images, start=1))
        evidence_note = (
            f"{len(images)} screenshot(s) are ATTACHED to this report and will be embedded "
            f"in an 'Evidence — Screenshots' section at the end, numbered: {figs}. "
            f"Reference the relevant one inline where it proves a step, e.g. '(see Figure 1)'."
            + (f" Additionally {len(videos)} PoC video(s) are attached." if videos else ""))
    else:
        evidence_note = ("No screenshots attached — describe the visual proof in words."
                         + (f" ({len(videos)} PoC video(s) attached.)" if videos else ""))

    hint = PLATFORM_HINTS.get(platform, PLATFORM_HINTS["generic"])
    system = (
        "You are a senior bug-bounty hunter writing a submission-ready vulnerability report. "
        "Write ONLY the report in clean Markdown — accurate, reproducible, no fabrication. "
        "If a detail is unknown, write a clear placeholder like [REDACTED/confirm]. Base severity "
        "and CVSS on the actual finding. Target platform: " + hint)
    user = (
        f"FINDING TITLE: {card.title}\n"
        f"SEVERITY: {card.severity or 'unknown'}"
        + (f"  CVSS: {card.cvss_vector} ({card.cvss_score})" if card.cvss_vector else "") + "\n"
        f"TARGET: {card.target_service or (assessment.target_domains if assessment else '')}\n"
        f"SCOPE/PROGRAM: {(assessment.scope if assessment else '') or 'n/a'}\n\n"
        f"TECHNICAL ANALYSIS:\n{card.technical_analysis or '(none)'}\n\n"
        f"PROOF OF CONCEPT (commands + evidence):\n{card.proof or '(none)'}\n\n"
        f"NOTES:\n{card.notes or '(none)'}\n"
        f"EVIDENCE: {evidence_note}\n\n"
        f"SIMILAR DISCLOSED REPORTS (use as a structural/precedent reference; cite in References):\n{prec_txt}\n\n"
        "Produce the full submission-ready report now."
    )

    try:
        client = ai.build_client(cfg)
        params = cfg.params or {}
        resp = await client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=params.get("temperature", 0.3), max_tokens=params.get("max_tokens", 2500))
    except LLMError as e:
        raise RuntimeError(f"Model error: {e}")

    report = resp.get("content") or ""
    return {
        "card_id": card_id, "platform": platform, "report_markdown": report,
        "precedents": [{"title": p.title, "url": (p.references or [None])[0]} for p in precedents],
    }
