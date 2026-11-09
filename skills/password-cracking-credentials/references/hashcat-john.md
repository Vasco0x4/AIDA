# hashcat & John the Ripper — modes, strategy, rules, masks, tuning

All `-m` mode numbers below are from the official hashcat **example_hashes** wiki
page (see `sources.md`). When in doubt, verify against your local build:
`hashcat --help | grep -i <keyword>` or `hashcat --example-hashes -m <n>`.

---

## 1. Hash identification

### Tools (all print the hashcat `-m` and John format)

```bash
# name-that-hash (nth) — modern, fast, ranks by likelihood
nth -f hashes.txt            # from file
echo -n '<hash>' | nth       # from stdin
nth -t '<hash>'              # single text hash

# hashid — regex-based, 220+ types; -m = hashcat mode, -j = john format
hashid -mj '<hash>'
hashid -mj -o out.txt hashes.txt

# hash-identifier (interactive, older); John also self-detects on load
john hashes.txt              # jumbo autodetects the format for many types
```

Treat tool output as **candidates**. A bare 32-hex string matches NTLM (1000),
raw-MD5 (0), MD4 (900), LM half, and more — **origin decides**. Salted/encoded
formats (those with `$...$` structure or a known prefix) are unambiguous.

### Format cues — recognize by shape

| Cue / prefix | Type | hashcat `-m` |
|---|---|---|
| 32 hex chars, from SAM/NTDS/`secretsdump` | NTLM | 1000 |
| `aad3b435...:` half or 32-hex LM | LM | 3000 |
| `$krb5tgs$23$*user$REALM*...` | Kerberoast RC4 | 13100 |
| `$krb5tgs$17$...` / `$krb5tgs$18$...` | Kerberoast AES128 / AES256 | 19600 / 19700 |
| `$krb5asrep$23$user@REALM:...` | AS-REP roast (RC4) | 18200 |
| `user::DOMAIN:...:...:...` (8-part) | NetNTLMv1 | 5500 |
| `user::DOMAIN:serverchallenge:HMAC:blob` | NetNTLMv2 | 5600 |
| `WPA*02*<mic>*<mac_ap>*...` (hashcat 22000 line) | WPA-PBKDF2-PMKID+EAPOL | 22000 |
| `$1$...` | md5crypt (Cisco/Unix) | 500 |
| `$2a$ / $2b$ / $2y$` | bcrypt | 3200 |
| `$5$...` | sha256crypt | 7400 |
| `$6$...` | sha512crypt | 1800 |
| `$P$ / $H$` | phpass (WordPress/phpBB) | 400 |
| `<header>.<payload>.<sig>` (base64url, dots) | JWT (HS256/384/512) | 16500 |
| `$keepass$*...` | KeePass 1/2 | 13400 |
| `$office$*2013*...` etc | MS Office | 9400/9500/9600 |
| `$pkzip2$ / $zip2$` | PKZIP / WinZip | 17200 / 13600 |
| `$7z$...` | 7-Zip | 11600 |
| `$RAR3$ / $rar5$` | RAR3-hp / RAR5 | 12500 / 13000 |
| `$pdf$...` | PDF | 10500 / 10700 |
| `$sshng$` | SSH private key | 22921 (john: `SSH`) |

---

## 2. Common hashcat modes — verified table

