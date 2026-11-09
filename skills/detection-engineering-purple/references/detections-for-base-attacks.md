# Detections mapped to the base's offensive skills

For each attacker technique in this skill base, a concrete detection: the ATT&CK
ID, the **telemetry source + event**, the **detection logic**, its
**Pyramid-of-Pain level** (durability), and the **validating atomic**. Prefer
behavior/TTP signals; note the log prerequisite (many are off by default).

Format per entry: **Technique (ATT&CK) — skill it comes from** → telemetry → logic
→ pyramid / FP notes.

---

## Active Directory (`active-directory-attack-paths`)

### Kerberoasting — T1558.003
- **Telemetry**: DC Security log **4769** (Kerberos service ticket requested).
- **Logic**: `EventID 4769 AND TicketEncryptionType=0x17 (RC4-HMAC)` excluding
  machine accounts (`ServiceName endswith $`) and `krbtgt`. Escalate on **>~3
  distinct SPNs requested as RC4 from one account within ~30 min**, or on RC4 in
  an AES-only environment.
- **Pyramid**: behavior/TTP (high). RC4 downgrade is intrinsic to offline
  cracking — hard for the attacker to avoid without giving up crackability.
- **FP**: legacy apps that still use RC4; baseline and exclude. **Atomic**: T1558.003.

### AS-REP Roasting — T1558.004
- **Telemetry**: DC **4768** (AS-REQ) with RC4; presence of accounts with
  "Do not require Kerberos preauth" (`userAccountControl` 0x400000).
- **Logic**: `4768 with pre-auth not required AND EncryptionType=0x17`; also alert
  on LDAP queries enumerating `DONT_REQ_PREAUTH` accounts.
- **Pyramid**: behavior (high). **Atomic**: T1558.004.

### Kerberos password spray / brute — T1110.003
- **Telemetry**: DC **4771** (pre-auth failed, failure code 0x18) and/or **4625**.
- **Logic**: one source IP -> many distinct target accounts failing in a short
  window (spray), or one account many fails (brute). Threshold + `count by src`.
- **Pyramid**: behavior. **FP**: broken service creds, VPN reconnects — baseline.

### DCSync — T1003.006
- **Telemetry**: DC Security **4662** (requires *Audit Directory Service Access* +
  SACL on domain object).
- **Logic**: **4662** where **Properties** contains the replication control-access
  GUIDs **DS-Replication-Get-Changes** (`1131f6aa-...`),
  **DS-Replication-Get-Changes-All** (`1131f6ad-...`), or `...-In-Filtered-Set`,
  **AND** the requesting account is **not** a Domain Controller machine account or
  sanctioned replication service. AccessMask often `0x100` (control access).
  Corroborate with a **4624 type 3** from a non-DC host just prior.
- **Pyramid**: behavior/TTP (high) — replication from a non-DC is the durable
  signal, tool-independent (mimikatz, secretsdump, DSInternals all trip it).
- **FP**: legit DC promotions, Azure AD Connect / MSOL sync account — allowlist
  those specific principals. **Atomic**: T1003.006. Elastic ships a prebuilt rule.

### Pass-the-Hash / overpass-the-hash — T1550.002 / T1550.003
- **Telemetry**: **4624** on the target with **Logon Type 3** (network) and
  **Logon Type 9** (NewCredentials, overpass/`sekurlsa::pth`); 4624 `AuthenticationPackageName=NTLM`
  where Kerberos is expected; `LogonProcessName`/`KeyLength=0` anomalies.
- **Logic**: NTLM network logon to a host using a domain account that normally
  authenticates via Kerberos; type 9 logon with outbound NTLM from an unusual
  process (`seclogon`), especially followed by lateral access. Correlate with
  **4648** (explicit creds).
- **Pyramid**: host/behavior artifact (medium-high) — the NTLM-where-Kerberos and
  type-9 patterns are durable; specific tool hashes are not.
- **FP**: legitimate NTLM in mixed environments; scope to sensitive assets/admins.
  **Atomic**: T1550.002.

