---
name: ics-scada-security
description: "Authorized, PASSIVE-FIRST security assessment of ICS/SCADA/OT (operational technology) environments — the domain where an active scan or a single malformed packet can disrupt a physical process and endanger human safety. Covers the Purdue Enterprise Reference Architecture (levels 0-5), the IT/OT boundary and IDMZ, Safety Instrumented Systems (SIS — never touched), passive asset discovery FIRST (network TAP/SPAN, Wireshark ICS dissectors, GRASSMARLIN, passive inventory), ICS/OT protocol awareness (Modbus/TCP 502, DNP3 20000, Siemens S7comm 102, EtherNet/IP CIP 44818/2222, BACnet 47808, OPC-UA 4840, IEC-104 2404, PROFINET, IEC 61850) — what each exposes, why they lack authentication, and why WRITE/control functions are forbidden on live equipment because they move physical plant. Covers external-exposure OSINT (Shodan/Censys ICS dorks, report-only, never interact with third-party OT), common ICS vulnerabilities (default HMI/PLC creds, unauthenticated protocols, known CISA-advisory CVEs, flat/unsegmented networks), and the STRICT rules for any active testing (explicit written OT-owner approval + engineer supervision + maintenance window + rollback). Grounded in NIST SP 800-82r3, IEC 62443, MITRE ATT&CK for ICS, and CISA ICS advisories. SAFETY-CRITICAL: a disruption here can be a physical-safety hazard, not just downtime — when in doubt, STOP. Use for ics/scada/ot security assessment, passive OT asset discovery, ICS protocol analysis, OT exposure reporting, or writing OT findings with IEC 62443 remediation."
version: 1.0.0
triggers:
  - ics security
  - scada
  - scada security
  - ot security
  - operational technology
  - ot pentest
  - ot assessment
  - industrial control system
  - modbus
  - dnp3
  - s7comm
  - siemens s7
  - ethernet/ip
  - cip
  - bacnet
  - opc-ua
  - iec-104
  - iec 61850
  - profinet
  - plc
  - hmi
  - rtu
  - purdue model
  - iec 62443
  - nist 800-82
  - attack for ics
  - safety instrumented system
  - sis
  - passive asset discovery
  - grassmarlin
  - network tap
  - span port
  - cisa ics advisory
---

# ICS / SCADA / OT Security (Authorized, Passive-First Assessment)

Operational playbook for assessing **operational technology** — the control systems
that run physical processes: PLCs, RTUs, HMIs, DCS controllers, historians,
engineering workstations, and the field instruments they command. This is **not** an
IT network. The devices are fragile, often decades old, run deterministic real-time
loops, and were built with **no authentication and no tolerance for unexpected
traffic**. A port scan that an IT server shrugs off can hang a PLC; a single
malformed or out-of-spec packet has crashed controllers and dropped production.

Because those controllers drive pumps, valves, breakers, turbines, and burners, a
disruption is not "downtime" — it can be a **safety incident**: overpressure, fire,
flood, equipment destruction, or injury. Therefore this skill is **passive-first,
do-no-harm, and safety-forward above everything else**. The default posture is to
*listen*, not to *probe*.

Grounding: **NIST SP 800-82r3** (Guide to OT Security), **IEC 62443**, **MITRE
ATT&CK for ICS**, and **CISA ICS advisories / recommended practices**.

---

## ⚠️ Safety — READ FIRST (inherits `safe-testing-doctrine`, then adds OT hard rules)

Load **`safe-testing-doctrine`** before anything. Everything there applies. OT adds
its own **non-negotiable** rules on top, because here a mistake can hurt people, not
just data. If any rule below conflicts with a request, **the rule wins — STOP and
escalate to the operator and the OT owner.**

**The OT hard rules:**

1. **PASSIVE-FIRST, ALWAYS.** The primary method is passive: mirror/tap the traffic
   and analyze it offline. You do not send packets to live control equipment as a
   default. Passive discovery answers the vast majority of assessment questions with
   **zero risk** to the process. Start there and stay there unless explicitly
   authorized otherwise.

2. **NO active scanning / nmap / fuzzing of live OT** without **ALL** of:
   explicit **written OT-owner approval** naming the exact assets, an **on-site
   control engineer supervising**, a **scheduled maintenance window / planned
   downtime** (or a lab / test rig), and a **rollback / restart plan**. Active scans
   and even benign version probes **have crashed PLCs and RTUs**. Assume any active
   traffic can trip the process until proven otherwise on that specific device.

3. **NEVER issue write / control / configuration commands to live equipment.**
   No `write coil`, no `write register`, no CIP set-attribute, no S7 write/stop/start,
   no DNP3 operate/direct-operate, no firmware or logic download. A write can
   **physically move plant** — open a valve, trip a breaker, change a setpoint — and
   cause damage or a safety event. Enumeration/read functions are also restricted on
   live gear (see rule 2); **writes are forbidden outright** on anything in service.

