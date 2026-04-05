"""
Report generation service - produces PDF pentest reports from assessment data
"""
import io
import base64
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Template
from weasyprint import HTML
from sqlalchemy.orm import Session

from models import Assessment, Card, ReconData, AssessmentSection, CommandHistory, Credential
from utils.logger import get_logger

logger = get_logger(__name__)

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
SEVERITY_COLORS = {
    "CRITICAL": "#e11d48",
    "HIGH": "#f43f5e",
    "MEDIUM": "#f59e0b",
    "LOW": "#3b82f6",
    "INFO": "#64748b",
}
SEVERITY_BG = {
    "CRITICAL": "rgba(225,29,72,0.08)",
    "HIGH": "rgba(244,63,94,0.08)",
    "MEDIUM": "rgba(245,158,11,0.08)",
    "LOW": "rgba(59,130,246,0.08)",
    "INFO": "rgba(100,116,139,0.08)",
}


def _load_logo_b64() -> str:
    """Load AIDA logo as base64 data URI."""
    logo_candidates = [
        Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "assets" / "aida-logo.png",
        Path(__file__).resolve().parent.parent / "assets" / "aida-logo.png",
    ]
    for p in logo_candidates:
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            return f"data:image/png;base64,{b64}"
    return ""


def _compute_risk_score(findings: list) -> str:
    """Compute overall risk level from findings."""
    if not findings:
        return "INFORMATIONAL"
    worst = min(SEVERITY_ORDER.get(f.severity or "INFO", 99) for f in findings)
    return {0: "CRITICAL", 1: "HIGH", 2: "MEDIUM", 3: "LOW"}.get(worst, "INFORMATIONAL")


def generate_pdf_report(db: Session, assessment_id: int) -> io.BytesIO:
    """Generate a PDF pentest report for the given assessment."""

    # --- Fetch data ---
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise ValueError(f"Assessment {assessment_id} not found")

    cards = (
        db.query(Card)
        .filter(Card.assessment_id == assessment_id)
        .all()
    )
    findings = sorted(
        [c for c in cards if c.card_type == "finding"],
        key=lambda c: SEVERITY_ORDER.get(c.severity or "INFO", 99),
    )
    observations = [c for c in cards if c.card_type == "observation"]
    info_cards = [c for c in cards if c.card_type == "info"]

    sections = (
        db.query(AssessmentSection)
        .filter(AssessmentSection.assessment_id == assessment_id)
        .order_by(AssessmentSection.section_number)
        .all()
    )

    recon = (
        db.query(ReconData)
        .filter(ReconData.assessment_id == assessment_id)
        .all()
    )

    credentials = (
        db.query(Credential)
        .filter(Credential.assessment_id == assessment_id)
        .all()
    )

    commands_count = (
        db.query(CommandHistory)
        .filter(CommandHistory.assessment_id == assessment_id)
        .count()
    )

    # --- Severity stats ---
    severity_counts = {}
    for f in findings:
        sev = f.severity or "INFO"
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    max_sev_count = max(severity_counts.values()) if severity_counts else 1

    # --- Risk score ---
    risk_score = _compute_risk_score(findings)

    # --- Logo ---
    logo_b64 = _load_logo_b64()

    # --- Render HTML ---
    html_content = REPORT_TEMPLATE.render(
        assessment=assessment,
        findings=findings,
        observations=observations,
        info_cards=info_cards,
        sections=sections,
        recon=recon,
        credentials=credentials,
        commands_count=commands_count,
        severity_counts=severity_counts,
        severity_colors=SEVERITY_COLORS,
        severity_bg=SEVERITY_BG,
        severity_order=SEVERITY_ORDER,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        total_findings=len(findings),
        total_observations=len(observations),
        total_recon=len(recon),
        total_credentials=len(credentials),
        max_sev_count=max_sev_count,
        risk_score=risk_score,
        logo_b64=logo_b64,
    )

    # --- Generate PDF ---
    pdf_buffer = io.BytesIO()
    HTML(string=html_content).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)

    logger.info(
        "Report generated",
        assessment_id=assessment_id,
        findings=len(findings),
        observations=len(observations),
    )

    return pdf_buffer


