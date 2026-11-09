---
name: privilege-escalation
description: "Authorized, host-level local privilege escalation on standalone Linux and Windows machines — from a low-privileged foothold to root/SYSTEM — complementing the domain-level active-directory-attack-paths skill. Linux: enumeration (LinPEAS/LinEnum/pspy/linux-exploit-suggester), SUID/SGID abuse via GTFOBins, sudo misconfiguration (sudo -l + GTFOBins), cron/wildcard/PATH abuse, writable /etc/passwd & /etc/shadow, Linux capabilities (getcap), NFS no_root_squash, docker/lxd/disk group membership, LD_PRELOAD/LD_LIBRARY_PATH & shared-object hijack, and kernel/component LPE CVEs (PwnKit CVE-2021-4034, DirtyPipe CVE-2022-0847, Dirty COW CVE-2016-5195, Looney Tunables CVE-2023-4911) marked crash-risk where relevant. Windows: enumeration (WinPEAS/PowerUp/Seatbelt/SharpUp/accesschk), unquoted service paths, weak service & registry ACLs, AlwaysInstallElevated, DLL search-order/hijack, service-binary & PATH hijack, token impersonation from SeImpersonate/SeAssignPrimaryToken via the Potato family (PrintSpoofer/GodPotato/RoguePotato/JuicyPotato/SigmaPotato), SeBackup/SeRestore/SeDebug abuse, UAC-bypass concepts, autoruns/scheduled tasks, and credential hunting (registry, SAM/SYSTEM hives, unattend/GPP, stored creds). For each finding: HOW TO FIND (enum command), HOW TO EXPLOIT (least-intrusive, crash-prone marked DETECT-ONLY/lab-only), a public reference, detection, and remediation. Authorized, in-scope, contracted engagements only — prove escalation minimally (id/whoami) then stop; no persistence; clean up. Use for linux privesc, windows privesc, suid, sudo -l, gtfobins, lolbas, linpeas, winpeas, powerup, potato, seimpersonate, printspoofer, godpotato, unquoted service path, alwaysinstallelevated, dll hijacking, writable path, capabilities, no_root_squash, docker group, ld_preload, pwnkit, dirtypipe, dirtycow, looney tunables, uac bypass, or writing local-privesc findings with remediation."
version: 1.0.0
triggers:
  - linux privesc
  - windows privesc
  - local privilege escalation
  - privilege escalation
  - root
  - system
  - suid
  - sgid
  - sudo
  - sudo -l
  - gtfobins
  - lolbas
  - linpeas
  - linenum
  - pspy
  - linux-exploit-suggester
  - winpeas
  - powerup
  - seatbelt
  - sharpup
  - accesschk
  - potato
  - printspoofer
  - godpotato
  - roguepotato
  - juicypotato
  - sigmapotato
  - seimpersonate
  - seassignprimarytoken
  - sebackupprivilege
  - sedebugprivilege
  - token impersonation
  - unquoted service path
  - weak service permissions
  - alwaysinstallelevated
  - dll hijacking
  - dll search order
  - service binary hijack
  - path hijack
  - writable path
  - capabilities
  - getcap
  - no_root_squash
  - nfs privesc
  - docker group
  - lxd privesc
  - ld_preload
  - writable /etc/passwd
  - cron privesc
  - wildcard injection
  - pwnkit
  - cve-2021-4034
  - dirtypipe
  - cve-2022-0847
  - dirtycow
  - cve-2016-5195
  - looney tunables
  - cve-2023-4911
  - uac bypass
  - autoruns
  - scheduled task privesc
  - credential hunting
  - unattend.xml
  - gpp password
  - sam hive
---

# Privilege Escalation (Authorized Host-Level: low-priv → root/SYSTEM)

Operational playbook for **local** privilege escalation on **standalone** Linux and
Windows hosts once you already have a low-privileged shell (post-exploitation, valid
low-priv creds, or an assumed-breach foothold). The bias throughout is
**enumerate first**, choose the **least-intrusive** technique, prove escalation with a
single identity check (`id` / `whoami /priv`), then **stop**. This skill is the
host-level companion to `active-directory-attack-paths` (which covers domain-wide
escalation to Domain Admin) — use this one on non-domain hosts, on the local
Administrator/root path, and on the "escalate the foothold before you pivot" step.

