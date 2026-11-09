# External Exposure, Vulnerabilities & Remediation (Report-First)

> **Safety reminder up front:** External OSINT here surfaces **real, live OT owned by
> other organizations.** You may look at banners and **report exposure** — you may
> **never** connect to, query, authenticate against, or otherwise interact with any
> third-party or internet-exposed OT. For the client's *own* internet-facing OT, the
> deliverable is a **report that it is exposed**, escalated urgently — not a live test.
> Default credentials are **documented as a finding**, not tried against live equipment.

---

## 1. External-exposure OSINT (Shodan / Censys) — passive, report-only

OT should essentially never be directly reachable from the internet. When it is, it is a
critical finding. Shodan and Censys index device banners passively (they scanned, not
you); reading their results is OSINT, not interaction. Use these to find the **client's
own** exposed OT (scoped to their IP ranges / ASNs / org name) and report it.

**Shodan ICS dorks (observe banners, do not connect):**
```
# By ICS port / protocol banner:
port:502                      # Modbus/TCP
port:20000 source address     # DNP3 (banner heuristic)
port:102                      # Siemens S7 (ISO-TSAP)
port:44818                    # EtherNet/IP (ListIdentity in banner)
port:47808                    # BACnet
port:4840                     # OPC-UA
port:2404 asdu address        # IEC-104
tag:ics                       # Shodan's ICS tag
# Product / device families:
"Schneider Electric"          "Modicon"           "Allen-Bradley"
"Siemens" port:102            "SIMATIC"           "Rockwell"
"BACnet"  "Tridium"  "Niagara"    # building automation
"Moxa"   "Lantronix"  "Digi"       # serial-to-Ethernet gateways (common exposure)
# Scope to the client only:
port:502 net:203.0.113.0/24
port:502 org:"Client Name"
# Shodan's curated ICS view: https://icsmap.shodan.io/
```

**Censys equivalents (search language):**
```
services.port: 502
services.service_name: MODBUS
services.service_name: S7
services.service_name: BACNET
services.service_name: FOX            # Niagara Fox / Tridium
# Constrain to client space:
services.port: 502 and ip: 203.0.113.0/24
```

