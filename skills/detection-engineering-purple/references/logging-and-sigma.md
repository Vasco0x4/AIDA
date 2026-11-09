# Logging & telemetry foundations + writing Sigma

You can only detect what you log. This file covers **what to collect** (Windows,
Linux, cloud, network), the **log gaps** that silently blind detection, then how
to **write a Sigma rule** and **translate it** to Splunk / Elastic / Sentinel,
plus detection-as-code and false-positive tuning. Anchored on the **Pyramid of
Pain**: prefer signals near the top.

## The Pyramid of Pain (why behavior beats IOC)

David Bianco's model — how much *pain* you cause an attacker by detecting at each
level, bottom (trivial to change) to top (hard to change):

1. **Hash values** — trivial; recompile flips the hash.
2. **IP addresses** — easy; rotate infrastructure.
3. **Domain names** — simple; register a new domain.
4. **Host / network artifacts** — annoying (registry keys, named pipes, User-Agents, service names).
5. **Tools** — challenging (detecting *the tool* forces a rebuild/replace).
6. **TTPs / behavior** — tough; changing *how* they operate is expensive.

**Detection-engineering consequence:** IOC feeds (hash/IP/domain) age out in
days; behavior/TTP detections (levels 4–6) survive attacker changes. Spend effort
at the top. A Sigma rule keyed on *"lsass.exe opened with GetChanges replication
rights"* beats one keyed on a specific tool hash. This is why emulation (running
the *behavior*) is how you validate — the behavior is the durable signal.

## Windows telemetry

### Sysmon (System Monitor)
Adds high-fidelity endpoint events that the default Security log lacks. Deploy
with a curated config — **SwiftOnSecurity's `sysmon-config`** (broad coverage,
heavy *exclusion* filtering of known-good software) or **Olaf Hartong's
`sysmon-modular`** (ATT&CK-tagged, modular). Most rules *exclude* noise rather
than include, so tune per environment. Key event IDs:

| Sysmon ID | Event | Detection value |
|-----------|-------|-----------------|
| 1  | Process creation | Full command line + hashes + parent — the workhorse; LOLBins, suspicious parent/child, encoded PowerShell |
| 3  | Network connection | Per-process outbound conns — C2, beaconing, lateral tools |
| 7  | Image (DLL) loaded | DLL hijack/side-loading, unsigned DLLs in odd paths |
| 8  | CreateRemoteThread | Classic process injection |
| 10 | ProcessAccess | LSASS access (credential dumping) — filter on `TargetImage: lsass.exe` |
| 11 | File create | Dropper files, webshells, ransomware canaries |
| 12/13/14 | Registry add/set/rename | Persistence (Run keys), config tampering |
| 15 | FileCreateStreamHash | Alternate data streams, mark-of-the-web |
| 22 | DNS query | Per-process DNS — DGA, C2 domains, exfil |
| 25 | Process tampering | Process hollowing / image replacement |

### Native Windows Security log — key event IDs
Enable via **Advanced Audit Policy** (Group Policy). The high-value IDs for the
attacks in this base:

| Event ID | Meaning | Detects |
|----------|---------|---------|
| 4624 | Successful logon (see **Logon Type**) | Type 3 = network (PtH, SMB), Type 9 = NewCredentials (overpass/runas), Type 10 = RDP |
| 4625 | Failed logon | Password spraying / brute force (many 4625 across accounts) |
| 4634/4647 | Logoff | Session correlation |
| 4648 | Explicit-credential logon | `runas`/overpass-the-hash |
| 4662 | Operation on an AD object | **DCSync** (DS-Replication-Get-Changes GUIDs) — requires *Audit Directory Service Access* |
| 4672 | Special privileges assigned | Admin/`SeDebug` logons |
| 4688 | Process creation (native) | Alt to Sysmon 1; enable **command-line auditing** or it's near-useless |
| 4697 | Service installed (Security) | Persistence / PsExec-style service |
| 4698/4702 | Scheduled task created/updated | Persistence (T1053) |
| 4720/4722/4728/4732/4756 | Account created / enabled / added to (global/local/universal) group | Persistence, privilege grants |
| 4738 | User account changed | Password/attribute tampering |
| 4768 | Kerberos TGT requested (AS-REQ) | AS-REP roasting context, initial auth |
| 4769 | Kerberos service ticket requested (TGS-REQ) | **Kerberoasting** — watch **Ticket Encryption Type 0x17 (RC4)** + many SPNs from one account |
| 4771 | Kerberos pre-auth failed | AS-REP roasting / Kerberos brute |
| 5136 | Directory object modified | ACL/DACL abuse, GPO changes, `msDS-KeyCredentialLink` (shadow creds) |
| 5140/5145 | Network share accessed / detailed | Lateral movement, SMB relay landing, ADMIN$/C$ |
| 7045 | Service installed (System log) | PsExec, malicious services (pairs with 4697) |
| 1102 | Security log cleared | Anti-forensics / defense evasion |