Commands assume: a Linux attack box for tooling/serving, and that you can transfer the
standard tools to the target (LinPEAS/LinEnum/pspy, `linux-exploit-suggester.sh`;
WinPEAS/PowerUp/Seatbelt/SharpUp/accesschk). GTFOBins and LOLBAS are the two
lookup tables you will use constantly.

## ⚠️ Safety — inherits `safe-testing-doctrine`

Load **`safe-testing-doctrine`** before any active test. This skill inherits every hard
limit there. Local-privesc specifics:

- **NO DoS. Kernel/component memory-corruption exploits can crash the host** (kernel
  panic, corrupted glibc, unbootable system). The following are **crash-prone** and are
  **DETECT-ONLY by default** — fingerprint the vulnerable version and report it as the
  finding. Run the actual exploit **only** in a lab or with explicit written RoE naming
  a **non-production / snapshotted** host where the client expects instability and a
  reboot:
  - **Dirty COW** (CVE-2016-5195) — race, can destabilize/hang the box.
  - **DirtyPipe** (CVE-2022-0847) — overwrites files/SUID pages; PoCs can corrupt the
    overwritten binary if not restored.
  - **Looney Tunables** (CVE-2023-4911) — glibc `ld.so` overflow; a bad run can leave
    glibc/loader unstable.
  - **Any `linux-exploit-suggester` / Watson / Sherlock kernel-exploit hit** — treat
    the suggester output as a *finding to report*, not an auto-run list.
  - **PwnKit** (CVE-2021-4034) is memory-corruption but generally reliable/clean; even
    so, prefer detect-first and only run where RoE allows.
- **Prove minimally, then stop.** The moment you land a root/SYSTEM context, run
  **only** `id` / `whoami` (Windows: `whoami /priv`, `whoami /groups`) to capture proof,
  screenshot/log it, and **stop escalating**. Do not read user data, dump the whole
  SAM/shadow, or roam the filesystem beyond what proves the finding.
- **No persistence.** Do not add users, SSH keys, backdoor services, scheduled tasks,
  cron jobs, run-keys, or web shells unless persistence is explicitly in the RoE. If you
  must create anything to prove a path (a test service binary, a payload MSI, a planted
  DLL, a benign SUID copy), it is a **temporary marker** — record it and remove it.
- **Cleanup obligations.** Restore anything you touched: files overwritten by a PoC,
  a modified `/etc/passwd`, a hijacked service binary/DLL, an `AlwaysInstallElevated`
  MSI, planted `.so`/`.dll`, `sudoers`/registry edits. Keep a per-action, timestamped
  cleanup log for the report and the retest.
- **Scope-only.** Only on in-scope hosts. Local privesc is not license to then attack
  other machines — pivoting/lateral movement is governed by the RoE and the
  `active-directory-attack-paths` skill.
- **Credential handling.** Hashes/creds you recover are sensitive evidence — store
  minimally and securely, never post them to third-party crackers, mask in the report.

## Area → reference file

