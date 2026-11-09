# Sources / Provenance — active-directory-attack-paths

This skill synthesizes public, reputable AD-security research and tooling
documentation. Patterns and methodology, not private engagement data.

## Methodology & knowledge bases
- The Hacker Recipes (AD) — https://www.thehacker.recipes/
- HackTricks (Active Directory) — https://book.hacktricks.xyz/windows-hardening/active-directory-methodology
- MITRE ATT&CK (Credential Access / Lateral Movement / etc.) — https://attack.mitre.org/
- Microsoft AD security docs & Tiered admin model — https://learn.microsoft.com/

## Core research
- SpecterOps — BloodHound & "Certified Pre-Owned" (AD CS / ESC1–ESC8) — https://posts.specterops.io/ ; https://specterops.io/wp-content/uploads/sites/3/2022/06/Certified_Pre-Owned.pdf
- dirkjanm.io — relay, mitm6, delegation, RBCD, coercion research — https://dirkjanm.io/
- harmj0y / Will Schroeder — Kerberoasting, ACL abuse, delegation — https://blog.harmj0y.net/
- Elad Shamir — "Wagging the Dog" (RBCD / S4U) — https://shenaniganslabs.io/
- Certipy / ly4k — AD CS abuse — https://github.com/ly4k/Certipy
- Shadow credentials (msDS-KeyCredentialLink) — Elad Shamir "Whisker"/pyWhisker research

## Tooling docs
- Impacket — https://github.com/fortra/impacket
- NetExec (nxc) — https://www.netexec.wiki/
- BloodHound / SharpHound / bloodhound-python — https://bloodhound.readthedocs.io/
- Certipy, Rubeus, mimikatz, Responder, mitm6, Coercer, Certifried,
  targetedKerberoast, bloodyAD, PetitPotam, printerbug — respective project repos.

## Specific coercion / delegation techniques
- PetitPotam (topotam), PrinterBug/SpoolSample (@tifkin_), DFSCoerce (Wh04m1001),
  ShadowCoerce — public PoC repositories.

> AD CVEs (Zerologon, PrintNightmare, noPac, Certifried, PetitPotam CVEs) and their
> patch details are covered with citations in the sibling skill
> `windows-ad-cve-exploitation/references/sources.md`. Verify tool behavior and
> scope before use.
