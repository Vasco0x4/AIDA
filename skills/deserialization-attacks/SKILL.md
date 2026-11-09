---
name: deserialization-attacks
description: "Cross-language playbook for authorized testing of INSECURE DESERIALIZATION — one of the highest-impact web/app bug classes (frequently unauthenticated RCE). Covers how to RECOGNIZE serialized data on the wire (Java `ac ed`/`rO0` base64, PHP `O:`/`a:`, Python pickle opcodes, .NET ViewState/`AAEAAAD`, Ruby Marshal `\\x04\\x08`, YAML/XML), where it ENTERS (cookies, params, ViewState, headers, message queues, caches, model files, APIs), gadget-chain tooling (ysoserial, ysoserial.net, phpggc, marshalsec), SAFE benign proof-of-concept (id/whoami/DNS callback only), detection (dangerous sinks readObject/unserialize/pickle.loads/BinaryFormatter/Marshal.load/yaml.load/TypeNameHandling), and remediation (allow-lists, data-only formats, look-ahead deserialization, ViewState MAC/machineKey). Includes .NET ViewState (__VIEWSTATE, machineKey, Blacklist3r), Java JNDI + Commons-Collections gadgets (links to web-cve-exploitation / Log4Shell), SnakeYAML & XStream, and notable CVEs (CVE-2015-4852 WebLogic T3, CVE-2017-9805 Struts REST XStream, CVE-2019-18935 Telerik, CVE-2017-5941 node-serialize, CVE-2019-5420 Rails, CVE-2022-1471 SnakeYAML). Authorized, in-scope engagements only. Use for insecure deserialization, object injection, POP/gadget chains, or writing deser findings with remediation."
version: 1.0.0
triggers:
  - insecure deserialization
  - object injection
  - gadget chain
  - pop chain
  - ysoserial
  - ysoserial.net
  - java deserialization
  - readobject
  - commons collections
  - jndi gadget
  - php pop chain
  - phpggc
  - unserialize
  - php object injection
  - python pickle
  - pickle.loads
  - dotnet viewstate
  - __viewstate
  - machinekey
  - blacklist3r
  - binaryformatter
  - typenamehandling
  - json.net deserialization
  - node-serialize
  - ruby marshal
  - marshal.load
  - snakeyaml
  - xstream
  - yaml deserialization
---

# Insecure Deserialization Attacks (cross-language)

Serialization turns an in-memory object into bytes; deserialization rebuilds it. When an
application rebuilds **attacker-controlled bytes** with a native, type-carrying
deserializer, the attacker doesn't just inject *data* — they inject the **object graph**,
including which classes get instantiated and which methods run during reconstruction.
Chaining already-present library classes ("gadgets") into that reconstruction produces
**remote code execution**, usually pre-auth. This is why OWASP tracks it as a top-tier
class (A08:2021 – Software and Data Integrity Failures).

This skill is **recognize → tool/gadget → SAFE proof → real CVE → detect → remediate**,
per language. It is for **authorized, scoped** engagements only.

## ⚠️ Safety (inherits `safe-testing-doctrine` — load it first)

Deserialization gives you **arbitrary code execution on the target**. That power makes the
safety rules non-negotiable — this class is one keystroke away from destroying a box.

- **Prove RCE with a BENIGN payload only.** The command in your gadget must be
  `id`, `whoami`, `hostname`, or an **out-of-band DNS/HTTP callback to your own
  collaborator** (`interactsh`, Burp Collaborator, a `nslookup <token>.oob.example`).
  Nothing destructive, nothing persistent.
- **NEVER use destructive or DoS gadgets.** No file delete/overwrite/encrypt, no
  `rm`/`format`/registry writes. Explicitly forbidden: **memory-exhaustion / "billion
  laughs" / decompression-bomb / recursive-collection chains** (e.g. hash-collision
  DoS payloads, `CommonsCollections` variants intended to hang, XML entity expansion).
  Those crash the service = availability impact = prohibited.
- **Do not leave RCE primitives live.** No webshells, no reverse shells left running,
  no scheduled tasks, no new accounts. Stop at the callback/echo that proves control.
- **Scope only.** Serialized blobs frequently ride in cookies/caches/queues shared with
  other tenants or systems — confirm the exact host/app is in scope before sending one.
- **Least-intrusive PoC.** First try to prove the sink is reachable *without* full RCE
  (e.g. a benign DNS lookup gadget, a detectable error differential, a URLDNS chain that
  only does a DNS resolve). Escalate to command execution only if RoE requires proof and
  it can be done with a benign command.
- **Cleanup + evidence.** Record every payload sent, every callback token, every artifact
  created; remove anything you created; hand the list to the report (`security-reporting`).

If RoE does not clearly permit active RCE proof, treat the finding as **DETECT-ONLY**:
show the reachable sink / recognizable format / unsigned ViewState and stop.

## Attack workflow

1. **Find serialized data** entering the app — hunt the recognizable markers below in
   cookies, hidden fields, params, headers, JSON `$type`/`_type` fields, uploaded files,
   message-queue bodies, cache entries.