| Platform | Area | Reference |
|---|---|---|
| Linux | Enumeration (LinPEAS/LinEnum/pspy/exploit-suggester) | `references/linux-privesc.md` |
| Linux | SUID/SGID + GTFOBins | `references/linux-privesc.md` |
| Linux | sudo misconfig (`sudo -l`, GTFOBins, CVEs) | `references/linux-privesc.md` |
| Linux | cron / wildcard / PATH abuse | `references/linux-privesc.md` |
| Linux | writable `/etc/passwd` & `/etc/shadow` | `references/linux-privesc.md` |
| Linux | capabilities (`getcap`) | `references/linux-privesc.md` |
| Linux | NFS `no_root_squash` | `references/linux-privesc.md` |
| Linux | docker / lxd / disk group | `references/linux-privesc.md` |
| Linux | LD_PRELOAD / LD_LIBRARY_PATH / .so hijack | `references/linux-privesc.md` |
| Linux | kernel/component CVEs (PwnKit, DirtyPipe, DirtyCOW, Looney Tunables) | `references/linux-privesc.md` |
| Windows | Enumeration (WinPEAS/PowerUp/Seatbelt/SharpUp/accesschk) | `references/windows-privesc.md` |
| Windows | Unquoted service paths | `references/windows-privesc.md` |
| Windows | Weak service / registry ACLs, binary/PATH hijack | `references/windows-privesc.md` |
| Windows | AlwaysInstallElevated | `references/windows-privesc.md` |
| Windows | DLL search-order hijack | `references/windows-privesc.md` |
| Windows | Token impersonation (SeImpersonate → Potato family) | `references/windows-privesc.md` |
| Windows | Privilege abuse (SeBackup/SeRestore/SeDebug/SeTakeOwnership) | `references/windows-privesc.md` |
| Windows | UAC bypass (concepts) | `references/windows-privesc.md` |
| Windows | Autoruns / scheduled tasks | `references/windows-privesc.md` |
| Windows | Credential hunting (registry, SAM, unattend/GPP, stored creds) | `references/windows-privesc.md` |

Public sources and URLs: `references/sources.md`.

## Workflow

1. **Establish context.** Who am I, where am I, what can I reach?
   - Linux: `id`, `whoami`, `hostname`, `uname -a`, `cat /etc/os-release`, `sudo -l`,
     `groups`, `env`, `ps aux`.
   - Windows: `whoami /all` (user, groups, **privileges**), `systeminfo`, `hostname`,
     `net user`, `net localgroup administrators`, `cmdkey /list`.
2. **Enumerate broadly (automated + manual).** Run one automated tool for coverage
   (LinPEAS / WinPEAS or PowerUp), but **read the output** — confirm each candidate
   manually before acting. Do not blindly execute suggested exploits.
3. **Rank candidates by safety and reliability.** Prefer misconfiguration paths (SUID
   GTFOBins, sudo, service-ACL, token impersonation) that are **deterministic and
   non-destructive** over kernel exploits that can crash the host. Kernel/component CVEs
   are last resort and DETECT-ONLY unless RoE permits running them.
4. **Validate the chosen path safely.** Execute the least-intrusive PoC. For a service
   or DLL hijack, use a benign payload that just spawns a proof shell / writes a
   controlled marker — not a destructive one.
5. **Prove and stop.** Capture `id` / `whoami /priv` as SYSTEM/root. Do not go further.
6. **Clean up and report.** Restore all changes, log them, then write up with
   `security-reporting`: finding, evidence, safe repro, CVE/CWE, detection, remediation.

## How to pick a technique fast

- **Linux, got `sudo -l` output?** → check every allowed binary/path against **GTFOBins**
  first (fastest, cleanest win).
- **Linux, SUID root binary that isn't standard?** → GTFOBins the binary name.
- **Windows, `whoami /priv` shows `SeImpersonatePrivilege` Enabled?** → Potato family
  (PrintSpoofer/GodPotato first — they work on modern builds).
- **Windows, a service you can reconfigure or whose binary/dir you can write?** →
  service-ACL / unquoted-path / binary hijack.
- **Either OS, nothing obvious?** → run the exploit-suggester, but treat kernel hits as
  **detect-and-report**, not auto-exploit.

## Related skills

- `active-directory-attack-paths` — **domain**-level escalation (Kerberoasting, ACL
  abuse, DCSync, delegation, coercion). This skill escalates the *local host*; that one
  escalates the *domain*. Escalating a domain-joined host to local SYSTEM (e.g. via a
  Potato) often feeds directly into that skill's credential-access steps (LSASS/SAM).
- `network-service-exploitation` — how you often *get* the initial foothold (weak
  service creds, exposed datastores) before you escalate here.
- `windows-ad-cve-exploitation` / `cve-knowledge-base` — deeper CVE fingerprinting and
  the KEV/EPSS prioritization workflow for the kernel/component CVEs referenced here.
- `container-supply-chain-security` — full treatment of container **escape** (the
  docker-group / docker.sock path here is the lightweight version).
- `security-reporting` — CVSS scoring and write-up templates for local-privesc findings.
