# Methodology & Threat Modeling

How to scope a white-box review, reason about data flow, review PRs/diffs, and
run lightweight STRIDE threat modeling that maps to controls. See `sources.md`
for provenance (OWASP Code Review Guide, ASVS, Threat Modeling Cheat Sheet).

---

## 1. Scoping the review

Before opening a file, establish context. A review with no context is just
guessing where bugs are.

**Questions to answer first:**
- **What is the app and who attacks it?** Public internet, authenticated users,
  internal only, multi-tenant? This sets your threat actor and the trust model.
- **What is in scope?** Which repos, branches, services, submodules. Get it in
  writing. Note explicit exclusions (vendored deps, generated code, test fixtures).
- **What is the crown jewels data?** PII, payment, secrets, auth tokens. Bugs
  that touch these outrank bugs that don't.
- **What is the tech stack?** Languages, frameworks (and their built-in
  protections — e.g. Django ORM parameterizes, React auto-escapes JSX), auth
  library, ORM, template engine, deserialization libs. This tells you which sink
  tables in `dangerous-sinks-by-language.md` matter.
- **What assurance level (ASVS)?** L1 (opportunistic), L2 (most apps —
  recommended default), L3 (high-value: finance/health/critical). Level scopes
  how deep you go.

**Budget the time.** Typical split for a fixed-time review:
`~15% scoping+threat model, ~15% automated pass, ~55% manual pass on hot spots,
~15% triage + write-up.` Don't read every line — read the security-relevant
paths and let SAST cover the breadth.

**Map the attack surface (entry points).** List every place untrusted data
enters: HTTP routes/controllers, GraphQL resolvers, message-queue consumers,
CLI args, file/upload handlers, webhooks, deserializers, and inter-service RPC.
These are your **taint sources**.

---

## 2. Data-flow / taint thinking (the core skill)

Almost every injection-class bug is the same shape:

```
SOURCE (untrusted input)  --->  [ no / weak SANITIZER ]  --->  SINK (dangerous op)
```

- **Source** — a program point where untrusted or sensitive data enters:
  `request.query`, `req.body`, `os.environ` (if attacker-influenced), form
  fields, headers, uploaded file names/contents, deserialized objects, DB rows
  that themselves came from user input (second-order).
- **Sanitizer** — a transformation that makes tainted data safe for a specific
  sink: parameterized query binding, output encoding/escaping for the right
  context, allow-list validation, canonicalization + boundary check for paths,
  strong type coercion. **A sanitizer is sink-specific** — HTML-encoding does
  nothing for SQL; escaping quotes does nothing for OS command.
- **Sink** — a place where tainted data causes harm: `db.query(concat)`,
  `Runtime.exec`, `eval`, `child_process.exec`, `pickle.loads`, template render,
  `fs.readFile(path)`, an outbound HTTP client (SSRF), `Response.redirect`.

**How to trace by hand:**
1. Start at the sink (dangerous function) — grep the sink tables, then work
   **backward** to see if any argument is attacker-derived. (Backward from sink
   is usually faster than forward from source because sinks are fewer.)
2. Or start at a source and follow it **forward** through assignments, function
   calls, and object properties to any sink. Watch for **taint-propagating**
   steps (string concat, `format`, collection ops) vs **value-preserving** steps.
3. At each hop, ask: *is this the same tainted value, and is it sanitized here?*
   A validation that runs on a different variable, or only on the happy path,
   does not count.
4. Confirm **reachability**: is the code path live (not behind a disabled flag),
   and does an auth check gate it? Reachability decides severity.

**Trust boundaries** — draw the lines where data crosses from lower to higher
trust: client -> server, internet -> DMZ -> internal, one microservice -> another,
user -> admin context, tenant A -> tenant B. **Every sink that sits just inside a
trust boundary is a priority.** Validation must happen *at* the boundary (server
side), never rely on client-side checks.