2. **Identify the format + framework** (magic bytes → language; error messages / stack
   traces / dependencies → which library and gadget space).
3. **Confirm the sink is reachable** with the least-intrusive probe (malformed blob →
   deserialize error differential; URLDNS / benign DNS-only gadget → OOB callback).
4. **If permitted, prove RCE** with the matching gadget tool and a **benign command**.
5. **Detect + remediate** for the report using the sink/allow-list guidance.

## Recognize-it-on-the-wire cheat sheet

| Language / format | Magic marker (raw) | Base64 / text prefix | Common entry points |
|---|---|---|---|
| **Java** (`ObjectOutputStream`) | `AC ED 00 05` | `rO0AB...` (b64), `H4sIA` if gzip’d | cookies, hidden fields, RMI/JMX/T3/JMS, `viewstate`-like tokens, headers, Kryo/Hessian variants |
| **PHP** (`serialize()`) | `O:` (object), `a:` (array), `s:` (string) | often raw in cookie/param | cookies, `__` params, cache files, `phpMyAdmin`-style state, WordPress meta |
| **Python** (`pickle`) | `80 04` / `80 05` (proto 4/5), ends `.` (`2e`) | `gAS...`/`gAN...` (b64) | cookies, caches, Celery/queue msgs, `.pkl`/ML model files (`joblib`, HF) |
| **.NET BinaryFormatter / LosFormatter** | `00 01 00 00 00 FF FF FF FF` | `AAEAAAD/////` (b64) | `__VIEWSTATE`, cookies, WCF/Remoting, cache, Telerik `DialogParameters` |
| **.NET ViewState** | (LosFormatter blob) | `__VIEWSTATE=...` (often ends `=`) | ASP.NET WebForms hidden field / cookieless URL |
| **Ruby** (`Marshal`) | `04 08` | `BAh...` / `BAg...` (b64) | cookies (`_session_id`), Rails `Marshal`, caches, `Oj`/`YAML` |
| **JSON with type hints** | n/a | `"$type":`, `"__type":`, `"_type":`, `@class`, `py/object` | any JSON API using polymorphic typing (Json.NET, Jackson default typing, jsonpickle) |
| **Node.js** (`node-serialize`) | n/a | `{"rce":"_$$ND_FUNC$$_function..."}` | cookies/params passed to `unserialize()` |
| **YAML** | n/a | `!!python/object`, `!!javax...`, `!ruby/object`, `!!com...` tags | config upload, API bodies, `yaml.load` |
| **XML** (XStream/XMLDecoder/`XmlSerializer`) | n/a | `<java.lang...>`, `<dynamic-proxy>`, `<object class=...>` | SOAP, REST `application/xml`, config import |

Base64 hint: **`rO0` = Java**, **`AAEAAAD` = .NET BinaryFormatter**, **`gAS`/`gAN` = Python pickle**,
**`BAh` = Ruby Marshal**. Decode any suspicious blob (`base64 -d | xxd | head`) and match byte 1-4.

## Index — jump to the language

| Language / tech | Gadget tool | Reference file |
|---|---|---|
| **Java** (`readObject`, Commons-Collections, JNDI, WebLogic T3, JSF) | `ysoserial`, `marshalsec` | `references/java-dotnet.md` |
| **.NET** (BinaryFormatter, ViewState, Json.NET, DataContract) | `ysoserial.net`, `Blacklist3r` | `references/java-dotnet.md` |
| **Java/.NET YAML & XML** (SnakeYAML, XStream, XMLDecoder) | `marshalsec`, `ysoserial` | `references/java-dotnet.md` |
| **PHP** (`unserialize`, POP chains, Phar) | `phpggc` | `references/php-python-ruby-node.md` |
| **Python** (`pickle`, `yaml.load`, `jsonpickle`, ML models) | hand-rolled `__reduce__`, `fickling` | `references/php-python-ruby-node.md` |
| **Ruby** (`Marshal.load`, `YAML.load`, Oj) | universal gadget (Jahnke) | `references/php-python-ruby-node.md` |
| **Node.js** (`node-serialize`, `serialize-to-js`, `funcster`) | IIFE payload | `references/php-python-ruby-node.md` |
| **Detection & remediation** (SAST sinks, allow-lists, safe formats) | Semgrep/CodeQL | `references/detection-remediation.md` |

Provenance for every claim: `references/sources.md`.

## Cross-references

- **Injection siblings / SSTI / XXE:** `web-vuln-hunting/references/injection.md`.
- **Java JNDI + Log4Shell mechanics** (the JNDI leg many Java gadgets reuse):
  `web-cve-exploitation` (CVE-2021-44228). ViewState-adjacent Telerik CVE-2019-18935
  also lives there.
- **Finding sinks in source, writing SAST rules:** `secure-code-review-sast`.
- **CVE lookup / EPSS / KEV enrichment for a specific deser CVE:** `cve-knowledge-base`.
- **Writing it up + CVSS:** `security-reporting`.