4. **NEVER touch Safety Instrumented Systems (SIS).** SIS / safety PLCs / emergency
   shutdown (ESD) / burner-management systems are the last line protecting people and
   plant. They are **out of scope by default and off-limits** — no scanning, no
   probing, no traffic, nothing. Interfering with a safety function can directly
   endanger life. If SIS is somehow in scope, it requires its own separate, explicit,
   engineer-led authorization — and even then, passive-only.

5. **Do NOT interact with third-party / internet-exposed OT you discover.** External
   OSINT (Shodan/Censys) will surface real, live, internet-facing control systems
   belonging to other organizations. **Report the exposure; never connect, never
   query, never authenticate.** Interacting with someone else's live OT is both
   dangerous and likely a crime. Passive OSINT observation only.

6. **When in doubt, STOP.** There is no finding worth a physical-safety incident.
   Uncertainty about whether an action is safe on OT is itself a stop condition.
   Escalate to the OT owner / control engineer before proceeding. "I'll just try it"
   does not exist in OT.

**Stop conditions (halt immediately, notify the OT owner):** any device becomes
unresponsive or reboots, any HMI alarm or process deviation appears, any protective
trip occurs, you observe you are on a network segment carrying SIS traffic, or you
are unsure whether the next action is safe.

---

## The assessment posture in one line

> **Listen first. Map from what you hear. Touch nothing that runs the process.
> Reserve any active action for an approved, supervised window on non-safety gear —
> and never write.**

---

## Method overview (safe order of operations)

1. **Scoping & authorization (`references/methodology-and-purdue.md`)** — establish
   the Purdue-level scope, confirm SIS exclusion, agree the IT/OT boundary, and lock
   in that Phase 1 is passive-only. Get emergency contacts and the stop procedure.
2. **Passive discovery (`references/methodology-and-purdue.md`)** — deploy a TAP or
   configure a SPAN/mirror port; capture with Wireshark ICS dissectors and/or
   GRASSMARLIN; build a passive asset inventory and network map. This is the core of
   the engagement.
3. **Protocol analysis (`references/protocols.md`)** — from the passive capture,
   identify protocols, devices, function codes seen, and what data is exposed;
   understand why the protocol is unauthenticated and why writes are forbidden.
4. **External exposure (`references/exposure-and-cves.md`)** — passive OSINT via
   Shodan/Censys to find the client's own internet-exposed OT; report-only.
5. **Vulnerability & architecture findings (`references/exposure-and-cves.md`)** —
   default creds (documented, not exploited on live gear), unauthenticated protocols,
   known CISA-advisory CVEs by fingerprint, flat-network / no-segmentation findings.
6. **Active testing — only if separately authorized (`references/methodology-and-purdue.md`)**
   — the strict maintenance-window / engineer-supervised / non-SIS / read-only-if-at-all
   procedure. Most OT assessments never reach this step, and that is correct.

## Reference index

| Area | Load this file |
|------|----------------|
| Purdue model (0-5), IT/OT boundary & IDMZ, SIS, passive-first methodology, framework mapping (NIST 800-82 / IEC 62443 / ATT&CK-ICS), the strict active-testing gate | `references/methodology-and-purdue.md` |
| Per-protocol reference — Modbus, DNP3, S7comm, EtherNet/IP-CIP, BACnet, OPC-UA, IEC-104, PROFINET, IEC 61850: port, function, what it exposes, lack of auth, why writes are forbidden, passive analysis approach | `references/protocols.md` |
| External-exposure OSINT (Shodan/Censys dorks, report-only), default-credential classes, known CVEs via CISA advisories, segmentation/flat-network findings, IEC 62443 remediation | `references/exposure-and-cves.md` |
| Consulted public sources (URLs) | `references/sources.md` |

## Cross-references to sibling skills

- **`safe-testing-doctrine`** — mandatory base safety contract (inherited).
- **`offensive-osint` / `osint-methodology`** — external recon technique that the
  Shodan/Censys exposure reporting here builds on (passive OSINT only for OT).
- **`network-service-exploitation`** — for the *IT* side of the IT/OT boundary
  (jump hosts, historians' IT interfaces, remote-access servers) which are often the
  real attack path *into* OT and are testable as normal IT (still respecting scope).
- **`cve-knowledge-base` / `web-cve-exploitation`** — enrichment workflow for the
  CISA-advisory CVEs referenced here; many OT HMIs expose web interfaces.
- **`security-reporting`** — writing OT findings; translate technical risk into
  **safety and process-availability** business risk, which is how OT owners weigh it.

Remediation throughout is framed against **IEC 62443** (zones & conduits,
segmentation, IDMZ, least privilege, secure remote access) and **NIST SP 800-82r3**.
