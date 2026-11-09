---
name: active-directory-attack-paths
description: "Operational playbook for authorized Active Directory / internal network penetration testing and audit. Covers the full internal kill chain with concrete commands (Impacket, NetExec/CrackMapExec, BloodHound, Rubeus, Certipy, Responder, mimikatz): unauthenticated recon (LDAP anonymous, SMB null/guest, user enumeration, RID cycling), initial-access poisoning (LLMNR/NBT-NS/mDNS via Responder, IPv6/mitm6 DNS takeover), NTLM relay (ntlmrelayx, LDAP/S, SMB), password spraying & policy-aware guessing, Kerberos attacks (Kerberoasting, AS-REP roasting, Kerberoast-without-preauth, ticket forging golden/silver/diamond), AD CS certificate abuse (ESC1–ESC14, Certifried), ACL/DACL abuse (GenericAll, GenericWrite, WriteDACL, WriteOwner, AddMember, ForceChangePassword, shadow credentials/msDS-KeyCredentialLink), delegation abuse (unconstrained, constrained, resource-based/RBCD), coercion (PetitPotam, PrinterBug/SpoolSample, DFSCoerce, ShadowCoerce), credential access (DCSync, SAM/LSA/LSASS, DPAPI, NTDS.dit), lateral movement (Pass-the-Hash/Ticket, overpass-the-hash, WMI/WinRM/PsExec/SMBexec), GPO abuse, trust attacks (SID history, cross-forest), MSSQL & LAPS/gMSA, and persistence. Includes BloodHound path analysis, an attack-decision flow, detection/OPSEC notes, and remediation for reports. Use when planning or executing an internal/AD pentest, escalating from a foothold to Domain Admin on an authorized engagement, choosing the right tool/command for an AD technique, or writing AD findings with remediation."
version: 1.0.0
triggers:
  - active directory pentest
  - AD pentest
  - internal pentest
  - domain admin
  - kerberoasting
  - AS-REP roasting
  - NTLM relay
  - LLMNR poisoning
  - responder
  - mitm6
  - bloodhound
  - ACL abuse
  - DCSync
  - ADCS
  - certipy
  - ESC1
  - shadow credentials
  - RBCD
  - unconstrained delegation
  - pass the hash
  - pass the ticket
  - password spraying
  - petitpotam
  - golden ticket
  - lateral movement
  - netexec
  - crackmapexec
  - impacket
---

# Active Directory Attack Paths (Authorized Internal Testing)

Playbook for taking an authorized internal engagement from zero access to Domain
Admin and documenting every step for the client. Commands assume a Linux attack
host with Impacket, NetExec (`nxc`), BloodHound, Certipy, Responder, and a Windows
foothold when needed (Rubeus/mimikatz/PowerView).

## ⚠️ Authorization gate — read first

This skill inherits **`safe-testing-doctrine`** (hard limits: no DoS/DDoS, no
destruction, no lockout storms, no impact on real users, scope-only,
least-intrusive PoC, full cleanup). Load it before testing.

- Only run against systems explicitly in the signed scope / rules of engagement.
- **Poisoning (Responder/mitm6) and relay attacks affect the live network** —
  confirm they are permitted, run in analyze mode first, and avoid business-hours
  disruption. Coordinate coercion/relay with the client.
- Use benign markers, clean up added objects/ACLs/tickets, and log every action
  with timestamps so the client can audit and so findings are reproducible.
- Do not disrupt production (no mass account lockouts — respect lockout
  thresholds when spraying; no DC crashes). Stop and check in for anything
  destructive.

## Kill-chain map → reference files

| Stage | Techniques | Reference |
|---|---|---|
| 0. Recon (unauth) | LDAP anon, SMB null, user enum, RID cycle, SMB signing | `references/recon-and-enum.md` |
| 1. Initial creds | LLMNR/NBT-NS/mDNS poisoning, mitm6, NTLM relay, spraying | `references/initial-access.md` |
| 2. Kerberos | Kerberoast, AS-REP roast, ticket forging | `references/kerberos-attacks.md` |
| 3. AD CS | ESC1–ESC14, Certifried, relay-to-CA | `references/adcs.md` |
| 4. ACL/object | GenericAll/Write, WriteDACL, shadow creds, GPO | `references/acl-and-object-abuse.md` |
| 5. Delegation | unconstrained, constrained, RBCD, coercion | `references/delegation-and-coercion.md` |
| 6. Credentials | DCSync, LSASS/SAM/LSA, DPAPI, NTDS.dit, LAPS/gMSA | `references/credential-access.md` |
| 7. Lateral move | PtH/PtT, overpass, WMI/WinRM/PsExec, MSSQL | `references/lateral-movement.md` |
| 8. Domain/forest | trusts, SID history, persistence | `references/domain-dominance.md` |
| BloodHound | collection + path analysis | `references/bloodhound.md` |

## How to use this skill

1. **Collect BloodHound early** (see `references/bloodhound.md`) — it turns the
   whole environment into a graph and shows the shortest path to DA. Let it drive
   which technique you reach for.
2. Work the kill chain, but **let findings reorder it** — an AS-REP-roastable
   user or an ESC1 template can jump you straight ahead.
3. Validate access at each hop (`nxc smb <host> -u u -p p`), capture evidence,
   and keep an inventory of every credential/ticket/ACL you obtain.
4. Write findings with the remediation notes in each reference.

## First-15-minutes checklist (from an in-scope foothold or network position)

```bash
# No creds yet — passive + light active recon
nxc smb <subnet/24>                             # host discovery, signing, OS, domain
responder -I eth0 -A                             # ANALYZE mode: see what would poison
nxc ldap <DC> -u '' -p '' --users               # anonymous LDAP bind?
nxc smb <DC> -u '' -p ''                         # null session
enum4linux-ng -A <DC>

# With any valid cred (user:pass or hash)
nxc smb <DC> -u user -p pass                     # validate + domain info
nxc ldap <DC> -u user -p pass --bloodhound -c all --dns-server <DC>
nxc ldap <DC> -u user -p pass --kerberoasting kerb.txt
nxc ldap <DC> -u user -p pass --asreproast asrep.txt
nxc smb <DC> -u user -p pass --pass-pol         # lockout threshold BEFORE spraying
```

## Attack-decision quick flow

- **No creds, on-net** → poisoning/relay (`initial-access.md`) or anon enum.
- **Valid creds** → BloodHound → Kerberoast/AS-REP → ACL paths → ADCS.
- **Local admin on a box** → dump creds (`credential-access.md`) → PtH lateral.
- **Coercible DC + relay target** → PetitPotam→ADCS/RBCD (`delegation-and-coercion.md`).
- **DA / DCSync rights** → dump domain, then document persistence risks.

## Core toolbox

NetExec (`nxc`), Impacket (`GetUserSPNs`, `GetNPUsers`, `secretsdump`,
`ntlmrelayx`, `getST`, `psexec/wmiexec/smbexec`), BloodHound + SharpHound/
bloodhound-python, Certipy, Rubeus, PowerView/PowerSploit, mimikatz, Responder,
mitm6, Coercer, hashcat/john. Prefer the quietest option that proves the path
(see OPSEC notes in each reference).
