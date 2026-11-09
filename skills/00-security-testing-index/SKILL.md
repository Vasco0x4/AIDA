---
name: security-testing-index
description: "Master index and navigation map for the authorized security-testing skill base. Lists every skill (governance, methodology, web, API, Active Directory/Windows, cloud, network services, CVE-exploitation, recon, reporting), what each covers, when to load it, how they reference each other, and the public provenance of the material (HackerOne/bug-bounty disclosures, CISA KEV, NVD/CVE, vendor advisories, OWASP WSTG/ASVS/Top 10, NIST SP 800-115, MITRE ATT&CK, PTES). Start here to pick the right skill for an authorized pentest/audit task, understand the safety model, or see where the content comes from."
version: 1.0.0
triggers:
  - security testing index
  - which skill
  - skill base map
  - pentest skills
  - security audit skills
  - where do I start
  - list security skills
---

# Security Testing Skill Base — Master Index

A curated set of skills for **authorized** penetration testing, security audit,
and in-scope bug-bounty work. All content is built for legal, contracted, and
scoped engagements, grounded in public sources, and bounded by a mandatory
safety doctrine.

## ⚠️ Everything here inherits `safe-testing-doctrine`

Before any active test, load **`safe-testing-doctrine`**. Hard limits, always:
**no DoS/DDoS, no destruction or modification of data/config, no impact on real
users or their data, scope-only, least-intrusive proof-of-concept, full
cleanup.** If a technique conflicts with the doctrine, the doctrine wins.

## How the base is organized

```
00-security-testing-index/     ← you are here (map + provenance)
engagement-orchestrator/       ← START HERE: routes target type → skill chain
safe-testing-doctrine/         ← MANDATORY safety & rules of engagement
pentest-methodology/           ← phases, standards map (NIST/PTES/OWASP/MITRE)
security-reporting/            ← CVSS/EPSS/KEV, report & submission templates

── Recon ──────────────────────────────
offensive-osint/               ← operational recon arsenal (pre-existing)
osint-methodology/             ← recon methodology (pre-existing)

── Web & API ──────────────────────────
web-vuln-hunting/              ← web vuln classes (IDOR/SSRF/XSS/injection/auth/logic…)
web-cve-exploitation/          ← notable real-world web CVEs (KEV-grounded)
api-security-testing/          ← OWASP API Security Top 10 (REST/GraphQL/gRPC)

── Windows / Active Directory ─────────
active-directory-attack-paths/ ← internal AD kill chain (recon→DA)
windows-ad-cve-exploitation/   ← notable Windows/AD/Exchange CVEs

── Cloud & Network ────────────────────
cloud-security-testing/        ← AWS/Azure-Entra/GCP/Kubernetes misconfig
network-service-exploitation/  ← common services + notable CVEs (many DETECT-ONLY)

── Mobile & AI ────────────────────────
mobile-app-security/           ← Android/iOS, Frida, OWASP MASVS/MASTG
ai-llm-security/               ← OWASP LLM Top 10 (2025), prompt injection, agentic

── Containers / Supply chain ──────────
container-supply-chain-security/← Docker/K8s deep, CI-CD (PPE), dependency confusion, SBOM/SLSA

── Wireless & OT ──────────────────────
wireless-security/             ← Wi-Fi (WPA2/3, PMKID), BLE, RFID/NFC — no-deauth
ics-scada-security/            ← ICS/SCADA/OT — PASSIVE-FIRST, safety-critical

── Host & post-exploitation ───────────
privilege-escalation/          ← Linux/Windows local privesc (host-level, → root/SYSTEM)
post-exploitation-pivoting/    ← pivoting/tunneling + C2 (contracted red-team, cleanup)
password-cracking-credentials/ ← hashcat/john offline cracking layer for all hashes

── Code & app-layer depth ─────────────
deserialization-attacks/       ← cross-language deser RCE (ysoserial/phpggc/pickle/ViewState)
secure-code-review-sast/       ← white-box code audit + Semgrep/CodeQL + STRIDE

── Social engineering ─────────────────
social-engineering-phishing/   ← phishing SIMULATION — separate SOW, explicit SE authorization

── Defensive / purple ─────────────────
detection-engineering-purple/  ← Sigma/Atomic/Caldera; detections for this base's attacks
compliance-mapping/            ← findings → PCI/HIPAA/SOC2/ISO27001/NIST/GDPR/CIS

── CVE freshness & research ───────────
cve-knowledge-base/            ← prioritized 2025-26 KEV catalog + any-CVE lookup method
vulnerability-research-zeroday/← 0-day discovery (fuzzing/audit/RE) + coordinated disclosure
```

## Pick-a-skill guide

