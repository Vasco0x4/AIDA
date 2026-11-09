# Sources — Public references consulted

All public, vendor/authoritative or well-known community methodology. Consulted while
building this skill; verify current versions/advisories at test time.

## Master lookup tables (used constantly)
- GTFOBins (Linux SUID/sudo/capabilities binary abuse) — https://gtfobins.github.io/
- LOLBAS (Windows living-off-the-land binaries/scripts) — https://lolbas-project.github.io/

## Methodology / checklists
- HackTricks — Linux Privilege Escalation — https://book.hacktricks.wiki/en/linux-hardening/privilege-escalation/
- HackTricks — Windows Local Privilege Escalation — https://book.hacktricks.wiki/en/windows-hardening/windows-local-privilege-escalation/
- HackTricks — RoguePotato/PrintSpoofer/SharpEfsPotato/GodPotato — https://hacktricks.wiki/en/windows-hardening/windows-local-privilege-escalation/roguepotato-and-printspoofer.html
- HackTricks — Abusing Tokens (SeImpersonate/SeBackup/SeDebug) — https://book.hacktricks.wiki/en/windows-hardening/windows-local-privilege-escalation/privilege-escalation-abusing-tokens.html
- PayloadsAllTheThings — Linux Privilege Escalation — https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Methodology%20and%20Resources/Linux%20-%20Privilege%20Escalation.md
- PayloadsAllTheThings — Windows Privilege Escalation — https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/Methodology%20and%20Resources/Windows%20-%20Privilege%20Escalation.md
- MITRE ATT&CK — Privilege Escalation (TA0004) — https://attack.mitre.org/tactics/TA0004/

## Enumeration tooling
- PEASS-ng (LinPEAS / WinPEAS) — https://github.com/peass-ng/PEASS-ng
- LinEnum — https://github.com/rebootuser/LinEnum
- linux-smart-enumeration (lse) — https://github.com/diego-treitos/linux-smart-enumeration
- pspy (unprivileged process/cron snooping) — https://github.com/DominicBreuker/pspy
- linux-exploit-suggester — https://github.com/The-Z-Labs/linux-exploit-suggester
- PowerSploit / PowerUp — https://github.com/PowerShellMafia/PowerSploit (PrivEsc/PowerUp.ps1)
- Seatbelt — https://github.com/GhostPack/Seatbelt
- SharpUp — https://github.com/GhostPack/SharpUp
- Sysinternals accesschk / Autoruns — https://learn.microsoft.com/en-us/sysinternals/downloads/accesschk
- Windows Exploit Suggester - Next Gen (wesng) — https://github.com/bitsadmin/wesng
- Watson — https://github.com/rasta-mouse/Watson

## Potato family (SeImpersonate → SYSTEM)
- PrintSpoofer (itm4n) — https://github.com/itm4n/PrintSpoofer
- GodPotato (BeichenDream) — https://github.com/BeichenDream/GodPotato
- RoguePotato (antonioCoco) — https://github.com/antonioCoco/RoguePotato
- JuicyPotato (ohpe) — https://github.com/ohpe/juicy-potato
- SigmaPotato (GodPotato fork, 2024–2025) — https://github.com/tylerdotrar/SigmaPotato
- itm4n "PrintSpoofer – Abusing Impersonation Privileges on Windows 10 / Server 2019" — https://itm4n.github.io/printspoofer-abusing-impersonation-privileges/

## Linux CVEs
- PwnKit CVE-2021-4034 (polkit pkexec) — Qualys advisory — https://blog.qualys.com/vulnerabilities-threat-research/2022/01/25/pwnkit-local-privilege-escalation-vulnerability-discovered-in-polkits-pkexec-cve-2021-4034
- NVD CVE-2021-4034 — https://nvd.nist.gov/vuln/detail/CVE-2021-4034 ; Red Hat RHSB-2022-001 — https://access.redhat.com/security/vulnerabilities/RHSB-2022-001
- DirtyPipe CVE-2022-0847 — Max Kellermann writeup — https://dirtypipe.cm4all.com/ ; CISA alert — https://www.cisa.gov/news-events/alerts/2022/03/10/dirty-pipe-privilege-escalation-vulnerability-linux ; JFrog analysis — https://jfrog.com/blog/dirtypipe-cve-2022-0847-the-new-dirtycow/
- Dirty COW CVE-2016-5195 — https://dirtycow.ninja/ ; NVD — https://nvd.nist.gov/vuln/detail/CVE-2016-5195
- Looney Tunables CVE-2023-4911 (glibc ld.so) — Qualys advisory — https://blog.qualys.com/vulnerabilities-threat-research/2023/10/03/cve-2023-4911-looney-tunables-local-privilege-escalation-in-the-glibcs-ld-so ; NVD — https://nvd.nist.gov/vuln/detail/CVE-2023-4911
- Sudo Baron Samedit CVE-2021-3156 — Qualys — https://blog.qualys.com/vulnerabilities-threat-research/2021/01/26/cve-2021-3156-heap-based-buffer-overflow-in-sudo-baron-samedit
- Sudo CVE-2019-14287 — https://nvd.nist.gov/vuln/detail/CVE-2019-14287 ; Sudo CVE-2023-22809 — https://nvd.nist.gov/vuln/detail/CVE-2023-22809
- ly4k/PwnKit (self-contained PoC, incl. check mode) — https://github.com/ly4k/PwnKit

## Windows CVEs / techniques
- PrintNightmare CVE-2021-34527 — https://msrc.microsoft.com/update-guide/vulnerability/CVE-2021-34527
- GPP cpassword / MS14-025 CVE-2014-1812 — https://learn.microsoft.com/en-us/security-updates/securitybulletins/2014/ms14-025
- UACMe (UAC bypass catalog) — https://github.com/hfiref0x/UACME
- Impacket (secretsdump for offline SAM/SYSTEM) — https://github.com/fortra/impacket

## Prioritization / advisories
- CISA Known Exploited Vulnerabilities (KEV) Catalog — https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- FIRST EPSS — https://www.first.org/epss/
- NVD / CVE — https://nvd.nist.gov/

## Standards / doctrine referenced by this skill
- NIST SP 800-115 (Technical Guide to Information Security Testing) — https://csrc.nist.gov/pubs/sp/800/115/final
- PTES (Penetration Testing Execution Standard) — http://www.pentest-standard.org/