Also collect: **PowerShell** Script Block Logging (Microsoft-Windows-PowerShell/
Operational **4104**) + Module (4103) + transcription — essential given how much
tradecraft is PowerShell; **WMI-Activity/Operational** (5857–5861) for WMI
persistence; **AppLocker/WDAC** events; **Windows Defender/Operational** (1116/1117).

### Windows log gaps that blind detection (fix these first)
- **4688 without command-line auditing** — you see a process ran but not *how*.
  Enable "Include command line in process creation events".
- **4662 not collected** — DCSync invisible. Enable *Audit Directory Service
  Access* + SACL on the domain object.
- **No Sysmon** — no reliable process-injection / LSASS-access / DNS visibility.
- **PowerShell logging off** — encoded/downloaded payloads invisible.
- **DC-only Kerberos events** — 4769/4768 are logged **on the DC**, not the
  workstation; forward DC security logs or you'll never see Kerberoasting.
- **Short retention / no forwarding** — events roll over before the SIEM ingests.
  Use WEF/WEC or an agent (Winlogbeat/Splunk UF/Elastic Agent) to centralize.

## Linux telemetry — auditd
The Linux audit framework. Write rules in `/etc/audit/rules.d/`; read with
`ausearch`/`aureport`. High-value coverage:
- **execve** syscall auditing -> command execution (equivalent of process
  creation). Tag rules with keys (`-k exec`).
- Watches on sensitive files: `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`,
  SSH `authorized_keys`, cron dirs.
- Privilege events: `setuid`/`setgid`, sudo usage (`/var/log/auth.log` / `secure`).
- Consider **Sysmon for Linux** (eBPF-based, same schema family) or **auditbeat**
  / **Falco** (container-aware, syscall/eBPF) for richer, ATT&CK-mappable events.
- Gaps: default auditd rules are minimal; ship a curated ruleset (e.g. Neo23x0's
  auditd rules) and forward centrally, or Linux stays a blind spot.

## Cloud & network telemetry
- **AWS**: CloudTrail (management + data events), GuardDuty, VPC Flow Logs,
  S3/Config. Detect IAM abuse, `AssumeRole`, `ConsoleLogin`, key exfil.
- **Azure / Entra ID**: Sign-in & Audit logs, Unified Audit Log, Defender, Azure
  Activity. Detect consent grants, role assignments, impossible travel.
- **GCP**: Cloud Audit Logs (Admin Activity / Data Access), VPC Flow.
- **Microsoft 365**: Unified Audit Log (mailbox, sharing, OAuth apps).
- **Network**: Zeek/Suricata, NetFlow, DNS logs, proxy/WAF logs, firewall — good
  for lateral movement, beaconing, exfil, and web attacks. (Cross-ref
  `cloud-security-testing` for the attack side.)

Sigma has `logsource` categories for many of these (`product: aws`,
`service: cloudtrail`; `product: azure`, etc.), so the same rule discipline applies.

## Writing a Sigma rule

Sigma is the vendor-neutral "YAML for detections" — write once, convert to any
SIEM via `sigma` CLI / pySigma backends. Rule anatomy:

```yaml
title: Kerberoasting - RC4 Service Ticket Requested for Many SPNs   # concise, specific
id: 5f8c...-uuid          # stable UUID, never reused
status: experimental       # experimental | test | stable | deprecated
description: Detects Kerberos TGS-REQ using weak RC4 encryption, a hallmark of Kerberoasting.
references:
  - https://attack.mitre.org/techniques/T1558/003/
author: Blue Team
date: 2026-08-13
tags:
  - attack.credential-access
  - attack.t1558.003
logsource:                 # WHERE to look — category | product | service
  product: windows
  service: security
detection:                 # WHAT to match — search-identifiers (maps) + condition
  selection:
    EventID: 4769
    TicketEncryptionType: '0x17'      # RC4-HMAC = the crackable ticket
  filter_machine:
    ServiceName|endswith: '$'         # exclude machine-account service tickets
  filter_krbtgt:
    ServiceName: 'krbtgt'
  condition: selection and not 1 of filter_*
fields:                    # what to surface in the alert
  - TargetUserName
  - ServiceName
  - IpAddress
falsepositives:
  - Legacy apps/services that still negotiate RC4 (baseline & exclude)
level: high                # informational | low | medium | high | critical
```