| Your task | Load |
|---|---|
| Not sure where to start / build a multi-skill test plan | `engagement-orchestrator` |
| Confirm what I'm allowed to do | `safe-testing-doctrine` |
| Plan the engagement / decide next step / ensure coverage | `pentest-methodology` |
| Map the external attack surface | `offensive-osint`, `osint-methodology` |
| Test a web app for a vuln class | `web-vuln-hunting` |
| Exploit/detect a known web CVE (Log4Shell, Citrix Bleed, MOVEit…) | `web-cve-exploitation` |
| Test an API against OWASP API Top 10 | `api-security-testing` |
| Escalate from AD foothold to Domain Admin | `active-directory-attack-paths` |
| Exploit/detect a Windows/AD CVE (Zerologon, PrintNightmare, ProxyShell…) | `windows-ad-cve-exploitation` |
| Assess a cloud tenant (AWS/Azure/GCP/K8s) | `cloud-security-testing` |
| Enumerate/exploit a network service (SMB/RDP/SNMP/Redis…) | `network-service-exploitation` |
| Test a mobile app (Android/iOS, Frida, pinning bypass) | `mobile-app-security` |
| Test an AI/LLM app (prompt injection, agentic, RAG) | `ai-llm-security` |
| Test containers/K8s deep, CI-CD pipeline, or software supply chain | `container-supply-chain-security` |
| Assess wireless (Wi-Fi/BLE/RFID) | `wireless-security` |
| Assess ICS/SCADA/OT (passive-first, safety-critical) | `ics-scada-security` |
| Escalate a single host from user to root/SYSTEM | `privilege-escalation` |
| Pivot/tunnel into segmented networks, run C2 (contracted red-team) | `post-exploitation-pivoting` |
| Crack collected hashes (Kerberoast/NTDS/WPA/JWT/…) offline | `password-cracking-credentials` |
| Test insecure deserialization (Java/.NET/PHP/Python/…) | `deserialization-attacks` |
| Review source code (white-box) / write SAST rules | `secure-code-review-sast` |
| Run an authorized phishing/social-engineering simulation (separate SOW) | `social-engineering-phishing` |
| Build detections / run a purple-team exercise | `detection-engineering-purple` |
| Map findings to PCI/HIPAA/SOC2/ISO/NIST/GDPR | `compliance-mapping` |
| Look up / triage any CVE, or find the latest 2025-26 exploited CVEs | `cve-knowledge-base` |
| Hunt for a previously-unknown (0-day) bug and disclose it responsibly | `vulnerability-research-zeroday` |
| Score findings and write the report | `security-reporting` |

## Typical engagement flow (which skills, in order)

1. **Scope & RoE** → `safe-testing-doctrine` (+ roe-checklist).
2. **Plan** → `pentest-methodology`.
3. **Recon** → `offensive-osint` / `osint-methodology`.
4. **Analyze & attack** → the domain skills (web/API/AD/cloud/network + CVE skills),
   always with the least-intrusive PoC from `safe-testing-doctrine/references/safe-poc-patterns.md`.
5. **Report** → `security-reporting`.

## Provenance — where the material comes from

This base is a synthesis of **public, reputable** security knowledge, not private
or proprietary exploit code. Primary source categories:

- **Disclosed vulnerability reports** — HackerOne Hacktivity, Bugcrowd, Intigriti
  public disclosures (patterns, not verbatim private data).
- **Authoritative CVE/exploit data** — NVD/CVE, **CISA Known Exploited
  Vulnerabilities (KEV)** catalog, **EPSS**, vendor security advisories (MSRC,
  Citrix, Ivanti, Fortinet, Atlassian, etc.), ExploitDB, Metasploit modules.
- **Standards & frameworks** — OWASP (WSTG, ASVS, Top 10, API Security Top 10,
  risk rating), **NIST SP 800-115**, **PTES**, **MITRE ATT&CK**, CWE, CIS Benchmarks.
- **Established research & tooling docs** — PortSwigger Research, SpecterOps /
  BloodHound / Certipy, dirkjanm.io, Impacket / NetExec docs, tool documentation.

Each CVE/cloud/network/API/reporting skill includes a `references/sources.md`
listing the specific public URLs consulted when it was written. Verify version
numbers and advisories against the vendor before using any technique on a target.

## Standards alignment (auditor view)
- Methodology → NIST SP 800-115 phases, PTES stages.
- Web/API coverage → OWASP WSTG test cases, ASVS levels, OWASP Top 10 / API Top 10.
- Internal/post-ex → MITRE ATT&CK techniques.
- Scoring → CVSS v3.1/4.0 + EPSS + CISA KEV.
- Safety/legal → authorization-first, CFAA/CMA-aware (`safe-testing-doctrine`).