**Second-order / stored taint** is the classic SAST blind spot: input is stored
(DB, cache, file) in one request and used dangerously in another. Trace stored
values as sources too.

---

## 3. The automated pass

Run these first to map hot spots (details in `tooling-semgrep-codeql.md`):

- **SAST breadth:** `semgrep --config auto` (or curated rulesets) for a fast,
  language-aware first sweep. Optionally CodeQL for deeper interprocedural flow.
- **Secrets:** `gitleaks detect` (fast regex+entropy, whole history) and
  `trufflehog` (verifies whether a credential is *live*).
- **Dependencies (SCA):** identify vulnerable/abandoned libraries (see tooling doc).
- **IaC / config:** if the repo ships Terraform/K8s/Dockerfiles, scan those too
  and cross-reference (a code bug + a permissive IaM policy compounds).

Treat SAST output as a **worklist of leads**, not findings. Every lead gets
manual confirmation before it becomes a report entry.

---

## 4. The manual pass — where humans win

SAST is blind to **logic and authorization**. Read these by hand:

- **Access control on every sensitive operation.** For each route/handler that
  reads or mutates data: *is there an authentication check? an authorization
  check? does it verify the object belongs to the caller (IDOR/BOLA)?* Missing
  or object-agnostic checks are the #1 high-severity manual finding.
- **Business logic & workflows** — can steps be skipped/replayed/reordered
  (coupon reuse, price tampering, negative quantities, race conditions on
  balances)? SAST cannot model your business rules.
- **Auth/session/crypto plumbing** — password storage (bcrypt/argon2 vs MD5),
  token generation randomness, JWT alg/`none`, session fixation, reset-token
  entropy and expiry.
- **Error handling & info leaks** — stack traces to users, secrets in logs,
  differential responses that enable enumeration.

Read framework config too (CORS, CSRF protection, security headers, cookie
flags, debug mode) — bugs hide in config, not just code.

---

## 5. Diff / PR security review

Reviewing a change set is cheaper than a full audit and catches bugs before
merge. Technique:

- **Focus on the delta, but understand the blast radius.** A 3-line diff can
  introduce a sink; read enough surrounding code to know where the new/changed
  data flows.
- **Red flags in a diff:** new raw SQL/`format` strings near queries; new
  `exec`/`eval`/`system`/`child_process`; new deserialization; new outbound HTTP
  with a user-supplied URL; new file path built from input; a removed or weakened
  validation/authz check; a new dependency; anything that looks like a secret;
  disabling TLS verification "to make it work"; `// TODO security` / `nosec` /
  `nosemgrep` added without justification.
- **Check the negative space** — did the PR add an endpoint but *not* an authz
  check? Add input but *not* validation? The bug is often what's missing.
- **Automate it:** run Semgrep on the diff in CI (`semgrep ci` / diff-aware scans)
  so only newly-introduced findings block the PR — this keeps signal high and
  avoids drowning devs in legacy noise.

---

## 6. Lightweight threat modeling (STRIDE + DFD)

Do this early — it tells you *what to look for* before you read code. Keep it
lightweight: a whiteboard DFD and a STRIDE pass beats a 40-page document nobody
reads. Four questions (OWASP): **What are we building? What can go wrong? What
are we going to do about it? Did we do a good job?**

### 6a. Data-flow diagram (DFD)

Model the system with a tiny symbol set:
- **External entity / actor** — rectangle (user, third-party API, browser).
- **Process** — circle (web app, API, worker, microservice).
- **Data store** — open-ended rectangle / two parallel lines (DB, cache, S3, config file).
- **Data flow** — arrow (request, response, query, message).
- **Trust boundary** — dotted line crossing flows where trust level changes
  (internet->server, service->service, user->admin). **Trust boundaries are where
  threats live.**

### 6b. STRIDE — enumerate threats per element

Walk each element/flow and ask which STRIDE categories apply:

