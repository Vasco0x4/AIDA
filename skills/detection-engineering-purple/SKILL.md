---
name: detection-engineering-purple
description: "Defensive/purple-team counterpart to the offensive skill base: turn attack techniques into detections, validate logging coverage, and run authorized adversary emulation. Covers the purple-team loop (pick ATT&CK techniques -> emulate with Atomic Red Team / MITRE Caldera -> observe telemetry -> assess detection -> write & tune a Sigma rule -> re-test -> measure coverage with ATT&CK Navigator / DeTT&CT), logging & telemetry foundations (Windows Sysmon + SwiftOnSecurity config and key Security event IDs 4624/4688/4769/4662/7045/etc., Linux auditd, cloud/network logs, and the log gaps that blind detection), detection engineering (writing Sigma rules — logsource/detection/condition structure and fields — translating to Splunk/Elastic/Sentinel, detection-as-code and CI, the Pyramid of Pain and why behavior beats IOC, false-positive tuning), and concrete detections mapped to this base's offensive skills (Kerberoasting 4769 RC4 0x17, DCSync 4662 DS-Replication-Get-Changes, Pass-the-Hash 4624 type 3/9 NTLM, AS-REP roasting, ADCS abuse, coercion/PetitPotam, NTLM relay, LLMNR poisoning, web attacks, container/K8s, cloud IAM). Use to build or tune detections, plan and run a purple-team / adversary-emulation exercise, assess SIEM/EDR logging coverage and gaps, write Sigma or SIEM detection content, or report detection gaps and improvements. Cross-references active-directory-attack-paths, pentest-methodology, security-reporting."
version: 1.0.0
triggers:
  - detection engineering
  - purple team
  - purple teaming
  - sigma rules
  - write a sigma rule
  - atomic red team
  - invoke-atomicredteam
  - caldera
  - adversary emulation
  - attack navigator
  - att&ck navigator
  - dett&ct
  - detection coverage
  - sysmon
  - swiftonsecurity
  - siem detection
  - splunk detection
  - elastic detection rules
  - sentinel analytics
  - threat detection
  - detection as code
  - pyramid of pain
  - windows event id
  - auditd
  - log coverage
  - telemetry gaps
  - detect kerberoasting
  - detect dcsync
  - detect pass the hash
  - false positive tuning
---

# Detection Engineering & Purple Team (Authorized / Defensive)

The **defensive counterpart** to this skill base. Every offensive skill here
(`active-directory-attack-paths`, `web-vuln-hunting`,
`container-supply-chain-security`, `cloud-security-testing`, …) describes a
technique an adversary runs. This skill closes the loop: **make sure that
technique produces telemetry, that a detection fires on it, and that the gap is
measured and reported.** The unit of work is not an exploit — it is a
technique -> emulation -> telemetry -> detection -> coverage chain.

Assumes a blue/purple operator with access to endpoint telemetry (Sysmon/EDR),
a SIEM (Splunk, Elastic, Microsoft Sentinel), and a lab or a deconflicted
authorized environment to emulate in.

## ⚠️ Safety / ethics — read first

This skill **inherits `safe-testing-doctrine`** (hard limits: no destruction, no
availability impact, scope-only, least-intrusive proof, cleanup). It is
**defensive** — its purpose is to build and validate detections, not to gain
access. Even so, adversary emulation *executes real technique behavior*, so:

- **Emulate only in an authorized lab or a deconflicted, in-scope environment.**
  Purple-team runs against production require written authorization, a maintenance
  window, and a **deconfliction** channel so the SOC knows an exercise (not a real
  breach) is in progress. Announce start/stop and a signal word.
- **Benign atomics only.** Use Atomic Red Team / Caldera abilities that emulate a
  technique with harmless markers (a test SPN, a canary file, a benign spawned
  process). Never chain emulation into real credential theft, data exfiltration,
  or lateral movement against real users.
- **No production disruption.** No DoS, no account-lockout storms, no service
  crashes, no destructive cleanup steps. Prefer atomics with a documented,
  non-destructive teardown; run the teardown.
- **Clean up** every artifact the emulation created (test accounts, SPNs, files,
  scheduled tasks, registry keys) and log every action with timestamps so the
  exercise is auditable and detections are reproducible.
- Detection content you write is defensive and safe to share; emulation
  command detail stays lab/authorized. When in doubt, STOP and check in.