| `-m` | Hash type | Speed | Typical source |
|---|---|---|---|
| **0** | raw MD5 | very fast | web app |
| **100** | raw SHA1 | very fast | web app |
| **1400** | raw SHA256 | fast | web app |
| **1000** | **NTLM** | very fast | SAM / NTDS.dit / LSASS |
| **3000** | **LM** | very fast | legacy SAM |
| **5500** | **NetNTLMv1** (+ESS) | very fast | Responder / relay |
| **5600** | **NetNTLMv2** | very fast | Responder / relay |
| **13100** | **Kerberoast** TGS-REP **RC4** | very fast | AD (Rubeus/GetUserSPNs) |
| **19600** | **Kerberoast** TGS-REP **AES128** | fast | AD |
| **19700** | **Kerberoast** TGS-REP **AES256** | fast | AD |
| **18200** | **AS-REP roast** (etype 23 / RC4) | very fast | AD (no-preauth users) |
| **7500** | Kerberos 5 AS-REQ Pre-Auth (RC4) | fast | AD |
| **19800 / 19900** | Kerberos 5 AS-REQ Pre-Auth AES128 / AES256 | fast | AD |
| **22000** | **WPA-PBKDF2-PMKID+EAPOL** (replaces 2500/16800) | slow | Wi-Fi handshake / PMKID |
| **16500** | **JWT** (HS256/384/512) | fast | web app / API token |
| **500** | md5crypt `$1$` | slow | Unix / Cisco IOS |
| **1800** | **sha512crypt** `$6$` | slow | Linux `/etc/shadow` |
| **7400** | sha256crypt `$5$` | slow | Linux `/etc/shadow` |
| **3200** | **bcrypt** `$2*$` | **very slow** | web app (best practice) |
| **400** | phpass (WP/phpBB/Joomla) | slow | CMS |
| **1500** | descrypt (DES crypt) | fast | legacy Unix |
| **14600** | LUKS v1 | very slow | disk encryption |
| **7100** | macOS PBKDF2-SHA512 (10.8+) | very slow | macOS |
| **13400** | **KeePass 1/2** | very slow | KeePass `.kdbx` |
| **9400 / 9500 / 9600** | MS Office 2007 / 2010 / 2013 | slow | Office docs |
| **10500 / 10700** | PDF 1.4-1.6 / 1.7 L8 | slow / very slow | PDF |
| **17200** | PKZIP (compressed) | fast | ZIP |
| **13600** | WinZip (AES) | slow | ZIP |
| **11600** | 7-Zip | very slow | 7z |
| **12500 / 13000** | RAR3-hp / RAR5 | slow / very slow | RAR |
| **300** | MySQL4.1+ (`SHA1(SHA1())`) | fast | database |
| **11200** | MySQL5 challenge-response | fast | database |
| **12** | PostgreSQL | fast | database |
| **131 / 1731** | MSSQL (2000 / 2012-2014) | fast | database |

> **AES > RC4 for defenders:** if you have a choice of Kerberoast ticket, RC4 (13100)
> cracks orders of magnitude faster than AES (19600/19700). Request RC4 where the
> account allows it; otherwise you're stuck with the slow AES modes.

---

## 3. Attack modes (`-a`)

| `-a` | Name | Use |
|---|---|---|
| **0** | Straight (dictionary) | wordlist, optionally with `-r rules` |
| **1** | Combination | concatenate two wordlists word-by-word |
| **3** | Brute-force / **Mask** | `?l?l?l?d?d?d...` charset masks |
| **6** | Hybrid Wordlist + Mask | `word` + `?d?d?d` appended |
| **7** | Hybrid Mask + Wordlist | `?d?d?d` prepended + `word` |
| **9** | Association | one-candidate-per-hash (e.g. username == password) |

Built-in **mask charsets**: `?l` a-z · `?u` A-Z · `?d` 0-9 · `?h` 0-9a-f · `?H`
0-9A-F · `?s` special (space + ``!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~``) · `?a` = l+u+d+s
· `?b` 0x00-0xff. Custom sets: `-1 ?l?u -2 ?d?s` then use `?1 ?2` in the mask.

---

## 4. Attack strategy — the ordering ladder

Run the **cheapest attack that is likely to work first**, escalate only as your time
budget allows. Fast hashes justify huge keyspaces; slow hashes (bcrypt, sha512crypt,
KeePass, WPA, 7z) demand **frugality** — targeted small attacks only, brute-force is
usually hopeless.

1. **Straight wordlist** — `rockyou.txt` first, then a bigger list
   (SecLists, weakpass). Cheapest possible.
   ```bash
   hashcat -m 1000 -a 0 hashes.txt rockyou.txt
   ```
