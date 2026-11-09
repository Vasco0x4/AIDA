# Frameworks Overview & Pentest Relevance

Each framework below: what it is, who must comply, its structure/version, and the
**specific hooks a pentester maps findings to**. Confirm the exact version in
scope with the client and cite it in the report. See `sources.md` for links.

---

## 1. PCI DSS v4.0 / v4.0.1 (Payment Card Industry Data Security Standard)

- **What it is:** A contractual security standard from the PCI Security Standards
  Council (Visa/Mastercard/Amex/Discover/JCB). Not a law, but enforced through
  card-brand and acquirer contracts; non-compliance -> fines, higher fees, or loss
  of card processing.
- **Who needs it:** Any entity that stores, processes, or transmits cardholder
  data (PAN) or can affect its security — merchants and service providers. Level
  determined by transaction volume; validated via SAQ or a QSA Report on
  Compliance (RoC).
- **Structure:** 12 requirements grouped in 6 goals, each with numbered
  sub-requirements and defined testing procedures. v4.0 (effective; v4.0.1 is the
  minor errata release that superseded 4.0) added *customized approach*,
  targeted risk analyses, and many "future-dated" requirements that became
  mandatory 31 Mar 2025. The core CDE concept: the **Cardholder Data Environment**
  is the assessment scope; segmentation reduces it.
- **The 12 requirements (short):** 1 network security controls (firewalls),
  2 secure configurations, 3 protect stored account data, 4 protect data in
  transit (strong crypto), 5 anti-malware, 6 secure systems & software (dev,
  patching, WAF), 7 restrict access by need-to-know, 8 identify & authenticate
  (MFA), 9 physical access, 10 log & monitor all access, 11 test security
  regularly (scans + **pentest 11.4** + segmentation), 12 security policy /
  program governance.
- **Pentest relevance (primary hooks):**
  - **Req 11.4** — the penetration-testing requirement: internal + external
    pentest at least annually and after significant change; segmentation testing
    (11.4.5 all entities annually; 11.4.6 service providers every 6 months);
    application-layer test covering Req 6.2.4 vuln classes.
  - **Req 11.3** — internal & external vulnerability scans (ASV quarterly external).
  - **Req 6.2.4 / 6.4.1-6.4.2** — application vulnerabilities (injection, XSS,
    access control, insecure deserialization, etc.) and public-facing web app
    protection (review or WAF).
  - Findings also commonly map to Req 2 (config), 3/4 (crypto), 7/8 (access/MFA),
    10 (logging).
  - Details of the 11.4 mandate are in `pentest-requirements-by-framework.md`.

---

## 2. HIPAA Security Rule (45 CFR Part 164, Subpart C)

- **What it is:** US federal law (HITECH-amended) enforced by HHS Office for Civil
  Rights (OCR). Sets the security standards for **electronic protected health
  information (ePHI)**. (The Privacy Rule and Breach Notification Rule are
  separate but related subparts.)
- **Who needs it:** Covered entities (health plans, clearinghouses, most
  providers) and their Business Associates (vendors handling ePHI), bound via
  Business Associate Agreements (BAAs).
- **Structure:** Standards + "implementation specifications" that are either
  *Required* or *Addressable* (addressable still must be implemented or the
  decision documented). Three safeguard groups:
  - **Administrative safeguards §164.308** — the largest: **risk analysis**
    §164.308(a)(1)(ii)(A), risk management, sanction policy, information system
    activity review, workforce security, contingency plan, **evaluation**
    §164.308(a)(8) (periodic technical/non-technical evaluation — the hook for a
    pentest), incident procedures §164.308(a)(6).
  - **Physical safeguards §164.310** — facility access, workstation & device
    controls, media disposal.
  - **Technical safeguards §164.312** — **access control §164.312(a)** (incl.
    unique user ID, encryption/decryption addressable), **audit controls
    §164.312(b)**, **integrity §164.312(c)**, **person/entity authentication
    §164.312(d)** (the MFA/auth hook), **transmission security §164.312(e)**
    (encryption in transit).
- **Pentest relevance:** HIPAA does not explicitly mandate a pentest, but the
  **risk analysis (§164.308(a)(1)(ii)(A))** and **periodic evaluation
  (§164.308(a)(8))** are the accepted hooks — a pentest is evidence supporting
  both. Findings map cleanly to §164.312 technical safeguards. **Breach
  Notification Rule (§164.400-414):** breaches of unsecured PHI -> notify
  individuals & HHS without unreasonable delay and no later than **60 days**;
  500+ affected -> notify HHS and media promptly. Note this exposure for PHI
  findings.

---

## 3. SOC 2 (AICPA System and Organization Controls 2 / Trust Services Criteria)

