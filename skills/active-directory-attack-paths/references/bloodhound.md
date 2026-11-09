# BloodHound — Collection & Path Analysis

BloodHound graphs every principal, ACL, session, and delegation into attack
paths. Collect it early; let it drive technique choice.

## Collection
```bash
# From Linux, with any domain creds (no agent on target):
bloodhound-python -u user -p pass -d corp.local -ns <DC_IP> -c All --zip
# NetExec built-in collector:
nxc ldap <DC> -u user -p pass --bloodhound -c all --dns-server <DC_IP>
# From a Windows foothold:
SharpHound.exe -c All --zippasswd <pw>
# Also collect sessions/loggedon over time for better paths:
bloodhound-python ... -c Session,LoggedOn
```
Use **BloodHound Community Edition** (or legacy) and import the zip. Certipy can
feed ADCS data into BloodHound CE for certificate paths.

## Highest-value queries / analysis
- **Shortest Paths to Domain Admins** (built-in) — your primary escalation map.
- **Shortest Paths from Owned Principals** — mark everything you control as Owned,
  then let it compute the route to DA.
- Kerberoastable / AS-REP-roastable users (jump straight to kerberos-attacks.md).
- Principals with DCSync (`GetChanges`+`GetChangesAll`) on the domain.
- Dangerous ACL edges: GenericAll, GenericWrite, WriteDACL, WriteOwner,
  AddKeyCredentialLink, ForceChangePassword, AddMember, Owns.
- Unconstrained / constrained / RBCD delegation nodes.
- Computers where Owned users have admin (lateral-movement targets).
- Shortest path to high-value targets (DCs, ADCS, Exchange, tier-0 servers).

## Reading an edge → the action
| Edge | Go to |
|---|---|
| MemberOf / AddMember | acl-and-object-abuse.md (group add) |
| GenericAll/Write, WriteDACL/Owner | acl-and-object-abuse.md |
| AddKeyCredentialLink | shadow credentials (acl-and-object-abuse.md) |
| ForceChangePassword | acl-and-object-abuse.md |
| CanRDP / AdminTo / CanPSRemote | lateral-movement.md |
| AllowedToDelegate / AllowedToAct | delegation-and-coercion.md |
| DCSync / GetChangesAll | credential-access.md |
| ADCS ESC edges (BHCE) | adcs.md |
| HasSession | harvest creds where a privileged user is logged on |

## Workflow
1. Collect → mark Owned nodes → run "Paths from Owned to DA".
2. Pick the shortest path with the lowest-noise edges.
3. Execute each edge with the matching reference; re-mark newly owned nodes.
4. Re-run the query as you gain control — paths shorten each hop.

## Reporting with BloodHound
Export the specific path graph as evidence; it communicates risk to clients far
better than text. Recommend they run BloodHound themselves periodically and
remediate the shortest paths (usually a handful of ACL edges) to break most
routes to DA.
