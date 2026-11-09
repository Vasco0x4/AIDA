"""
Load the offensive-security skill base (skills/*/SKILL.md) into the knowledge
layer so `search_knowledge` surfaces it and the agent can `read_skill` the full
methodology + references on demand — independent of which model runs the agent.

SKILL.md files use YAML-ish frontmatter (name, description, triggers) + a Markdown
body. We parse it without a YAML dependency (frontmatter here is single-line
fields + a simple triggers list).
"""
from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from models.knowledge_entry import KnowledgeEntry
from utils.logger import get_logger

logger = get_logger(__name__)

SKILLS_ROOT = os.getenv("SKILLS_ROOT", "/skills")
_MAX_CONTENT = 16000


def _parse_frontmatter(text: str):
    """Return (meta: dict, body: str). meta has name/description/triggers."""
    meta = {"name": None, "description": "", "triggers": []}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return meta, body
    fm, body = m.group(1), m.group(2)

    name = re.search(r'^name:\s*"?([^"\n]+)"?\s*$', fm, re.M)
    if name:
        meta["name"] = name.group(1).strip()

    # description may be a long single-line quoted string.
    desc = re.search(r'^description:\s*"(.*?)"\s*$', fm, re.M | re.S)
    if not desc:
        desc = re.search(r'^description:\s*(.+)$', fm, re.M)
    if desc:
        meta["description"] = desc.group(1).strip().strip('"')

    # triggers: subsequent "  - item" lines under "triggers:".
    tm = re.search(r'^triggers:\s*\n((?:\s*-\s*.+\n?)+)', fm, re.M)
    if tm:
        meta["triggers"] = [t.strip().lstrip("- ").strip()
                            for t in tm.group(1).splitlines() if t.strip()]
    return meta, body


def load_skills(db: Session, root: str = None) -> int:
    """Upsert every skills/*/SKILL.md into knowledge_entries (source='skill')."""
    root = root or SKILLS_ROOT
    if not os.path.isdir(root):
        logger.warning("skills root not found; skipping skill load", root=root)
        return 0

    loaded = 0
    for entry in sorted(os.listdir(root)):
        sdir = os.path.join(root, entry)
        skill_md = os.path.join(sdir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            text = open(skill_md, encoding="utf-8").read()
        except Exception as e:
            logger.warning("could not read skill", skill=entry, error=str(e))
            continue

        meta, body = _parse_frontmatter(text)
        name = meta["name"] or entry
        refs = []
        refdir = os.path.join(sdir, "references")
        if os.path.isdir(refdir):
            refs = sorted(f for f in os.listdir(refdir) if f.endswith(".md"))

        ext_id = entry  # directory name is the stable slug
        row = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.ext_id == ext_id, KnowledgeEntry.source == "skill").first()
        if not row:
            row = KnowledgeEntry(ext_id=ext_id, source="skill")
            db.add(row)
        row.title = name
        row.description = (meta["description"] or "")[:2000]
        row.content = body.strip()[:_MAX_CONTENT]
        row.tags = (", ".join(meta["triggers"]) or entry)[:400]
        row.references = refs
        loaded += 1

    db.commit()
    logger.info("Loaded offensive-security skills", count=loaded, root=root)
    return loaded


def read_skill_file(slug: str, reference: str = None, root: str = None) -> str:
    """Read a skill's SKILL.md, or one of its reference files (safe path only)."""
    root = root or SKILLS_ROOT
    # Sanitize slug + reference to prevent path traversal.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", slug or ""):
        return ""
    if reference:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", reference):
            return ""
        path = os.path.join(root, slug, "references", reference)
    else:
        path = os.path.join(root, slug, "SKILL.md")
    real = os.path.realpath(path)
    if not real.startswith(os.path.realpath(root) + os.sep):
        return ""
    if not os.path.isfile(real):
        return ""
    try:
        return open(real, encoding="utf-8").read()
    except Exception:
        return ""