Key mechanics:
- **`logsource`** = `category` (group of products, e.g. `process_creation`,
  `firewall`), `product` (e.g. `windows`, `aws`), `service` (e.g. `security`,
  `sysmon`, `sshd`). Pick the narrowest that fits.
- **`detection`** = one or more named **selections** (maps of field:value, ANDed
  within a map; a value list is ORed) + a **`condition`** that combines them
  (`and`, `or`, `not`, `1 of selection_*`, `all of them`, counts like
  `| count() by ... > 5`).
- **Field modifiers** refine matching: `|contains`, `|startswith`, `|endswith`,
  `|re` (regex), `|all` (list must all match), `|base64`/`|base64offset`
  (encoded command lines), `|cidr` (IP ranges), `|windash` (flag variants).
- **Filters + `not`** are how you kill false positives without deleting the rule:
  `condition: selection and not filter`.
- Use the **SigmaHQ conventions**: lowercase-hyphen title style, stable UUID,
  correct ATT&CK tags, meaningful `falsepositives`, honest `level`.
- Reuse first: check the **SigmaHQ/sigma** repo — a vetted rule may already exist;
  adapt it rather than write from scratch.

## Translating Sigma to a SIEM

Use the `sigma` CLI (pySigma) with the right backend/pipeline:

```
sigma convert -t splunk    -p splunk_windows   rule.yml   # -> SPL
sigma convert -t esql      -p ecs_windows      rule.yml   # -> Elastic ES|QL
sigma convert -t lucene    -p ecs_windows      rule.yml   # -> Elastic/Kibana
sigma convert -t kusto     -p sentinel         rule.yml   # -> Sentinel/Defender KQL
```

The **pipeline** (`-p`) does field mapping — Sigma's logical field
(`TicketEncryptionType`) to the SIEM's real field (Splunk `Ticket_Encryption_Type`,
ECS `winlog.event_data.TicketEncryptionType`). Roughly what each target looks like:

- **Splunk SPL**: `index=wineventlog EventCode=4769 Ticket_Encryption_Type=0x17
  NOT (Service_Name="*$" OR Service_Name="krbtgt") | stats ... `. Splunk also ships
  curated content — **ESCU / Splunk Security Content** (`research.splunk.com`) —
  already ATT&CK-mapped; reuse and cite it.
- **Elastic**: prebuilt **detection-rules** repo (TOML, EQL/KQL/ES|QL). EQL is
  great for *sequence* behavior (`sequence by host.id [process where ...] [network
  where ...]`).
- **Microsoft Sentinel / Defender XDR**: **KQL** analytics rules; many community +
  Microsoft rules on GitHub, ATT&CK-tagged.

Prefer, in order: (1) an existing vetted rule from SigmaHQ/Elastic/Splunk content;
(2) a Sigma rule you convert; (3) hand-written SIEM query as a last resort.

## Detection-as-code & CI

Treat detections like software:
- **Version control** every rule (git), with PR review and ATT&CK tags.
- **Test**: pair each rule with the **Atomic Red Team** test that should trigger
  it. In CI, run the atomic in a lab, ship the telemetry, assert the rule fires
  (and doesn't fire on a known-good sample) — a **detection unit test**.
- **Lint/validate**: `sigma check` / pySigma validators for schema + field
  correctness before merge.
- **Deploy** via pipeline to the SIEM; track rule metadata (owner, ATT&CK ID,
  validating atomic, last-tested date).
- **Metrics**: true/false-positive counts per rule, time-to-detect, coverage delta
  over time.

## False-positive tuning (make alerts triageable)

An alert nobody triages is worse than no alert. For every new rule:
1. **Baseline** — run it over historical data / a quiet period; enumerate what it
   fires on legitimately (admin scripts, backup accounts, vuln scanners, legacy
   RC4 apps, service accounts).
2. **Add filters** — exclude known-good with `not filter` selections; scope to
   asset/OU/user context where possible. Prefer *behavioral* exclusions
   (`parent process X spawning Y`) over blanket IP/host allowlists.
3. **Add thresholds / aggregation** — e.g. Kerberoasting = *many* distinct SPNs
   as RC4 from one account in a short window, not a single 4769; spraying = *N*
   4625 across *M* accounts. Rare-event enrichment (first-seen) cuts noise.
4. **Set severity honestly** — reserve `critical/high` for high-confidence; put
   noisy-but-useful signals at `low`/`informational` feeding hunts, not pages.
5. **Re-test** with the atomic after each change; record final FP rate.