# ---------------------------------------------------------------------------
# Jinja2 HTML template — professional AIDA pentest report
# ---------------------------------------------------------------------------

REPORT_TEMPLATE = Template('''\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  /* ================================================================
     PAGE & BASE
     ================================================================ */
  @page {
    size: A4;
    margin: 1.8cm 2cm 2.2cm 2cm;
    @bottom-left {
      content: "CONFIDENTIAL — AIDA Security Report";
      font-size: 7pt;
      color: #94a3b8;
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
    @bottom-right {
      content: "Page " counter(page) " / " counter(pages);
      font-size: 7pt;
      color: #94a3b8;
      font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
  }
  @page :first {
    margin: 0;
    @bottom-left  { content: none; }
    @bottom-right { content: none; }
  }

  :root {
    --primary: #6366f1;
    --primary-dark: #4338ca;
    --bg-dark: #0f172a;
    --bg-card: #ffffff;
    --border: #e2e8f0;
    --text: #1e293b;
    --text-light: #64748b;
    --text-muted: #94a3b8;
    --accent-critical: #e11d48;
    --accent-high: #f43f5e;
    --accent-medium: #f59e0b;
    --accent-low: #3b82f6;
    --accent-info: #64748b;
  }

  * { box-sizing: border-box; }

  body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.6;
    color: var(--text);
    margin: 0;
    padding: 0;
  }

  /* ================================================================
     COVER PAGE — dark gradient
     ================================================================ */
  .cover {
    page-break-after: always;
    width: 210mm;
    height: 297mm;
    background: linear-gradient(160deg, #0f172a 0%, #1e1b4b 40%, #312e81 100%);
    color: #ffffff;
    padding: 0;
    position: relative;
    overflow: hidden;
  }

  /* decorative circles */
  .cover::before {
    content: "";
    position: absolute;
    width: 500px;
    height: 500px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%);
    top: -120px;
    right: -120px;
  }
  .cover::after {
    content: "";
    position: absolute;
    width: 350px;
    height: 350px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%);
    bottom: 60px;
    left: -80px;
  }

  .cover-inner {
    position: relative;
    z-index: 1;
    padding: 80px 60px 60px 60px;
    height: 100%;
  }

  .cover-logo {
    width: 90px;
    height: auto;
    margin-bottom: 16px;
    opacity: 0.95;
  }

  .cover-brand {
    font-size: 13pt;
    font-weight: 600;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #a5b4fc;
    margin-bottom: 60px;
  }

  .cover-line {
    width: 60px;
    height: 3px;
    background: linear-gradient(90deg, #6366f1, #a78bfa);
    border: none;
    margin: 0 0 30px 0;
    border-radius: 2px;
  }

  .cover h1 {
    font-size: 32pt;
    font-weight: 700;
    line-height: 1.15;
    margin: 0 0 12px 0;
    color: #ffffff;
  }

  .cover .cover-subtitle {
    font-size: 15pt;
    font-weight: 400;
    color: #c7d2fe;
    margin-bottom: 50px;
  }

  .cover-meta-grid {
    margin-top: auto;
    position: absolute;
    bottom: 80px;
    left: 60px;
    right: 60px;
  }

  .cover-meta-row {
    padding: 10px 0;
    border-top: 1px solid rgba(255,255,255,0.1);
  }
  .cover-meta-row:last-child {
    border-bottom: 1px solid rgba(255,255,255,0.1);
  }

  .cover-meta-label {
    display: inline-block;
    width: 120px;
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #a5b4fc;
  }
  .cover-meta-value {
    font-size: 10pt;
    color: #e2e8f0;
  }

  .cover-footer {
    position: absolute;
    bottom: 25px;
    left: 60px;
    right: 60px;
    text-align: center;
    font-size: 7.5pt;
    color: rgba(255,255,255,0.3);
    letter-spacing: 0.5px;
  }

  /* ================================================================
     TABLE OF CONTENTS
     ================================================================ */
  .toc {
    page-break-after: always;
    padding-top: 20px;
  }
  .toc h2 {
    font-size: 18pt;
    color: var(--primary-dark);
    border: none;
    margin-bottom: 30px;
    padding-bottom: 0;
  }
  .toc-item {
    padding: 8px 0;
    border-bottom: 1px dotted #cbd5e1;
    font-size: 10pt;
  }
  .toc-item a {
    color: var(--text);
    text-decoration: none;
  }
  .toc-num {
    display: inline-block;
    width: 30px;
    font-weight: 700;
    color: var(--primary);
  }

  /* ================================================================
     SECTION HEADINGS
     ================================================================ */
  h2 {
    font-size: 16pt;
    font-weight: 700;
    color: var(--bg-dark);
    margin-top: 35px;
    margin-bottom: 6px;
    padding-bottom: 8px;
    border-bottom: 3px solid var(--primary);
    letter-spacing: -0.3px;
  }
  h2 .section-num {
    color: var(--primary);
    margin-right: 6px;
  }
  h3 {
    font-size: 11.5pt;
    font-weight: 600;
    margin-top: 22px;
    margin-bottom: 4px;
    color: #334155;
  }

  /* ================================================================
     RISK BANNER
     ================================================================ */
  .risk-banner {
    border-radius: 10px;
    padding: 20px 24px;
    margin: 20px 0 28px 0;
    color: #fff;
    text-align: center;
  }
  .risk-banner .risk-label {
    font-size: 8pt;
    text-transform: uppercase;
    letter-spacing: 2px;
    opacity: 0.85;
    margin-bottom: 4px;
  }
  .risk-banner .risk-level {
    font-size: 22pt;
    font-weight: 800;
    letter-spacing: 1px;
  }

  /* ================================================================
     STATS CARDS
     ================================================================ */
  .stats-row {
    width: 100%;
    margin: 16px 0 24px 0;
    border-collapse: separate;
    border-spacing: 8px 0;
  }
  .stat-card {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 10px;
    text-align: center;
    width: 25%;
  }
  .stat-num {
    font-size: 24pt;
    font-weight: 800;
    line-height: 1.1;
  }
  .stat-label {
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--text-light);
    margin-top: 2px;
  }

  /* ================================================================
     SEVERITY BAR CHART
     ================================================================ */
  .sev-chart {
    margin: 16px 0 20px 0;
    width: 100%;
  }
  .sev-chart-row {
    margin-bottom: 8px;
  }
  .sev-chart-label {
    display: inline-block;
    width: 70px;
    font-size: 8pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    vertical-align: middle;
  }
  .sev-chart-bar-bg {
    display: inline-block;
    width: calc(100% - 110px);
    height: 22px;
    background: #f1f5f9;
    border-radius: 4px;
    vertical-align: middle;
    overflow: hidden;
  }
  .sev-chart-bar {
    height: 100%;
    border-radius: 4px;
    min-width: 2px;
  }
  .sev-chart-count {
    display: inline-block;
    width: 30px;
    text-align: right;
    font-size: 9pt;
    font-weight: 700;
    vertical-align: middle;
    color: var(--text);
  }

  /* ================================================================
     FINDING CARDS
     ================================================================ */
  .finding {
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 18px;
    page-break-inside: avoid;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .finding-header {
    padding: 12px 18px;
    color: #fff;
    font-weight: 700;
    font-size: 10.5pt;
    letter-spacing: -0.2px;
  }
  .finding-header .finding-id {
    opacity: 0.7;
    font-weight: 400;
    font-size: 8.5pt;
    margin-left: 8px;
  }
  .finding-body {
    padding: 16px 18px;
    background: #fff;
  }
  .finding-meta {
    font-size: 8.5pt;
    color: var(--text-light);
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #f1f5f9;
  }
  .finding-meta span {
    margin-right: 18px;
  }
  .finding-meta strong {
    color: var(--text);
  }

  .finding-field {
    margin-top: 12px;
  }
  .finding-field .field-label {
    font-size: 7.5pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-light);
    margin-bottom: 4px;
  }
  .finding-field pre {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 8.5pt;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-x: hidden;
    max-width: 100%;
    color: #334155;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  }

  /* CVSS badge */
  .cvss-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 8.5pt;
    font-weight: 700;
    color: #fff;
    margin-left: 4px;
  }

  /* ================================================================
     SEVERITY BADGE
     ================================================================ */
  .severity {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 7.5pt;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.5px;
  }

  /* ================================================================
     OBSERVATION CARDS
     ================================================================ */
  .obs-card {
    border-left: 4px solid var(--primary);
    background: #f8fafc;
    border-radius: 0 8px 8px 0;
    padding: 14px 18px;
    margin-bottom: 14px;
    page-break-inside: avoid;
  }
  .obs-card h4 {
    margin: 0 0 6px 0;
    font-size: 10.5pt;
    color: var(--primary-dark);
  }
  .obs-card p {
    margin: 2px 0;
    font-size: 9pt;
    color: var(--text-light);
  }
  .obs-card pre {
    background: #fff;
    border: 1px solid var(--border);
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 8.5pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    margin-top: 8px;
    color: #334155;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  }

  /* ================================================================
     TABLES
     ================================================================ */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 8.5pt;
  }
  th, td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid #e2e8f0;
  }
  th {
    background: #f8fafc;
    font-weight: 700;
    font-size: 7.5pt;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--text-light);
    border-bottom: 2px solid var(--border);
  }
  tr:nth-child(even) td { background: #fafbfc; }

  /* ================================================================
     CREDENTIALS TABLE
     ================================================================ */
  .cred-type {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 8px;
    font-size: 7.5pt;
    font-weight: 600;
    background: #ede9fe;
    color: #5b21b6;
  }

  /* ================================================================
     RECON SECTION
     ================================================================ */
  .recon-type-heading {
    font-weight: 700;
    font-size: 10pt;
    color: var(--primary-dark);
    margin-top: 16px;
    margin-bottom: 6px;
    padding: 6px 12px;
    background: #f1f5f9;
    border-radius: 6px;
    border-left: 3px solid var(--primary);
  }

  /* ================================================================
     PHASE / SECTION CARDS
     ================================================================ */
  .phase-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 14px;
    page-break-inside: avoid;
    overflow: hidden;
  }
  .phase-header {
    background: #f8fafc;
    padding: 10px 16px;
    font-weight: 700;
    font-size: 10pt;
    color: #334155;
    border-bottom: 1px solid var(--border);
  }
  .phase-body {
    padding: 14px 16px;
  }
  .phase-body pre {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 8.5pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: #334155;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    margin: 0;
  }

  /* ================================================================
     INFO CARDS
     ================================================================ */
  .info-card {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 12px;
    page-break-inside: avoid;
  }
  .info-card h4 {
    margin: 0 0 8px 0;
    font-size: 10pt;
    color: #92400e;
  }
  .info-card pre {
    background: #fff;
    border: 1px solid #fde68a;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 8.5pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: #334155;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  }

  /* ================================================================
     MISC
     ================================================================ */
  .text-muted { color: var(--text-muted); font-size: 8.5pt; }
  .page-break { page-break-before: always; }
  a { color: var(--primary); text-decoration: none; }
  p { margin: 4px 0; }
</style>
</head>
<body>

<!-- ===================== COVER PAGE ===================== -->
<div class="cover">
  <div class="cover-inner">
    {% if logo_b64 %}
    <img class="cover-logo" src="{{ logo_b64 }}" alt="AIDA">
    {% endif %}
    <div class="cover-brand">AIDA</div>

    <hr class="cover-line">
    <h1>Security Assessment<br>Report</h1>
    <div class="cover-subtitle">{{ assessment.name }}</div>

    <div class="cover-meta-grid">
      {% if assessment.client_name %}
      <div class="cover-meta-row">
        <span class="cover-meta-label">Client</span>
        <span class="cover-meta-value">{{ assessment.client_name }}</span>
      </div>
      {% endif %}
      {% if assessment.category %}
      <div class="cover-meta-row">
        <span class="cover-meta-label">Category</span>
        <span class="cover-meta-value">{{ assessment.category }}</span>
      </div>
      {% endif %}
      {% if assessment.start_date %}
      <div class="cover-meta-row">
        <span class="cover-meta-label">Period</span>
        <span class="cover-meta-value">{{ assessment.start_date }} — {{ assessment.end_date or "Ongoing" }}</span>
      </div>
      {% endif %}
      <div class="cover-meta-row">
        <span class="cover-meta-label">Status</span>
        <span class="cover-meta-value">{{ assessment.status or "Active" }}</span>
      </div>
      <div class="cover-meta-row">
        <span class="cover-meta-label">Generated</span>
        <span class="cover-meta-value">{{ generated_at }}</span>
      </div>
    </div>
    <div class="cover-footer">This document is confidential and intended solely for the named recipient. Generated by AIDA — AI-Driven Assessment.</div>
  </div>
</div>

<!-- ===================== TABLE OF CONTENTS ===================== -->
<div class="toc">
  <h2>Table of Contents</h2>
  <div class="toc-item"><a href="#exec-summary"><span class="toc-num">01</span> Executive Summary</a></div>
  {% if findings %}
  <div class="toc-item"><a href="#findings"><span class="toc-num">02</span> Findings ({{ total_findings }})</a></div>
  {% endif %}
  {% if observations %}
  <div class="toc-item"><a href="#observations"><span class="toc-num">03</span> Observations ({{ total_observations }})</a></div>
  {% endif %}
  {% if sections %}
  <div class="toc-item"><a href="#phases"><span class="toc-num">04</span> Assessment Phases</a></div>
  {% endif %}
  {% if recon %}
  <div class="toc-item"><a href="#recon"><span class="toc-num">05</span> Reconnaissance Data ({{ total_recon }})</a></div>
  {% endif %}
  {% if credentials %}
  <div class="toc-item"><a href="#credentials"><span class="toc-num">06</span> Discovered Credentials ({{ total_credentials }})</a></div>
  {% endif %}
  {% if info_cards %}
  <div class="toc-item"><a href="#info"><span class="toc-num">07</span> Additional Information</a></div>
  {% endif %}
</div>

<!-- ===================== EXECUTIVE SUMMARY ===================== -->
<h2 id="exec-summary"><span class="section-num">01</span> Executive Summary</h2>

<!-- overall risk -->
{% set risk_bg = {"CRITICAL":"linear-gradient(135deg,#881337,#e11d48)","HIGH":"linear-gradient(135deg,#9f1239,#f43f5e)","MEDIUM":"linear-gradient(135deg,#92400e,#f59e0b)","LOW":"linear-gradient(135deg,#1e3a8a,#3b82f6)","INFORMATIONAL":"linear-gradient(135deg,#334155,#64748b)"} %}
<div class="risk-banner" style="background:{{ risk_bg.get(risk_score, risk_bg['INFORMATIONAL']) }}">
  <div class="risk-label">Overall Risk Level</div>
  <div class="risk-level">{{ risk_score }}</div>
</div>

<!-- stat cards as table for WeasyPrint compatibility -->
<table class="stats-row" style="border:none;border-spacing:8px;">
  <tr style="border:none;">
    <td class="stat-card" style="border:1px solid #e2e8f0;">
      <div class="stat-num" style="color:var(--accent-critical)">{{ total_findings }}</div>
      <div class="stat-label">Findings</div>
    </td>
    <td class="stat-card" style="border:1px solid #e2e8f0;">
      <div class="stat-num" style="color:var(--primary)">{{ total_observations }}</div>
      <div class="stat-label">Observations</div>
    </td>
    <td class="stat-card" style="border:1px solid #e2e8f0;">
      <div class="stat-num" style="color:var(--accent-low)">{{ total_recon }}</div>
      <div class="stat-label">Recon Items</div>
    </td>
    <td class="stat-card" style="border:1px solid #e2e8f0;">
      <div class="stat-num" style="color:var(--accent-info)">{{ commands_count }}</div>
      <div class="stat-label">Commands Run</div>
    </td>
  </tr>
</table>

<!-- severity bar chart -->
{% if severity_counts %}
<h3>Findings by Severity</h3>
<div class="sev-chart">
  {% for sev in ["CRITICAL","HIGH","MEDIUM","LOW","INFO"] %}
  {% set cnt = severity_counts.get(sev, 0) %}
  {% if cnt > 0 %}
  <div class="sev-chart-row">
    <span class="sev-chart-label" style="color:{{ severity_colors[sev] }}">{{ sev }}</span>
    <span class="sev-chart-bar-bg">
      <span class="sev-chart-bar" style="width:{{ (cnt / max_sev_count * 100)|int }}%;background:{{ severity_colors[sev] }}"></span>
    </span>
    <span class="sev-chart-count">{{ cnt }}</span>
  </div>
  {% endif %}
  {% endfor %}
</div>
{% endif %}

{% if assessment.scope %}
<h3>Scope</h3>
<p>{{ assessment.scope }}</p>
{% endif %}

{% if assessment.target_domains %}
<h3>Target Domains</h3>
<p>{{ assessment.target_domains | join(", ") }}</p>
{% endif %}

{% if assessment.ip_scopes %}
<h3>IP Ranges</h3>
<p>{{ assessment.ip_scopes | join(", ") }}</p>
{% endif %}

{% if assessment.objectives %}
<h3>Objectives</h3>
<p>{{ assessment.objectives }}</p>
{% endif %}

{% if assessment.limitations %}
<h3>Limitations</h3>
<p>{{ assessment.limitations }}</p>
{% endif %}

<!-- ===================== FINDINGS ===================== -->
{% if findings %}
<div class="page-break"></div>
<h2 id="findings"><span class="section-num">02</span> Findings</h2>

{% for f in findings %}
<div class="finding">
  <div class="finding-header" style="background:{{ severity_colors.get(f.severity or 'INFO', '#64748b') }}">
    {{ f.severity or "INFO" }} — {{ f.title }}
    <span class="finding-id">#F-{{ loop.index }}</span>
  </div>
  <div class="finding-body">
    <div class="finding-meta">
      {% if f.target_service %}<span><strong>Target:</strong> {{ f.target_service }}</span>{% endif %}
      {% if f.status %}<span><strong>Status:</strong> {{ f.status }}</span>{% endif %}
      {% if f.cvss_score is not none %}
        <span><strong>CVSS 4.0:</strong>
          {% set cvss_color = "#e11d48" if f.cvss_score >= 9.0 else "#f43f5e" if f.cvss_score >= 7.0 else "#f59e0b" if f.cvss_score >= 4.0 else "#3b82f6" %}
          <span class="cvss-badge" style="background:{{ cvss_color }}">{{ f.cvss_score }}</span>
        </span>
        {% if f.cvss_vector %}<br><span class="text-muted">{{ f.cvss_vector }}</span>{% endif %}
      {% endif %}
    </div>

    {% if f.technical_analysis %}
    <div class="finding-field">
      <div class="field-label">Technical Analysis</div>
      <pre>{{ f.technical_analysis }}</pre>
    </div>
    {% endif %}

    {% if f.proof %}
    <div class="finding-field">
      <div class="field-label">Proof of Concept</div>
      <pre>{{ f.proof }}</pre>
    </div>
    {% endif %}

    {% if f.notes %}
    <div class="finding-field">
      <div class="field-label">Notes / Remediation</div>
      <pre>{{ f.notes }}</pre>
    </div>
    {% endif %}
  </div>
</div>
{% endfor %}
{% endif %}

<!-- ===================== OBSERVATIONS ===================== -->
{% if observations %}
<div class="page-break"></div>
<h2 id="observations"><span class="section-num">03</span> Observations</h2>

{% for o in observations %}
<div class="obs-card">
  <h4>{{ o.title }}</h4>
  {% if o.target_service %}<p><strong>Target:</strong> {{ o.target_service }}</p>{% endif %}
  {% if o.technical_analysis %}<pre>{{ o.technical_analysis }}</pre>{% endif %}
  {% if o.notes %}<p class="text-muted" style="margin-top:6px">{{ o.notes }}</p>{% endif %}
</div>
{% endfor %}
{% endif %}

<!-- ===================== PHASES ===================== -->
{% if sections %}
<div class="page-break"></div>
<h2 id="phases"><span class="section-num">04</span> Assessment Phases</h2>

{% for s in sections %}
<div class="phase-card">
  <div class="phase-header">{{ s.section_number }} — {{ s.title or s.section_type }}</div>
  <div class="phase-body">
    {% if s.content %}
    <pre>{{ s.content }}</pre>
    {% else %}
    <p class="text-muted">No content documented for this phase.</p>
    {% endif %}
  </div>
</div>
{% endfor %}
{% endif %}

<!-- ===================== RECON ===================== -->
{% if recon %}
<div class="page-break"></div>
<h2 id="recon"><span class="section-num">05</span> Reconnaissance Data</h2>

{% set recon_by_type = {} %}
{% for r in recon %}
  {% if r.data_type not in recon_by_type %}
    {% set _ = recon_by_type.update({r.data_type: []}) %}
  {% endif %}
  {% set _ = recon_by_type[r.data_type].append(r) %}
{% endfor %}

{% for dtype, items in recon_by_type.items() %}
<div class="recon-type-heading">{{ dtype | replace("_"," ") | title }} — {{ items|length }} item{{ "s" if items|length != 1 }}</div>
<table>
  <thead>
    <tr><th style="width:35%">Name</th><th>Details</th></tr>
  </thead>
  <tbody>
  {% for item in items[:50] %}
    <tr>
      <td style="font-weight:600">{{ item.name }}</td>
      <td class="text-muted">{{ item.details if item.details else "—" }}</td>
    </tr>
  {% endfor %}
  {% if items|length > 50 %}
    <tr><td colspan="2" class="text-muted" style="text-align:center">… and {{ items|length - 50 }} more entries</td></tr>
  {% endif %}
  </tbody>
</table>
{% endfor %}
{% endif %}

<!-- ===================== CREDENTIALS ===================== -->
{% if credentials %}
<div class="page-break"></div>
<h2 id="credentials"><span class="section-num">06</span> Discovered Credentials</h2>
<p class="text-muted" style="margin-bottom:10px">Sensitive values are masked in this report. Refer to the AIDA platform for full credential data.</p>

<table>
  <thead>
    <tr>
      <th>Name</th>
      <th>Type</th>
      <th>Service</th>
      <th>Target</th>
      <th>Discovered</th>
    </tr>
  </thead>
  <tbody>
  {% for c in credentials %}
    <tr>
      <td style="font-weight:600">{{ c.name }}</td>
      <td><span class="cred-type">{{ c.credential_type }}</span></td>
      <td>{{ c.service or "—" }}</td>
      <td>{{ c.target or "—" }}</td>
      <td>{{ c.discovered_by or "manual" }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}

<!-- ===================== INFO CARDS ===================== -->
{% if info_cards %}
<div class="page-break"></div>
<h2 id="info"><span class="section-num">07</span> Additional Information</h2>

{% for i in info_cards %}
<div class="info-card">
  <h4>{{ i.title }}</h4>
  {% if i.technical_analysis %}<pre>{{ i.technical_analysis }}</pre>{% endif %}
  {% if i.notes %}<p class="text-muted" style="margin-top:6px">{{ i.notes }}</p>{% endif %}
</div>
{% endfor %}
{% endif %}

</body>
</html>
''')