2. **Wordlist + rules** — the single highest-ROI step for fast hashes.
   ```bash
   hashcat -m 1000 -a 0 hashes.txt rockyou.txt -r rules/best64.rule        # cheap, ~77 rules
   hashcat -m 1000 -a 0 hashes.txt rockyou.txt -r OneRuleToRuleThemAll.rule # ~52k rules, big
   ```
3. **Targeted mask** from the observed/known **password policy** (e.g. "min 8, must
   have upper+digit"): model `Capitalized + word + Year/!`.
   ```bash
   # e.g. Companyname + 2 digits + special:  Season2024!
   hashcat -m 1000 -a 3 hashes.txt -1 '!@#$' '?u?l?l?l?l?l?d?d?1'
   ```
4. **Pure brute-force mask** — only for short/fast hashes. Estimate keyspace first
   (§7); anything past ~8 mixed chars on a slow hash is infeasible.
   ```bash
   hashcat -m 1000 -a 3 hashes.txt ?a?a?a?a?a?a?a --increment
   ```
5. **Hybrid** — wordlist stems with appended/prepended masks (people love `word2024!`).
   ```bash
   hashcat -m 1000 -a 6 hashes.txt rockyou.txt '?d?d?d?d'   # word + 4 digits
   hashcat -m 1000 -a 7 hashes.txt '?d?d' rockyou.txt       # 2 digits + word
   ```
6. **Combinator** — two curated lists (e.g. `adjectives` × `nouns`, or company terms
   × years).
   ```bash
   hashcat -m 1000 -a 1 hashes.txt list1.txt list2.txt
   ```

**When to use which:** fast hash + no policy info -> wordlist + `OneRule`. Known
policy -> targeted mask/hybrid. Slow hash -> small targeted wordlist + `best64` only.
Company/CTF context -> CeWL/combinator on scraped terms. Re-crack a large NTDS set ->
run recovered plaintexts back as a wordlist (people reuse patterns across a domain).

---

## 5. Rules

Rules mutate each wordlist candidate (capitalize, append digits, leetspeak, etc.),
multiplying coverage cheaply — the best value on fast hashes.

| Rule file | Size | When |
|---|---|---|
| `best64.rule` (ships with hashcat) | ~77 rules | first pass, slow hashes, quick wins |
| `rockyou-30000.rule` | 30k | medium budget |
| `dive.rule` (ships) | large | thorough, fast hashes |
| **`OneRuleToRuleThemAll.rule`** | ~52k | best single general-purpose ruleset (Will Hunt; distilled from top-performing hashcat rules against a 4.3M-hash test set) |
| `OneRuleToRuleThemStill.rule` | trimmed | same crack rate, faster |
| `unix-ninja-leetspeak.rule` | small | leet-heavy targets |

```bash
# stack multiple rule files (cartesian product — grows fast)
hashcat -m 1000 -a 0 hashes.txt wordlist.txt -r best64.rule -r toggles1.rule
# generate random rules on the fly for a slow hash where you want variety cheaply
hashcat -m 1000 -a 0 hashes.txt wordlist.txt -g 5000
# debug what a rule produces
hashcat --stdout wordlist.txt -r best64.rule | less
```
John equivalent: rules live in `john.conf` under `[List.Rules:...]`; invoke with
`john --wordlist=rockyou.txt --rules=Jumbo hashes.txt`.

---

## 6. Masks — building targeted brute-force

- **Charset masks** describe structure, not content. `?u?l?l?l?l?l?d?d` = one upper,
  five lower, two digits (e.g. `Summer24`).
- **Derive masks from the password policy.** If the domain forces upper+lower+digit,
  min length 8, most users satisfy it minimally: `Word` + `##` + `!`. Model that,
  don't brute the whole `?a` space.
- **`--increment`** walks lengths (`--increment-min 6 --increment-max 10`).
- **Custom charsets** narrow the space: `-1 '?d!@#$'` then `?u?l?l?l?l?1?1`.
- **`hcmask` files** let you queue many masks (one per line) for `-a 3`.
- **Common-mask lists** (e.g. from a prior crack: `hashcat --show ... -o` then
  `PACK`'s `maskgen`/`policygen`, or the `rockyou.hcmask` shipping in some distros)
  prioritize the masks that historically crack the most per unit time.

---

## 7. Keyspace estimation (before you waste GPU-days)

Keyspace = (charset size)^length. Time = keyspace / hashrate.

```bash
hashcat -b -m 1000          # benchmark this mode -> hashes/sec (H/s)
hashcat -m 1000 -a 3 hashes.txt ?a?a?a?a?a?a?a?a --keyspace   # print candidate count
```

Worked example: `?a` = 95 chars. 8 chars = 95^8 ≈ 6.6×10^15. On a GPU doing NTLM at
~100 GH/s (10^11 H/s): ~6.6×10^4 s ≈ **18 hours**. The same 8-char `?a` against
**bcrypt** at ~20 kH/s (2×10^4 H/s) would take ~**10,000 years** — which is exactly
why bcrypt is a good defense and why you attack slow hashes with *wordlists/rules*,
never pure brute-force. Always benchmark, compute, and decide **before** launching a
long mask.

---

## 8. GPU vs CPU, tuning, benchmarking

- **GPU (hashcat) for the parallel-friendly modes** — NTLM, NetNTLMv2, Kerberoast,
  MD5/SHA, WPA. Massive speedups (100x-1000x over CPU).
- **CPU (John jumbo) shines** on some formats hashcat lacks or where the format is
  inherently serial, and for its rich `*2john` ecosystem. Many workflows extract with
  a `*2john` tool, then crack with **hashcat** for GPU speed.
- **Workload profile** `-w 1..4` (Low / Default / High / **Nightmare**). Use `-w 3`
  or `-w 4` on a **dedicated** cracking box; `-w 1/2` if the machine is also doing
  other work. `-w 4` maximizes throughput but makes the desktop unresponsive.
- **Optimized kernels** `-O` (limits max password length, big speedup) — safe when
  your candidates are short; drop it if you need long passwords.
- **`-S`** slow-candidate mode helps some slow hashes; `--force` bypasses warnings
  (avoid on real runs). Set `-d 1,2` to pick devices; `--status --status-timer 10`
  for progress.
- **Benchmark first:** `hashcat -b` (all modes) or `hashcat -b -m <n>` (one). Drives
  your keyspace math and the go/no-go on masks.

---

## 9. Potfile management

hashcat auto-writes cracked results to `~/.local/share/hashcat/hashcat.potfile`
(`hash:plaintext`). This is a **sensitive credential store** — encrypt it, never
commit it, wipe it at engagement end.

```bash
hashcat -m 1000 hashes.txt wordlist.txt                 # cracked lines go to potfile
hashcat -m 1000 hashes.txt --show                       # show already-cracked from potfile
hashcat -m 1000 hashes.txt --left                       # show still-uncracked
hashcat -m 1000 hashes.txt wordlist.txt --potfile-path engagement.pot  # isolate per-engagement
hashcat ... --potfile-disable                           # don't persist (ephemeral)
# export cracked user:pass for reporting stats (then destroy)
hashcat -m 1000 hashes.txt --show --username -o cracked.txt
```
John: cracked go to `~/.john/john.pot`; view with `john --show hashes.txt`.

**Feedback loop:** dump cracked plaintexts (`awk -F: '{print $2}' cracked.txt | sort -u
> found.txt`) and reuse `found.txt` as a wordlist (+`best64`) against the remaining
`--left` hashes — domain users reuse each other's patterns.

---

## 10. Distributed / scale concepts

For large NTDS sets or slow hashes, spread work across GPUs/hosts by **splitting the
keyspace**, not by re-running the same attack:

- `-s <skip> -l <limit>` slices a straight/mask attack's keyspace across nodes.
- `--keyspace` gives the total to divide.
- Orchestrators: **Hashtopolis** (server + agents) coordinates many crackers and
  merges potfiles; keep it **on infrastructure you control** (never third-party) to
  honor the "no external cracking services" rule.
- Reuse potfiles across the fleet so a crack on one node stops the others repeating it.
