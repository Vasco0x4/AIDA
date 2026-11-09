# Stage 8 — Domain / Forest Dominance, Trusts & Persistence

Once at Domain Admin (or equivalent), the goal is to **document blast radius and
persistence risk** for the report — not to entrench. Demonstrate, clean up, and
advise.

## Enumerate trusts
```bash
nxc ldap <DC> -u user -p pass -M enum_trusts
netexec ldap <DC> -u user -p pass --query "(objectClass=trustedDomain)" ""
# BloodHound shows trust edges and cross-domain paths.
```
Note direction (inbound/outbound/bidirectional), transitivity, and SID filtering
status — these decide whether child→parent / cross-forest escalation is possible.

## Child → parent / forest escalation
Within a forest there is no security boundary between domains. From child-domain
DA to Enterprise Admin:
- **SID history injection** — forge a golden ticket including the Enterprise
  Admins SID of the parent (needs child `krbtgt`):
```bash
ticketer.py -nthash <child_krbtgt> -domain-sid <child_SID> \
  -extra-sid <parent_SID>-519 -domain child.corp.local Administrator
```
- **Trust key / inter-realm TGT** — use the trust account hash to forge a referral
  ticket across the trust.
- **KRBTGT of child** enables full parent access via extra-SID (above).

## Cross-forest (where trust + no SID filtering)
- Kerberoast/abuse across a bidirectional forest trust; foreign group memberships
  and ACLs (BloodHound "ForeignGroupMembership") can grant access without full DA.
- SID filtering usually blocks SID-history across forests — verify before claiming.

## Persistence techniques (document as risk; do not leave active)
- **Golden ticket** (`krbtgt` hash) — forge any TGT anytime → rotate krbtgt twice
  to remediate. (kerberos-attacks.md)
- **Silver ticket** — per-service, stealthy, survives krbtgt rotation.
- **Diamond ticket** — modified real TGT, better OPSEC.
- **DCSync backdoor via ACL** — grant a low-priv user replication rights.
- **AdminSDHolder** — write to the ACL that reapplies to protected groups every
  hour → durable rights on Domain Admins.
- **Golden certificate** — stolen CA key forges auth certs (adcs.md).
- **Skeleton key**, **DSRM password**, malicious GPO, and computer-account
  backdoors — all high-severity persistence to flag.

For each, in the report: how it was possible, detection guidance, and cleanup
performed. Actually remove test artifacts (added SIDs, ACLs, tickets, computer
accounts, GPO edits) at engagement end and give the client a cleanup list.

## Full domain proof (evidence)
```bash
secretsdump.py corp.local/DA:pass@<DC> -just-dc     # hash dump = decisive proof
# 'nxc smb <DC> -u DA -p pass' Pwn3d on the DC + a DA-only file read.
```

## OPSEC / ethics
This is the most sensitive phase — minimize dwell, never exfiltrate real data,
protect the hash dump as crown-jewel evidence (encrypt/delete), and keep the
client informed if you reach DA earlier than expected.

## Remediation to recommend
Treat the forest as the security boundary (separate sensitive assets into their
own forest); enable SID filtering / selective auth on trusts; rotate `krbtgt`
twice and on any DA compromise; monitor golden/silver-ticket indicators and
AdminSDHolder/DCSync ACL changes; tiered admin model; regular BloodHound-based
attack-path audits.