| Letter | Threat | Violates | Typical code-level cause | Control family (ASVS) |
|--------|--------|----------|--------------------------|-----------------------|
| **S** | Spoofing | Authentication | Weak/missing authn, credential stuffing, forgeable tokens | V2 Authentication, V3 Session |
| **T** | Tampering | Integrity | Missing input validation, mass assignment, unsigned data, IDOR on writes | V5 Validation/Encoding, V4 Access Control |
| **R** | Repudiation | Non-repudiation | No/weak audit logging, spoofable actor in logs | V7 Error/Logging |
| **I** | Information disclosure | Confidentiality | Verbose errors, secrets in logs, broken authz reads, weak crypto | V6 Crypto, V8 Data Protection, V4 |
| **D** | Denial of service | Availability | Unbounded loops/allocations, ReDoS, no rate limits, zip/XML bombs | V11 Business Logic, V13 API |
| **E** | Elevation of privilege | Authorization | Missing authz, IDOR/BFLA, injection -> RCE, unsafe deserialization | V4 Access Control, V1 Architecture |

For each identified threat, note the **existing control** (or its absence) and the
**code location** to verify during the manual pass. This produces your review
checklist.

### 6c. Abuse cases

Flip each feature into how an attacker misuses it: "As an attacker, I change the
`account_id` in the request to read another tenant's invoices." Abuse cases turn
fuzzy STRIDE into concrete tests you can confirm in code (that invoice endpoint
must check ownership).

### 6d. Map threats to controls (ASVS)

Use **OWASP ASVS** as the requirements checklist and the language for
remediation. ASVS has ~17 chapters (Architecture, Authentication, Session
Management, Access Control, Validation/Sanitization/Encoding, Cryptography,
Error/Logging, Data Protection, Communications, Malicious Code, Business Logic,
Files/Resources, API/Web Services, Config, etc.) across three levels:
- **L1** low assurance / mostly black-box detectable — minimum bar.
- **L2** recommended for most apps — defends against most current risks.
- **L3** high-value apps (finance, health, critical) — highest rigor.

Cite the specific ASVS requirement in each finding so devs get a testable,
standards-backed fix ("ASVS V4.1.x — enforce access control server-side on every
object reference").

---

## 7. Triage: true vs false positive

For each candidate:
1. **Source real?** Trace to origin. Constants, internal config, and non-attacker
   data are *not* sources -> likely FP or informational.
2. **Sanitizer present & correct for this sink?** Parameterized query, context-
   correct encoder, allow-list, safe API. If yes and it's on the actual path ->
   FP (but note it, defense-in-depth may still warrant a comment).
3. **Sink reachable & exploitable?** Dead code, feature-flagged off, or gated by
   solid authz lowers severity or kills it. Reachability = severity multiplier.
4. **Impact & likelihood** -> severity (use `security-reporting` for CVSS). An SQLi
   on an unauthenticated public endpoint outranks the same bug behind admin-only.

Record *why* something is an FP so it isn't re-triaged; suppress the rule inline
with a justifying comment (`// nosemgrep: rule-id -- input is an int enum, safe`).

---

## 8. Writing dev-friendly findings

A finding a developer can act on beats a clever one they ignore. Include:
- **What & where** — file + line + the exact source->sink data-flow path.
- **Why it matters** — concrete impact in this app ("any user can read any other
  user's messages"), plus **CWE** id and **ASVS** requirement.
- **Proof** — minimal PoC or the traced path; redact real secrets.
- **Severity** — CVSS/qualitative (see `security-reporting`).
- **Fix** — a **copy-pasteable** remediation (parameterized query snippet, the
  safe API, the allow-list), not "sanitize input." Point to the OWASP Cheat Sheet
  for the class.
- **Effort / references** — so it can be prioritized and scheduled.

Group systemic issues (e.g. "raw SQL string-building across 14 files") into one
root-cause finding with a pattern fix, rather than 14 duplicates.
