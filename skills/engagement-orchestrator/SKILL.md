---
name: engagement-orchestrator
description: "Entry-point router for the authorized security-testing skill base. Given a target type or an engagement goal, it maps you to the right sequence of skills to load and in what order — from scoping to reporting — so you never miss a phase or a safety gate. Covers routing for: external web app, internal Active Directory / Windows network, API, cloud tenant (AWS/Azure/GCP), Kubernetes/containers & CI-CD supply chain, mobile app (Android/iOS), AI/LLM application, network services, wireless (Wi-Fi/BLE), ICS/SCADA/OT, a specific named CVE, and greenfield vulnerability research / 0-day. Also encodes the always-on flow (doctrine → methodology → recon → domain skills → reporting) and the safety gates that apply to each target. Use at the START of any engagement, when unsure which skill to load, or to assemble a multi-phase test plan across several skills."
version: 1.0.0
triggers:
  - where do I start
  - which skills for this engagement
  - build a test plan
  - orchestrate the engagement
  - engagement plan
  - what should I test
  - route by target type
  - assemble skill chain
  - i have a target
  - pentest plan
---

# Engagement Orchestrator

Start here. Tell me the **target type** or **goal**, and this skill routes you to
the right chain of skills, in order, with the safety gate for that target. It does
not replace the domain skills — it sequences them.

## Always-on spine (every engagement, in this order)

1. **`safe-testing-doctrine`** — pass the authorization gate + RoE checklist. Hard
   limits apply throughout: no DoS/DDoS, no destruction, no real-user impact,
   scope-only, least-intrusive PoC, cleanup. *(Never skip.)*
2. **`pentest-methodology`** — pick the phase model (NIST 800-115 / PTES) and the
   coverage checklist (OWASP WSTG/ASVS, MITRE ATT&CK).
3. **Recon** — `offensive-osint` + `osint-methodology` (external footprint / asset graph).
4. **Domain skills** — per the routing table below.
5. **`security-reporting`** — score (CVSS/EPSS/KEV) and write it up.

For any known-CVE that surfaces, branch to **`cve-knowledge-base`** (lookup/triage)
→ the deep skill (`web-cve-exploitation` / `windows-ad-cve-exploitation`).

## Routing table — target/goal → skill chain