**How to report it:** record the IP, port/protocol, product/firmware from the banner, the
Shodan/Censys observation date, and the inferred owner (confirm it is the client's). Rate
the finding CRITICAL — internet-exposed, unauthenticated control protocol. **Recommend
immediate removal from internet exposure / placement behind VPN+IDMZ**, and note that you
did **not** interact with the device. If the exposed OT turns out to belong to a **third
party**, stop, do not report it as a client finding, and do not touch it.

See `offensive-osint` and `osint-methodology` for the broader passive-OSINT workflow;
apply the OT constraint (observe only) throughout.

---

## 2. Default & weak credentials on HMIs / PLCs / EWS

Default credentials are pervasive in OT because devices ship with well-known logins and
are rarely changed (change is risky and needs downtime). **Document this as a finding
from evidence — do not attempt logins against live equipment.**

- **Where they live:** HMI panels and SCADA web interfaces, PLC web servers, engineering
  workstation software, VNC/RDP to operator stations, serial-to-Ethernet gateways,
  building-automation controllers.
- **How to establish the finding safely:** identify the product/firmware **passively**
  (from capture banners or Shodan) and cross-reference the **vendor's documented default
  credentials** and CISA advisories noting hardcoded/default creds. That establishes
  "device X is deployed and ships with default/known credentials" without touching it.
- **Classes of default-cred issues to report:** vendor defaults unchanged, **hardcoded /
  undocumented backdoor accounts** (a recurring CISA advisory theme), shared operator
  passwords, no per-user accounts, credentials embedded in HMI project files or EWS
  configs.
- **If (and only if) credential validation is explicitly authorized** on a
  **non-production / lab** device in a maintenance window with engineer supervision:
  attempt a single documented default, once, non-locking, and stop. Never run credential
  spraying against OT (lockout = loss of operator access = safety issue).

---

## 3. Known ICS CVEs — fingerprint passively, cite CISA, validate carefully

Map product + firmware (learned **passively**) to known vulnerabilities via **CISA ICS
advisories (ICSA-YY-NNN)** and NVD. Reference the advisory; do **not** fire exploits at
live control equipment.

- **Source of truth:** CISA ICS advisories — https://www.cisa.gov/news-events/cybersecurity-advisories
  (filter to ICS/ICS Medical). Each advisory gives affected products/versions, CVE, CVSS,
  and mitigations. Use the `cve-knowledge-base` skill's enrichment workflow (NVD/EPSS/KEV)
  for prioritization.
- **Recurring OT CVE classes** (cite the specific advisory for the device you found):
  - Unauthenticated protocol operations allowing read/write to logic or memory.
  - Hardcoded/backdoor credentials and authentication bypass in HMIs/controllers.
  - Web-interface flaws (XSS/CSRF/auth-bypass/RCE) on HMI and gateway web servers — see
    `web-cve-exploitation`; these often *are* safely testable if the HMI web UI is on the
    IT side, but confirm the box does not command Level 1 before any active web test.
  - Firmware/update mechanisms without signature verification.
  - Denial-of-service via malformed packets (**explicitly do-not-trigger** on live gear —
    the DoS *is* the safety impact).
- **Historic anchors for context (do not reproduce on live systems):** Stuxnet (S7 logic
  manipulation), TRITON/TRISIS (Triconex **SIS** — the reason SIS is untouchable),
  Industroyer/CRASHOVERRIDE (IEC-101/104/61850 grid protocols), the Ukraine grid attacks.
  These illustrate *why* the safety rules exist.
- **Validation posture:** confirm the CVE by **version fingerprint from passive data**.
  Active exploit validation of an OT CVE requires the full active-testing gate
  (`references/methodology-and-purdue.md` §5), is memory-safety-risky, and for any RCE/DoS
  class should stay **DETECT-ONLY** (fingerprint, don't fire) unless a lab/test rig is
  provided.

---

## 4. Flat networks / no IT-OT segmentation (usually the top finding)

The most common and most impactful OT finding is architectural: **no real segmentation
between IT and OT**, or a flat OT network where everything can reach everything (including
paths toward SIS). This is what turns an IT phishing foothold into plant impact.

**How to find it — passively / by review:**
- From the passive capture and topology (GRASSMARLIN / Wireshark conversations), look for
  **IT hosts talking directly to Level 2/1 devices**, control protocols traversing what
  should be boundaries, and the **absence of an IDMZ** between Level 3 and Level 4.
- Review firewall rulesets and network diagrams (documentation review, not probing):
  bidirectional any-any rules across the boundary, control protocols permitted upward,
  vendor remote-access (VPN/RDP/TeamViewer/cellular RTU routers) landing directly in OT.
- Note shared infrastructure (same VLAN/AD/DNS/DHCP for IT and OT), and any segment where
  **SIS traffic mixes with basic-control or general OT traffic** (a serious finding —
  report, do not probe).

**Remediation (IEC 62443 zones & conduits / NIST 800-82r3):**
- Define **zones** by criticality (enterprise, IDMZ, site ops, supervisory, control,
  safety) and allow traffic only through explicit **conduits**.
- Stand up an **IDMZ (Level 3.5)**: no direct IT↔OT flows; brokered access via jump hosts
  and replicated historians; **data diodes / unidirectional gateways** for one-way egress.
- **Isolate SIS** into its own zone with the most restrictive conduit (ideally air-gapped
  or diode-only monitoring).
- Enforce **least privilege** and **protocol-aware firewalling** (deny write/control
  function codes across conduits — see `references/protocols.md`).
- **Secure remote access**: no direct vendor tunnels into OT; broker through the IDMZ with
  MFA, session recording, and time-boxed access.
- Assign **IEC 62443 Security Levels (SL-T)** per zone and drive remediation to close the
  gap to target.

Frame the business risk for the report in OT terms (see `security-reporting`): the impact
is **safety and process availability** — potential for equipment damage, environmental
release, or injury — not merely data confidentiality. That framing is what moves OT
owners to act.
