# Sources & provenance

All material below is from public documentation and open-source tooling. Mode numbers
and attack-mode/charset details were verified against the hashcat wiki at authoring
time (2026). Always re-confirm against your local build: `hashcat --example-hashes`.

## hashcat (official)

- **Example hashes / full mode table** — authoritative `-m` number for every hash
  type (source of the modes table): https://hashcat.net/wiki/doku.php?id=example_hashes
- **hashcat wiki — usage, attack modes, mask charsets, workload profiles**
  (`-a 0/1/3/6/7/9`, `?l?u?d?s?a?b`, `-w 1..4`, `-O`):
  https://hashcat.net/wiki/doku.php?id=hashcat
- **Mask attack**: https://hashcat.net/wiki/doku.php?id=mask_attack
- **Rule-based attack** (rule syntax, `--stdout`, `-g`):
  https://hashcat.net/wiki/doku.php?id=rule_based_attack
- **WPA 22000 / hcxtools** (PMKID+EAPOL unified format):
  https://hashcat.net/wiki/doku.php?id=cracking_wpawpa2 and
  https://github.com/ZerBea/hcxtools
- hashcat repository: https://github.com/hashcat/hashcat

## John the Ripper

- Openwall JtR (jumbo) documentation & wiki:
  https://www.openwall.com/john/ and https://github.com/openwall/john
- `*2john` extractors (`zip2john`, `office2john`, `pdf2john`, `rar2john`, `7z2john`,
  `keepass2john`, `unshadow`, `ssh2john`) ship with the jumbo build (`/run/`).
- Rules & modes: https://www.openwall.com/john/doc/RULES.shtml

## Hash identification

- **name-that-hash** (bee-san / HashPals) — 300+ types, prints hashcat & JtR:
  https://github.com/HashPals/Name-That-Hash (Kali: https://www.kali.org/tools/name-that-hash/)
- **hashID** (psypanda) — 220+ types via regex, `-m`/`-j` output:
  https://github.com/psypanda/hashID
- **hash-identifier** (blackploit): https://github.com/blackploit/hash-identifier

## Rules

- **best64.rule**, **dive.rule**, `rockyou-30000.rule`, `toggles*.rule` — ship in
  hashcat `rules/`: https://github.com/hashcat/hashcat/tree/master/rules
- **OneRuleToRuleThemAll** / **OneRuleToRuleThemStill** (Will Hunt / In.security) —
  distilled top-performing ruleset: https://github.com/stealthsploit/OneRuleToRuleThemAll
  and https://in.security/2023/01/10/oneruletorulethemstill-new-and-improved/
- **pantagrule** (real-world compromised-password rules):
  https://github.com/rarecoil/pantagrule

## Wordlists

- **rockyou.txt** — ships with Kali (`/usr/share/wordlists/rockyou.txt.gz`).
- **SecLists** (Passwords/, and JWT secrets list `jwt.secrets.list`):
  https://github.com/danielmiessler/SecLists
- **weakpass** — large curated lists & rules: https://weakpass.com/
- **CeWL** (custom wordlists from a site): https://github.com/digininja/CeWL
- **Mentalist** (GUI wordlist mangler): https://github.com/sc0tfree/mentalist
- **PACK** (policygen/maskgen/statsgen for policy-shaped masks):
  https://github.com/iphelix/pack

## Distributed cracking

- **Hashtopolis** (self-hosted distributed hashcat orchestration):
  https://github.com/hashtopolis/server

## Upstream capture tools (produce the hashes this skill cracks)

- Impacket (`GetUserSPNs.py`, `GetNPUsers.py`, `secretsdump.py`):
  https://github.com/fortra/impacket
- Rubeus (Kerberoast/AS-REP on Windows): https://github.com/GhostPack/Rubeus
- Responder (NetNTLMv1/v2): https://github.com/lgandx/Responder
- NetExec: https://github.com/Pennyw0rth/NetExec

## Standards / handling

- NIST SP 800-115 (Technical Guide to Information Security Testing) — evidence
  handling and offline-analysis discipline.
- Cross-reference: `safe-testing-doctrine` (this base) for the scope/handling/
  destruction rules that bound all cracking activity.