| Target / goal | Load, in order (after doctrine + methodology) |
|---|---|
| **External web application** | `offensive-osint` → `web-vuln-hunting` → (if known product/CVE) `cve-knowledge-base` → `web-cve-exploitation` → `security-reporting` |
| **API (REST/GraphQL/gRPC)** | `offensive-osint` → `api-security-testing` (+ `web-vuln-hunting` for payload mechanics) → `security-reporting` |
| **Internal network / Active Directory** | `active-directory-attack-paths` (BloodHound-driven) → `windows-ad-cve-exploitation` (named CVEs) → `network-service-exploitation` (services) → `security-reporting` |
| **A specific Windows/AD CVE** | `cve-knowledge-base` (triage) → `windows-ad-cve-exploitation` → `security-reporting` |
| **Cloud tenant (AWS/Azure/GCP)** | `offensive-osint` → `cloud-security-testing` → (K8s? ) `container-supply-chain-security` → `security-reporting` |
| **Kubernetes / containers / CI-CD / supply chain** | `container-supply-chain-security` (+ `cloud-security-testing` for managed K8s/IAM) → `security-reporting` |
| **Mobile app (Android/iOS)** | `mobile-app-security` (+ `api-security-testing` for its backend) → `security-reporting` |
| **AI / LLM application** | `ai-llm-security` (+ `web-vuln-hunting`/`api-security-testing` for output-handling sinks) → `security-reporting` |
| **Network services (SMB/RDP/SNMP/DB…)** | `network-service-exploitation` → (named CVE?) `cve-knowledge-base` → `security-reporting` |
| **Wireless (Wi-Fi / BLE / RFID)** | `wireless-security` → `security-reporting` |
| **ICS / SCADA / OT** | `ics-scada-security` (PASSIVE-FIRST) → `security-reporting` |
| **Look up / triage any CVE** | `cve-knowledge-base` → deep skill by category |
| **Find a novel bug / 0-day** | `vulnerability-research-zeroday` (lab-only) → coordinated disclosure → `security-reporting` |
| **Single-host privilege escalation** | `privilege-escalation` → (creds found?) `password-cracking-credentials` → `security-reporting` |
| **Post-foothold: pivot / lateral / C2** | `post-exploitation-pivoting` (+ `active-directory-attack-paths` for AD, `privilege-escalation` for host) → `security-reporting` |
| **Cracking collected hashes** | `password-cracking-credentials` |
| **Deserialization suspected** | `deserialization-attacks` (+ `web-cve-exploitation` for JNDI/Log4Shell) → `security-reporting` |
| **White-box code / SAST audit** | `secure-code-review-sast` (+ `deserialization-attacks`, `web-vuln-hunting` per finding) → `security-reporting` |
| **Phishing / social-engineering (separate SOW)** | `social-engineering-phishing` (+ `offensive-osint` for targets) → `security-reporting` |
| **Build detections / purple team** | `detection-engineering-purple` (maps the offensive skills' techniques → detections) |
| **Map findings to a compliance framework** | `compliance-mapping` → `security-reporting` |

## Per-target safety gate (the extra rule that bites for that target)

- **Web / API** — no DoS payloads; prove IDOR with 1–2 objects; rate-limit tests
  are a *small* sample, never a flood; no destructive SQL.
- **Active Directory** — spraying respects lockout policy; poisoning/relay/coercion
  need explicit RoE + coordination; clean up tickets/ACLs/accounts; Zerologon needs
  the restore step.
- **Cloud** — read-only Describe/List/Get; discovered creds → identity-check only,
  then stop; no resource deletion.
- **Containers/K8s/CI-CD** — read-only scanning; container-escape & node-impacting
  PoCs are lab/RoE-only; don't push malicious images or poison real feeds.
- **Mobile** — instrument your own test device with test accounts; don't distribute
  modified/cracked builds.
- **AI/LLM** — benign canary probes to show control gaps; no real harmful-content
  generation; no prod data/model poisoning; consumption tests probe *for a limit*,
  never flood.
- **Network services** — memory-corruption RCEs (EternalBlue/BlueKeep/SMBGhost/
  regreSSHion) are DETECT-ONLY unless RoE + non-prod.
- **Wireless** — **no deauth / no jamming (that's a DoS)**; capture handshakes
  passively or via PMKID; only authorized SSIDs; crack offline.
- **ICS/SCADA/OT** — **PASSIVE-FIRST**; no active scan/write to live equipment
  without OT-owner approval + engineer supervision + maintenance window; never
  touch Safety Instrumented Systems; disruption here is a *safety* hazard.
- **0-day research** — fuzzing/crash-testing lab-only on systems you own; no
  weaponization; coordinated disclosure.
- **Host privesc** — kernel exploits can crash the host → DETECT-ONLY / lab-or-RoE-only;
  prove escalation minimally (`id`/`whoami`), no persistence, clean up.
- **Post-ex / pivoting / C2** — contracted red-team only; no persistence left behind;
  no pivot to out-of-scope/third-party nets; deconflict; remove every implant/tunnel/
  account and hand over an artifact list.
- **Password cracking** — crack only lawfully-obtained in-scope hashes, OFFLINE; never
  online-brute live services (lockout-DoS); handle cracked creds as sensitive, then delete.
- **Social engineering** — SEPARATE explicit written authorization (default-forbidden);
  client's own employees only; no real financial loss / no reusable real creds; immediate
  awareness redirect; measurement & training, not exploitation.

## How to use

1. State the target type / goal.
2. Load the spine (doctrine + methodology), then the chain from the routing table.
3. Apply the per-target safety gate above (in addition to the doctrine).
4. Converge on findings → `security-reporting`.

Full base map and provenance: `00-security-testing-index`.
