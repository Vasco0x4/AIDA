# Detection & Remediation — Insecure Deserialization

The cross-cutting defender/reviewer view. Use with `secure-code-review-sast` (taint
analysis, writing rules) and `security-reporting` (writing the finding). For per-language
sinks see the other two reference files.

---

## 1. Dangerous sinks (grep / SAST source→sink catalog)

A deserialization finding is **request-tainted data → one of these sinks**.

| Language | Dangerous sinks (grep for these on untrusted input) |
|---|---|
| **Java** | `ObjectInputStream.readObject` / `readUnshared` / `readExternal`, `XMLDecoder.readObject`, `XStream.fromXML`, SnakeYAML `Yaml.load` (no SafeConstructor), `jackson` `enableDefaultTyping`/`@JsonTypeInfo(Id.CLASS)`, `SerializationUtils.deserialize` (Commons Lang), Hessian/Burlap/Kryo `readObject`, JMS `ObjectMessage.getObject` |
| **.NET** | `BinaryFormatter.Deserialize`, `SoapFormatter`, `NetDataContractSerializer`, `LosFormatter`/`ObjectStateFormatter` (ViewState), `JavaScriptSerializer` with resolver, `Json.NET` `TypeNameHandling != None`, `fastJSON`, `XmlSerializer`/`DataContractSerializer` with attacker-controlled types, `Activator.CreateInstance` on typed input |
| **PHP** | `unserialize(` on `$_GET/$_POST/$_COOKIE/$_REQUEST`, filesystem funcs on `phar://` paths (`file_exists`,`fopen`,`getimagesize`…), `yaml_parse` |
| **Python** | `pickle.load(s)`, `cPickle`, `_pickle`, `dill.load(s)`, `shelve`, `yaml.load` (no `SafeLoader`), `jsonpickle.decode`, `numpy.load(allow_pickle=True)`, `torch.load`, `joblib.load`, `pandas.read_pickle` |
| **Ruby** | `Marshal.load`/`restore`, `YAML.load` (Psych < 3.1), `Oj.load` `:object` mode, `Ox.parse_obj` |
| **Node.js** | `node-serialize`/`serialize-to-js`/`funcster`/`cryo` `.unserialize`, `eval`/`Function`/`vm.runIn*` on request data |

**Semgrep** (taint mode) — `mode: taint`, `pattern-sources` = the HTTP-input accessors,
`pattern-sinks` = the calls above, optional `pattern-sanitizers` = allow-list wrappers.
**CodeQL** — model the sink with `isSink`, HTTP input with `isSource`, run taint tracking;
CodeQL ships `UnsafeDeserialization` queries for Java/C#/Python/JS/Ruby. See
`secure-code-review-sast` for rule-writing mechanics.

---

## 2. Black-box detection (on an authorized test)

1. **Locate serialized blobs** — decode every opaque cookie/param/hidden field/header:
   `echo <val> | base64 -d | xxd | head`. Match byte 1-4 to the SKILL.md recognize table
   (`rO0`=Java, `AAEAAAD`=.NET, `gAS`=pickle, `BAh`=Ruby, `O:`=PHP, `__VIEWSTATE`).
2. **Error-differential probe** — send a **truncated/mutated** blob and a well-formed but
   wrong-type one; deserialization errors (`InvalidClassException`, `unserialize()`
   warnings, `EndOfStreamException`, ViewState MAC errors) confirm a live deserializer
   without running code.
3. **Safest live confirmation** — a **DNS-only gadget** (Java `URLDNS`, a PHP/Python gadget
   that fetches a URL) to your collaborator. A DNS hit proves deserialization. **Stop here
   if DETECT-ONLY.**
4. **RCE proof (only if RoE permits)** — matching gadget tool + **benign command / OOB
   callback** (never destructive, never a memory-exhaustion chain). Record token + request.

**Scanning aids:** Burp **"Java Deserialization Scanner"** and **Freddy** (Burp) detect and
help exploit Java/.NET/others; `nuclei` templates exist for specific product deser CVEs.
Passive: watch for the magic-byte prefixes in proxied traffic.

---

## 3. Remediation (defense-in-depth, best → last resort)

**Best — eliminate the pattern:**
- **Do not deserialize untrusted data with a native, type-carrying deserializer.** Prefer
  **data-only formats**: JSON, protobuf, MessagePack, CBOR — parsed into known types with
  schema validation. These carry data, not object graphs or code.

**If native (de)serialization is unavoidable:**
- **Allow-list the types** ("look-ahead" / class filtering), reject everything else:
  - Java: **JEP 290 `ObjectInputFilter`** / `jdk.serialFilter`, Commons IO
    `ValidatingObjectInputStream`, `SerialKiller`, override `resolveClass()`.
  - .NET: `SerializationBinder`/`ISerializationBinder` allow-list; **retire
    `BinaryFormatter`** (obsolete, throws by default in .NET 8, removed in .NET 9).
  - PHP: `unserialize($d, ['allowed_classes' => false])` or an explicit class array.
  - Python/Ruby: no safe allow-list for pickle/Marshal — **switch formats** instead.
  - Jackson: `PolymorphicTypeValidator` allow-list; never `enableDefaultTyping`.
  - SnakeYAML: `SafeConstructor` / ≥ 2.0. XStream: ≥ 1.4.18 allow-list ("no permission by
    default") via `allowTypes`.
- **Integrity — sign the blob.** If serialized state must round-trip a client, wrap it in
  an **HMAC / digital signature** and verify before deserializing, so attackers can't
  substitute their own object graph.
- **ViewState specifically:** keep **MAC enabled** (default; never `enableViewStateMac=false`),
  set `viewStateEncryptionMode="Always"`, use a **per-app auto-generated `machineKey`**
  (never hardcoded/shared/committed), rotate any leaked key.
- **Isolate & least-privilege:** run deserializing services with minimal OS privileges,
  in a sandbox/container, network-egress-restricted (blunts JNDI/URL fetch legs). Remove
  unused gadget libraries from the classpath and keep dependencies patched (SCA).
- **Monitor/detect at runtime:** log class names being deserialized; alert on unexpected
  types; JVM agents (`NotSoSerial`, `Contrast`); WAF signatures for `rO0`/`AAEAAAD`/`O:`
  patterns are a stop-gap, not a fix.

---

## 4. Reporting quick-reference

- **CWE-502: Deserialization of Untrusted Data** (in the CWE Top 25). Related:
  CWE-915 (mass-assignment-ish object modification), CWE-91/611 (XML/XXE side), CWE-94.
- **OWASP:** A08:2021 Software & Data Integrity Failures (was A08:2017 Insecure
  Deserialization).
- **Severity:** typically **Critical** when unauthenticated RCE; use CVSS (often
  `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H` → 9.8) — see `security-reporting`.
- **Evidence:** decoded blob + magic bytes, the benign gadget payload, the OOB callback
  token/timestamp, and the reachable sink. Note in cleanup any artifact created.