- **What it is:** An attestation *report* (not a certification) issued by a
  licensed CPA firm under AICPA standards, evaluating a service organization's
  controls against the **Trust Services Criteria (TSC)**. **Type I** = design at a
  point in time; **Type II** = operating effectiveness over a period (typically
  3-12 months) — enterprise buyers usually require Type II.
- **Who needs it:** Service organizations (SaaS, cloud, MSPs, data processors)
  whose customers demand assurance — a de-facto sales requirement for B2B SaaS.
- **Structure:** Five TSC categories. **Security (the "Common Criteria")** is
  mandatory; the other four are optional based on customer commitments:
  - **Security / Common Criteria CC1-CC9:** CC1 control environment, CC2
    communication & information, CC3 risk assessment, CC4 monitoring activities,
    CC5 control activities, **CC6 logical & physical access controls**, **CC7
    system operations (incl. vuln detection & incident response)**, CC8 change
    management, CC9 risk mitigation. (The CC series reuses COSO + adds tech
    controls.)
  - **Availability (A)**, **Confidentiality (C)**, **Processing Integrity (PI)**,
    **Privacy (P)** — added when in scope.
- **Pentest relevance:** SOC 2 does not name "penetration test" as a criterion,
  but auditors routinely expect one as evidence for:
  - **CC4.1** monitoring of controls, **CC7.1** detect/monitor for vulnerabilities
    and config changes (vuln scanning + pentest), **CC7.2-7.5** incident detection
    & response, **CC3.2** risk identification.
  - **CC6.1/6.6/6.7** logical access, boundary protection, encryption in transit
    — where most access-control/crypto findings land.
  - **CC8.1** change management for config/patching findings.

---

## 4. ISO/IEC 27001:2022 (Information Security Management System)

- **What it is:** The international standard for an **ISMS**; organizations get
  *certified* by an accredited body after a Stage 1/Stage 2 audit and surveillance
  audits. The management-system clauses (4-10) are the certifiable requirements;
  **Annex A** is the control catalog (drawn from ISO/IEC 27002:2022).
- **Who needs it:** Any org wanting a recognized, auditable security certification
  — common for global enterprise, B2B, and as a SOC 2 alternative/complement.
- **Structure:** Clauses **4-10** (context, leadership, planning incl. risk
  assessment/treatment, support, operation, performance evaluation, improvement) +
  a mandatory **Statement of Applicability (SoA)** justifying each Annex A control.
  **Annex A:2022 = 93 controls in 4 themes** (down from 114/14 domains in 2013):
  - **A.5 Organizational (37 controls, 5.1-5.37)** — policies, roles, supplier
    security, threat intel (A.5.7), access control policy (A.5.15), incident mgmt
    (A.5.24-5.28).
  - **A.6 People (8, 6.1-6.8)** — screening, awareness, disciplinary.
  - **A.7 Physical (14, 7.1-7.14)** — facilities, equipment, media.
  - **A.8 Technological (34, 8.1-8.34)** — where most pentest findings map:
    A.8.2 privileged access, A.8.3 information access restriction, **A.8.5 secure
    authentication (MFA)**, A.8.8 **management of technical vulnerabilities**,
    A.8.9 config mgmt, A.8.12 data leakage prevention, A.8.15 logging, A.8.16
    monitoring, A.8.20-8.23 network/web security, A.8.24 cryptography, A.8.25-8.28
    secure development, **A.8.29 security testing in development & acceptance**.
- **Pentest relevance:** **A.8.8** (technical vulnerability management) and
  **A.8.29** (security testing) are the direct hooks; clause **9.2** internal
  audit and **6.1.2** risk assessment consume pentest output. Findings are written
  as *nonconformities* (major/minor) against specific Annex A controls or clauses.

---

## 5. NIST Cybersecurity Framework (CSF) 2.0

- **What it is:** A voluntary, outcome-based framework (NIST, v2.0 released
  **Feb 2024**). Widely adopted in the US and beyond as a common risk-management
  language; not a control catalog or certification.
- **Who needs it:** Any organization wanting a risk-based posture model; often
  used to organize a program that is implemented with 800-53 or CIS controls.
- **Structure:** **6 Functions** (2.0 added **Govern**): **GV Govern** (new — risk
  strategy, roles, policy, supply chain, oversight, sits at the center),
  **ID Identify**, **PR Protect**, **DE Detect**, **RS Respond**, **RC Recover** —
  each broken into Categories and Subcategories (e.g. ID.RA risk assessment,
  PR.AA identity/authentication/access control, PR.PS platform security, DE.CM
  continuous monitoring, RS.MA/RS.AN response, RC.RP recovery). Uses Tiers and
  Profiles to describe maturity/target state.
- **Pentest relevance:** Maps naturally — **ID.RA** (risk assessment / vuln
  identification) and **ID.RA-01/-05** consume pentest results; **PR.AA**
  (authentication/access, MFA), **PR.PS/PR.IR** (platform/infra protection,
  patching), **DE.CM** (monitoring/detection), **RS/RC** (incident response &
  recovery). CSF Subcategories cross-reference 800-53 and CIS via NIST's
  Informative References.

