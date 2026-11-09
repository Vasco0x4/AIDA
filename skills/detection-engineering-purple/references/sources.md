# Sources & further reading (public)

All material below is from public, authoritative sources. Techniques here are for
**defensive** detection engineering and **authorized** purple-team exercises.

## Frameworks & methodology
- **MITRE ATT&CK** — https://attack.mitre.org/ (techniques, data sources,
  adversary emulation plans, Get-Started: Adversary Emulation & Red Teaming).
- **MITRE ATT&CK Navigator** — https://mitre-attack.github.io/attack-navigator/
  (coverage heatmap layers).
- **DeTT&CT (Detect Tactics, Techniques & Combat Threats)** —
  https://github.com/rabobank-cdc/DeTTECT (data-source quality, visibility &
  detection scoring as Navigator layers).
- **SANS Purple Team Exercise Framework (PTEF)** —
  https://www.sans.org/blog/continuous-purple-teaming-practical-approach-strengthening-offensive-capabilities/
- **The Pyramid of Pain** — David J. Bianco (2013) —
  https://www.sans.org/tools/the-pyramid-of-pain/ ;
  original: http://detect-respond.blogspot.com/2013/03/the-pyramid-of-pain.html

## Adversary emulation tooling
- **Atomic Red Team** (Red Canary) — https://github.com/redcanaryco/atomic-red-team ;
  runner `Invoke-AtomicRedTeam` — https://github.com/redcanaryco/invoke-atomicredteam ;
  docs https://www.atomicredteam.io/
- **MITRE Caldera** — https://github.com/mitre/caldera , https://caldera.mitre.org/
- Red Canary comparison of adversary-emulation platforms —
  https://redcanary.com/blog/testing-and-validation/atomic-red-team/comparing-red-team-platforms/

## Detection content (Sigma & SIEM)
- **SigmaHQ / sigma** (rules) — https://github.com/SigmaHQ/sigma
- **Sigma specification & conventions** —
  https://sigmahq.io/docs/ ,
  https://github.com/SigmaHQ/sigma-specification (rules spec, logsource spec,
  SigmaHQ rule convention).
- **pySigma / sigma CLI** (converters/backends) — https://github.com/SigmaHQ/pySigma
- **Elastic detection-rules** — https://github.com/elastic/detection-rules ;
  prebuilt reference — https://www.elastic.co/docs/reference/security/prebuilt-rules/
- **Splunk Security Content / ESCU** — https://research.splunk.com/ ,
  https://github.com/splunk/security_content
- **Microsoft Sentinel content** — https://github.com/Azure/Azure-Sentinel

## Windows logging / telemetry
- **Sysmon** (Sysinternals) —
  https://learn.microsoft.com/sysinternals/downloads/sysmon
- **SwiftOnSecurity/sysmon-config** —
  https://github.com/SwiftOnSecurity/sysmon-config
- **Olaf Hartong/sysmon-modular** (ATT&CK-tagged) —
  https://github.com/olafhartong/sysmon-modular
- **Windows Security Audit events** (event ID reference) —
  https://learn.microsoft.com/windows/security/threat-protection/auditing/
- **Advanced Audit Policy / command-line process auditing** — Microsoft docs.

## Attack-specific detection references
- **Kerberoasting / 4769 RC4 (0x17)** — Sean Metcalf, ADSecurity —
  https://adsecurity.org/?p=3458 ; Splunk research —
  https://research.splunk.com/endpoint/5cc67381-44fa-4111-8a37-7a230943f027/
- **DCSync / 4662 DS-Replication-Get-Changes** — Elastic rule —
  https://github.com/elastic/detection-rules/blob/main/rules/windows/credential_access_dcsync_replication_rights.toml ;
  Splunk research — https://research.splunk.com/endpoint/51307514-1236-49f6-8686-d46d93cc2821/
- **Detecting AD Kerberos attacks** (Splunk Threat Research) —
  https://www.splunk.com/en_us/blog/security/detecting-active-directory-kerberos-attacks-threat-research-release-march-2022.html

## Linux / cloud / container telemetry
- **Linux auditd** — https://github.com/linux-audit/audit-documentation ;
  curated rules — https://github.com/Neo23x0/auditd
- **Sysmon for Linux** — https://github.com/Sysinternals/SysmonForLinux
- **Falco** (runtime, eBPF, container-aware) — https://falco.org/
- **Kubernetes audit logging** —
  https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/
- Cloud: AWS CloudTrail, Azure/Entra sign-in & audit logs, GCP Cloud Audit Logs
  (vendor docs).

## Related skills in this base
`active-directory-attack-paths`, `container-supply-chain-security`,
`cloud-security-testing`, `web-vuln-hunting`, `pentest-methodology`,
`security-reporting`, `safe-testing-doctrine`.