## The purple-team loop (the core method)

```
   ┌─> 1. SELECT technique (ATT&CK ID, threat-intel driven)
   │        └─ map to an offensive skill in this base
   │   2. EMULATE (Atomic Red Team / Caldera, benign) in lab/deconflicted
   │   3. OBSERVE telemetry — did anything get logged? (Sysmon/4688/EDR/cloud)
   │        └─ NO log  -> LOG GAP: fix collection, go to 2
   │   4. ASSESS detection — did an existing rule fire?
   │        └─ NO alert -> DETECTION GAP: go to 5
   │   5. WRITE / TUNE detection (Sigma -> SIEM), target behavior not IOC
   │   6. RE-TEST — re-run the atomic, confirm the rule fires, tune FPs
   └── 7. MEASURE coverage (ATT&CK Navigator / DeTT&CT) + REPORT gaps
```

Three outcomes for every technique, and each has a different fix:
- **Not logged** (telemetry gap) -> fix logging/collection first — no rule can
  detect what was never recorded. See `references/logging-and-sigma.md`.
- **Logged but not detected** (detection gap) -> write/tune a rule. See
  `references/logging-and-sigma.md` (Sigma) + `references/detections-for-base-attacks.md`.
- **Logged and detected** -> validate FP rate, record coverage, move on.

## Index

| Reference | What it covers | Load when |
|-----------|----------------|-----------|
| `references/purple-team-workflow.md` | The emulate -> detect -> tune loop in depth; Atomic Red Team & Caldera usage; DeTT&CT + ATT&CK Navigator coverage mapping; exercise planning & deconfliction; measuring detection maturity | Planning/running a purple-team or adversary-emulation exercise; measuring coverage |
| `references/logging-and-sigma.md` | Telemetry foundations (Sysmon + SwiftOnSecurity config, key Windows Security event IDs, Linux auditd, cloud/network logs, common log gaps); writing Sigma rules (logsource/detection/condition, fields, modifiers); translating Sigma to Splunk SPL / Elastic EQL/KQL / Sentinel KQL; detection-as-code & FP tuning; Pyramid of Pain | Deciding what to log; writing a Sigma rule; converting to a SIEM; reducing false positives |
| `references/detections-for-base-attacks.md` | Concrete detection ideas mapped to each offensive skill: Kerberoasting, AS-REP, DCSync, PtH/PtT, ADCS, delegation, coercion/relay, LLMNR poisoning, web attacks (webshell/SQLi/SSRF), container/K8s, cloud IAM — each with event source, logic, and Pyramid level | You need a detection for a specific technique the red team ran |
| `references/sources.md` | Public references (MITRE ATT&CK, SigmaHQ, Atomic Red Team, Caldera, Elastic/Splunk content, Sysmon, DeTT&CT, Pyramid of Pain) | Verifying provenance / deeper reading |

## Where this fits with the rest of the base

- **`active-directory-attack-paths`** — the AD kill chain this skill detects
  (Kerberoasting, DCSync, relay, coercion, ADCS). Read its "detection/OPSEC"
  notes alongside `references/detections-for-base-attacks.md`.
- **Evasion awareness** — attackers try to *avoid* the telemetry here (AMSI
  tampering, ETW patching, unhooking, LOLBins). Detection must anticipate evasion:
  prefer behavior/kernel/cloud signals the attacker can't easily silence.
- **`pentest-methodology`** — the ATT&CK mapping and phase model that feed
  technique selection; a purple-team exercise is a pentest run *collaboratively*
  with the blue team.
- **`security-reporting`** — how to write up detection gaps and coverage as a
  deliverable (findings, severity, remediation, retest). Coverage reporting in
  `references/purple-team-workflow.md` feeds directly into it.

## Golden rules

1. **You can only detect what you log.** Verify telemetry before blaming the rule.
2. **Climb the Pyramid of Pain.** Behavior/TTP detections survive attacker
   IOC rotation; hash/IP detections don't. Prefer the top of the pyramid.
3. **Emulate to validate.** A rule that has never fired on a real emulation is a
   hypothesis, not a detection. Re-test after every change.
4. **Detection-as-code.** Version rules in git, test them, review them, deploy via
   pipeline — same rigor as software.
5. **Tune for the environment.** Every detection has a false-positive budget;
   an alert nobody triages is worse than none. Measure and tune.