---

## 6. NIST SP 800-53 Rev.5 (Security & Privacy Controls)

- **What it is:** The comprehensive US federal control catalog. Mandatory for
  federal information systems under FISMA and the basis for **FedRAMP** (cloud)
  via defined baselines (Low/Moderate/High, selected with 800-53B). Also widely
  used privately as a deep control reference.
- **Who needs it:** US federal agencies, contractors, FedRAMP cloud providers, and
  anyone wanting a rigorous control set.
- **Structure:** **20 control families** (Rev.5 added Supply Chain Risk Mgmt SR and
  merged privacy). Key families for pentesters: **AC** access control, **AU**
  audit & accountability (logging), **CA** assessment/authorization (incl.
  **CA-8 penetration testing**), **CM** configuration mgmt, **IA** identification
  & authentication (**IA-2(1)/(2)** MFA), **RA** risk assessment (**RA-5**
  vulnerability monitoring/scanning), **SC** system & communications protection
  (crypto SC-8/SC-13, boundary SC-7), **SI** system & information integrity
  (**SI-2** flaw remediation/patching, SI-4 monitoring), IR incident response.
- **Pentest relevance:** **CA-8** is the explicit penetration-testing control;
  **RA-5** vuln scanning; findings map to the family for their weakness class
  (AC/IA for access & MFA, SC for crypto, SI-2 for patching, AU for logging).

---

## 7. GDPR (EU General Data Protection Regulation, 2016/679)

- **What it is:** EU regulation with the force of law; enforced by national Data
  Protection Authorities. Fines up to **€20M or 4% of global annual turnover**.
- **Who needs it:** Any organization (anywhere) processing personal data of people
  in the EU/EEA — controllers and processors.
- **Structure:** 99 Articles. Security-relevant articles for pentest mapping:
  - **Art. 5** principles (incl. integrity & confidentiality); **Art. 25** data
    protection by design & by default; **Art. 24/28** controller/processor
    obligations.
  - **Art. 32 Security of processing** — the core technical/organizational
    measures article: pseudonymization & **encryption** (32(1)(a)); ongoing
    **confidentiality, integrity, availability, resilience** (32(1)(b)); ability
    to restore availability (32(1)(c)); a **process for regularly testing,
    assessing and evaluating** effectiveness (32(1)(d)) — *this is the explicit
    hook that supports pentesting/vuln assessment.*
  - **Art. 33 Breach notification to the supervisory authority** — without undue
    delay, where feasible **within 72 hours** of becoming aware, unless unlikely
    to result in risk to rights and freedoms.
  - **Art. 34 Communication to the data subject** — when the breach is likely to
    result in **high risk** to individuals, notify them without undue delay
    (unless data was encrypted/otherwise unintelligible or risk mitigated).
- **Pentest relevance:** Findings that expose personal data (IDOR/BOLA leaking
  PII, missing encryption, SQLi, broken access control) map to **Art. 32** as
  inadequate technical measures, and raise **Art. 33/34** breach-notification
  exposure if exploited. State this exposure explicitly for PII findings — it is
  the regulator/fine angle management reacts to.

---

## 8. CIS Controls v8.1 (Center for Internet Security Critical Security Controls)

- **What it is:** A prioritized, community-maintained set of defensive actions —
  a "what to do first" hygiene baseline. Free; not a certification, but maps to
  PCI, HIPAA, ISO, NIST CSF/800-53 via the CIS mappings, making it a useful
  Rosetta Stone. v8.1 aligns with CSF 2.0 (adds a "Govern" security function).
- **Who needs it:** Any organization wanting an actionable prioritized starting
  point; often used by SMBs and as the practical layer under a CSF program.
- **Structure:** **18 Controls, 153 Safeguards**, tiered into three
  **Implementation Groups**: **IG1** (56 safeguards — "essential cyber hygiene",
  every org), **IG2** (adds up to 130, moderate complexity/regulated), **IG3**
  (all 153, high-threat). Controls: 1 inventory of enterprise assets, 2 inventory
  of software, 3 data protection, 4 **secure configuration**, 5 account mgmt,
  6 **access control mgmt (incl. MFA 6.3/6.5)**, 7 **continuous vulnerability
  management**, 8 audit log management, 9 email/web browser protections,
  10 malware defenses, 11 data recovery, 12 network infrastructure mgmt,
  13 network monitoring & defense, 14 security awareness, 15 service provider
  mgmt, 16 application software security, 17 incident response mgmt, **18
  penetration testing**.
- **Pentest relevance:** **Control 18** is the explicit penetration-testing
  control (internal & external, scope, remediation of findings); **Control 7**
  vuln management; findings map to 4 (config), 5/6 (accounts/access/MFA), 8
  (logging), 16 (app security).