### Pass-the-Ticket / Golden/Silver ticket — T1550.003 / T1558.001-002
- **Telemetry**: **4769**/**4624** anomalies; TGTs with abnormal lifetimes;
  Silver ticket = service access **without a corresponding 4769 on the DC**;
  Golden ticket = tickets referencing a nonexistent/mismatched account or krbtgt
  anomalies.
- **Logic**: service logon (4624) on a member server with **no matching TGS
  request (4769) on the DC** = forged silver ticket; RID/account mismatches; TGT
  lifetime far exceeding domain policy.
- **Pyramid**: behavior (high) but harder — invest in ticket-lifetime and
  missing-4769 correlation. **Atomic**: T1558.001.

### ADCS abuse (ESC1–ESC8) — T1649
- **Telemetry**: CA logs / **4886/4887** (cert requested/issued), **4768** where
  logon is certificate-based; template changes via **5136**.
- **Logic**: certificate issued where **SAN ≠ requester** (ESC1); enrollment for a
  template allowing SAN specification by a low-priv user; sudden cert-based TGT
  (4768) for a privileged account (Certifried). Monitor template DACL changes.
- **Pyramid**: behavior (high). **FP**: legit auto-enrollment — baseline templates.

### ACL/DACL abuse & shadow credentials — T1098 / T1484
- **Telemetry**: **5136** (directory object modified) — track writes to
  `msDS-KeyCredentialLink` (shadow creds), `nTSecurityDescriptor` (WriteDACL),
  `member` (AddMember), `msDS-AllowedToActOnBehalfOfOtherIdentity` (RBCD).
- **Logic**: alert on modification of these attributes by non-admin principals or
  to sensitive objects; correlate `msDS-KeyCredentialLink` add -> subsequent PKINIT
  4768.
- **Pyramid**: behavior (high). Needs *Audit Directory Service Changes* + SACLs.

### Coercion (PetitPotam / PrinterBug / DFSCoerce) — T1187
- **Telemetry**: **5145** (detailed file share) showing access to named pipes
  `\lsarpc`, `\efsrpc`, `\spoolss`, `\netdfs`; inbound auth to a relay listener.
- **Logic**: RPC call to EFSRPC/MS-RPRN/MS-DFSNM from an unexpected host, followed
  by the DC/server making an **outbound** NTLM auth (4624 type 3 elsewhere).
- **Pyramid**: behavior (high). **FP**: legit print/DFS — scope by source.

### NTLM relay — T1557.001
- **Telemetry**: **4624** type 3 NTLM where the **source and authenticating
  identity mismatch** (auth arriving from a relay host); LDAP/SMB signing failures.
- **Logic**: a machine/user authenticating from an IP that isn't theirs;
  simultaneous auth to LDAP/SMB from a single relay host to many targets.
- **Pyramid**: behavior. Remediation-adjacent: alert on **SMB/LDAP signing not
  required**. 

### LLMNR/NBT-NS/mDNS poisoning — T1557.001 (initial access)
- **Telemetry**: network — anomalous LLMNR (UDP 5355) / NBT-NS (137) **responses**;
  a host answering name queries for many different names; NetNTLM auth to a rogue
  host.
- **Logic**: one host responding authoritatively to LLMNR/NBT-NS for names it
  doesn't own = Responder. Alert on the *responder* behavior, not a hash.
- **Pyramid**: behavior (high). Best fix + detect: disable LLMNR/NBT-NS, then any
  traffic is suspicious.

### Credential dumping — LSASS — T1003.001
- **Telemetry**: **Sysmon 10** (ProcessAccess) `TargetImage=lsass.exe` with
  suspicious `GrantedAccess` (0x1010/0x1410/0x1fffff); Sysmon 11 for dump files;
  4688/Sysmon 1 for `comsvcs.dll MiniDump`, `procdump`, `rundll32` LSASS.
- **Logic**: non-security-product process opening LSASS with read/dump rights;
  creation of `*.dmp` in temp; `MiniDump` LOLBin patterns.
- **Pyramid**: behavior (high) — the LSASS access is durable across tools.
  **Atomic**: T1003.001. Note: attackers try to blind
  Sysmon/EDR here, so corroborate with kernel/ETW-TI where available.

### Malicious service / PsExec lateral — T1569.002 / T1021.002
- **Telemetry**: **7045** (System, service installed) + **4697**; **5145** ADMIN$;
  Sysmon 1 for `services.exe` -> odd child; 4624 type 3.
- **Logic**: new service with a random/short name, binary in temp, or cmd/PowerShell
  as the image path; PSEXESVC pattern. **Pyramid**: tool/behavior. **Atomic**: T1021.002.

---

## Web (`web-vuln-hunting`, `web-cve-exploitation`)
Telemetry: web/WAF/proxy/app logs + Sysmon on the web host.
- **Webshell / RCE after upload** (T1505.003): web server process (`w3wp`,
  `php-fpm`, `java`) spawning `cmd`/`sh`/`whoami`/`powershell` — a **process-lineage**
  detection (Sysmon 1 parent=web process). Highest-value web detection; tool-agnostic.
- **SQLi / injection** (T1190): WAF/app logs with injection signatures, spikes of
  500s, `UNION SELECT`/error patterns, sudden DB errors. Pyramid: artifact (medium)
  — signatures rotate; pair with anomalous DB query volume.
- **SSRF** (T1190): app making outbound requests to **169.254.169.254** / internal
  ranges; egress DNS/HTTP from the app tier to metadata endpoints.
- **Known-CVE exploitation**: match the CVE's IOCs/paths (from `web-cve-exploitation`)
  *and* the post-exploit behavior (shell spawn). Behavior beats the URL signature.

## Containers / Kubernetes (`container-supply-chain-security`, `cloud-security-testing`)
- **Container escape / privileged pod** (T1611): Falco / auditd — `mount`,
  `nsenter`, writes to `/proc/*/root`, `release_agent`; K8s audit log for
  `privileged:true`, `hostPath`, `hostPID` pods.
- **K8s API abuse** (T1613): K8s **audit log** — `exec`/`attach` into pods,
  anonymous or over-broad RBAC (`create pods`, `get secrets`), `kubectl auth can-i`
  reconnaissance patterns, serviceaccount-token use from unexpected IPs.
- **Sensitive mount / docker.sock** access: Falco rule on `/var/run/docker.sock`.
- Pyramid: behavior (high) — audit-log verbs are durable.

## Cloud IAM (`cloud-security-testing`)
- **Privilege escalation / role abuse** (T1078.004): CloudTrail `AssumeRole`,
  `PassRole`, `AttachUserPolicy`, `CreateAccessKey` on another user; Entra role
  assignment / consent grant; GCP `setIamPolicy`. Alert on privilege-granting API
  calls by non-admin principals or from new IPs/ASNs.
- **IMDS/SSRF credential theft** (T1552.005): temporary creds used from an IP
  outside the instance (GuardDuty `InstanceCredentialExfiltration`); flag IMDSv1.
- **Anomalous console login / impossible travel** (T1078): 4624-equivalent cloud
  sign-in logs; new-country/new-device first-seen.
- Pyramid: behavior (high) — API verbs + first-seen context.

## Evasion counter-detections
Attackers try to *remove* the telemetry above. Watch the meta-signals:
- **Log clearing** — Security **1102**, Sysmon service stop, `wevtutil cl`.
- **ETW/AMSI tampering** — Sysmon 7/8 patterns against `amsi.dll`/`ntdll` ETW
  functions; PowerShell 4104 with AMSI-bypass strings.
- **Defender tampering** — Defender/Operational 5001 (real-time protection
  disabled), `Set-MpPreference -Disable*`.
- **Sysmon/EDR service stop or driver unload** — service-control events, missing
  expected heartbeat.
- Pyramid: behavior (high). These are prime purple-team targets: emulate the
  evasion, confirm you still see *something* (kernel ETW-TI, cloud, network) when
  the endpoint agent is blinded — defense in depth across telemetry sources.

---

## How to use this file in the loop
1. Red team runs a technique (from the mapped offensive skill).
2. Find the matching entry here -> confirm the **telemetry source** is actually
   collected (fix the log gap first — see `logging-and-sigma.md`).
3. Implement the **logic** as a Sigma rule (structure in `logging-and-sigma.md`),
   converge on the highest **Pyramid** signal available.
4. Validate with the listed **Atomic** test, tune FPs, record coverage
   (`purple-team-workflow.md`), report gaps (`security-reporting`).
