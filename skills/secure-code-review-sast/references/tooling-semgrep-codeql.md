# Tooling — Semgrep, CodeQL, Secret Scanning, SCA, IaC

Running and **writing** SAST rules, plus secret/dependency/IaC scanning. All
tools below run **locally / read-only** on source you are authorized to review.
Prefer self-hosted/CLI backends unless the client has sanctioned a cloud service
(no exfiltration of proprietary source — see SKILL.md safety note).

---

## 1. Semgrep

Fast, multi-language, pattern-based SAST. Rules are YAML; patterns look like the
code you're matching (with metavariables `$X`, ellipsis `...`).

### Running

```bash
# Zero-config: auto-select rules by detected languages/frameworks
semgrep --config auto /path/to/repo

# Curated community/registry rulesets
semgrep --config p/security-audit --config p/secrets --config p/owasp-top-ten .

# A specific ruleset or your own rules dir/file
semgrep --config p/javascript .
semgrep --config ./my-rules/ .

# CI / diff-aware: only findings introduced by the current change (high signal)
semgrep ci                       # baseline-aware in CI
semgrep scan --baseline-commit <sha> .

# Output for triage / reporting
semgrep --config auto --sarif -o results.sarif .
semgrep --config auto --json    -o results.json  .
```

Suppress a confirmed false positive inline (with justification):
`foo(bar);  // nosemgrep: rule-id -- bar is an int enum, not attacker-controlled`

### Writing a rule — basic (syntactic)

Match a dangerous sink pattern directly:

```yaml
rules:
  - id: python-eval-on-request
    languages: [python]
    severity: ERROR
    message: >
      eval() called on request data -> code injection (CWE-95). Use ast.literal_eval
      or parse explicitly.
    metadata:
      cwe: "CWE-95: Improper Control of Generation of Code"
      owasp: "A03:2021 Injection"
      references:
        - https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html
    patterns:
      - pattern: eval(...)
      - pattern-inside: |
          def $F(request, ...):
            ...
```

Useful operators: `pattern` / `patterns` (AND) / `pattern-either` (OR) /
`pattern-not` (exclude) / `pattern-inside` (context) / `pattern-not-inside` /
`metavariable-pattern` / `metavariable-regex` / `focus-metavariable`.

### Writing a rule — taint mode (source -> sanitizer -> sink)

Taint mode tracks data flow, dramatically cutting false positives: it fires
**only when a real path exists** from a source to a sink with no sanitizer. Set
`mode: taint` and provide the three annotation sets:

```yaml
rules:
  - id: node-command-injection-taint
    mode: taint
    languages: [javascript, typescript]
    severity: ERROR
    message: >
      Untrusted request data flows into child_process exec -> OS command
      injection (CWE-78). Use execFile/spawn with an argument array; validate input.
    metadata:
      cwe: "CWE-78: OS Command Injection"
      owasp: "A03:2021 Injection"
    pattern-sources:
      - pattern: req.body
      - pattern: req.query
      - pattern: req.params
      - patterns:
          - pattern: $REQ.headers[...]
    pattern-sanitizers:
      # values that make the data safe are dropped from the taint set
      - pattern: shellEscape(...)
      - patterns:
          - pattern: parseInt(...)          # coercion to int is safe here
    pattern-sinks:
      - patterns:
          - pattern-either:
              - pattern: child_process.exec($SINK, ...)
              - pattern: child_process.execSync($SINK, ...)
          - focus-metavariable: $SINK
```

Taint concepts (same across engines): **sources** = where untrusted data enters;
**sinks** = dangerous functions; **sanitizers** = patterns that neutralize taint
(they remove the value from the tainted set so it no longer reaches the sink).
`pattern-propagators` (advanced) model taint flowing through custom functions.
For n-day variant hunting, write a taint rule for the fixed bug's sink and run it
across the codebase to find siblings (see `vulnerability-research-zeroday`).

### Rule-writing workflow

- Prototype in the **Semgrep Playground** (semgrep.dev) or with `--test` against
  fixture files (`// ruleid:` and `// ok:` annotations) so the rule has
  regression tests.
- Start broad (syntactic) to see all hits, then tighten with `pattern-inside` /
  `pattern-not` / taint to kill false positives.
- Check the **registry** for an existing rule before writing one; borrow its
  source/sink lists (e.g. `express-sandbox-code-injection`, `p/*` packs).

---

## 2. CodeQL

Deeper, interprocedural semantic analysis: compile the code into a **CodeQL
database**, then query it in QL. Heavier than Semgrep (needs a build for compiled
languages) but stronger **global data-flow / taint tracking**. Powers GitHub code
scanning.

### Running (CLI)

```bash
# 1. Build a database (interpreted langs need no build command)
codeql database create db --language=python --source-root=.
codeql database create db --language=java --command="mvn -B clean compile"

# 2. Analyze with the standard security query suite -> SARIF
codeql database analyze db \
  codeql/python-queries:codeql-suites/python-security-extended.qls \
  --format=sar-if-latest --output=results.sarif

# Run a single custom query
codeql query run my-query.ql -d db
```

### How CodeQL taint tracking works

- **Data flow** tracks values that are *preserved* through assignments and calls;
  **taint tracking** adds edges for *non-value-preserving* steps (e.g. a substring
  of a tainted string is still tainted) — modeling "may be derived from."
- **Local** flow = within one function (fast). **Global** flow = across functions
  and through object properties (more powerful, more expensive).
- A modern data-flow/taint config implements predicates: **`isSource`** (untrusted
  entry points), **`isSink`** (dangerous operations), and optionally
  **`isAdditionalFlowStep`** (custom propagation) and `isBarrier`/`isSanitizer`
  (stops flow). A path query then reports source->sink flow paths.

```ql
/** Minimal shape of a taint-tracking query (Python-ish pseudocode). */
import python
import semmle.python.dataflow.new.TaintTracking
import semmle.python.dataflow.new.DataFlow

module Cfg implements DataFlow::ConfigSig {
  predicate isSource(DataFlow::Node n) { /* e.g. HTTP request param */ }
  predicate isSink(DataFlow::Node n) { /* e.g. arg to os.system */ }
  predicate isSanitizer(DataFlow::Node n) { /* e.g. shlex.quote result */ }
}
module Flow = TaintTracking::Global<Cfg>;

from DataFlow::Node source, DataFlow::Node sink
where Flow::flow(source, sink)
select sink, "Untrusted data from $@ reaches a command sink.", source, "here"
```

Use CodeQL when you need real interprocedural proof of a flow (fewer FPs on deep
paths), for **variant analysis** of a known CVE, and for patch-diff research.

### Semgrep vs CodeQL — when to use which

| | Semgrep | CodeQL |
|---|---|---|
| Setup | none; runs on raw source | build a DB (compiled langs need a build) |
| Speed | very fast | slower, heavier |
| Depth | good local + taint; per-file leaning | strong global/interprocedural flow |
| Rule authoring | quick YAML, code-like patterns | QL language, steeper curve |
| Best for | fast breadth, CI diff scans, custom org rules | deep flow proof, variant analysis, research |

Run **both** where budget allows: Semgrep for breadth and CI gating, CodeQL for
depth on the highest-value flows. Ingest both via SARIF into one triage view.

---

## 3. Secret scanning — gitleaks & trufflehog

Secrets leak in **git history**, not just current files, so always scan history.

```bash
# gitleaks: fast regex + Shannon-entropy, scans full history by default
gitleaks detect --source . --report-format sarif --report-path gitleaks.sarif
gitleaks detect --source . --log-opts="--all"      # all refs/branches
gitleaks protect --staged                            # pre-commit gate

# trufflehog: finds candidates, then VERIFIES them against the live provider API
trufflehog git file://. --only-verified               # only live/working creds
trufflehog filesystem ./path --json
trufflehog github --repo=https://github.com/org/repo
```

- **gitleaks** is *rule-first* (regex + entropy): tells you a string **looks
  like** a secret. Great as a fast pre-commit + CI gate.
- **trufflehog** is *verification-first*: it makes a live API call to confirm the
  credential **actually works right now**. A **verified** finding is a live
  credential — treat as urgent, recommend immediate rotation. **Unverified** =
  pattern match, still triage.
- Recommended combo: **gitleaks pre-commit** (speed) + **trufflehog in CI**
  (depth/verification).
- Safety: a discovered live secret is still the client's — **report and
  recommend rotation, do NOT use it** to access anything (SKILL.md safety note).
  Redact secrets in the report (show provider + last 4 only).

---

## 4. Dependency SCA (vulnerable & malicious libraries)

Cross-reference your code findings with known-vulnerable dependencies — a code
path that reaches a vulnerable library function raises severity.

```bash
# Ecosystem-native
npm audit --production            # Node
pip-audit                         # Python (PyPA)
mvn org.owasp:dependency-check-maven:check   # Java (OWASP Dependency-Check)
bundle audit                      # Ruby
govulncheck ./...                 # Go (only reports reachable vulns)

# Multi-ecosystem scanners
osv-scanner -r .                  # Google OSV database, lockfile-aware
trivy fs --scanners vuln,secret,misconfig .
```

Notes: prefer tools that consider **reachability** (e.g. `govulncheck`) to cut
noise. Check lockfile integrity and watch for **dependency confusion** /
typosquatting on internal package names. For CVE enrichment (EPSS/KEV) see the
`cve-knowledge-base` skill.

---

## 5. IaC / config scanning — cross-reference

If the repo ships infrastructure, scan it and correlate with app findings (an app
SSRF plus an over-permissive IAM role plus IMDSv1 is a chain, not three separate
lows).

```bash
checkov -d .                 # Terraform/CFN/K8s/Dockerfile/Helm
tfsec .                      # Terraform
trivy config .               # IaC + Dockerfile misconfig
kics scan -p .               # multi-IaC
hadolint Dockerfile          # Dockerfile lint
```

Cross-reference examples: hardcoded cloud creds in code (secret scan) + public
S3 bucket (IaC) = data exposure; app deserialization RCE + container running
`--privileged` (IaC) = host takeover path. See `cloud-security-testing` and
`container-supply-chain-security` for the infra side.

---

## 6. Wiring it into CI (defense-in-depth)

A practical secure-SDLC pipeline layers the tools so each catches what the others
miss, and **diff-aware** scans keep developer signal high:

```
pre-commit:  gitleaks protect --staged   (block secrets before they land)
PR / CI:     semgrep ci  (diff-aware, blocks NEW findings)
             trufflehog --only-verified  (live-secret gate)
             SCA (osv-scanner / npm audit / govulncheck)
             checkov/trivy config  (IaC)
nightly:     full semgrep + CodeQL security-extended suite (depth, whole repo)
```

Gate the PR on **new** high-severity findings only (don't block on legacy debt);
route full-repo depth scans to a nightly job. Feed all SARIF into one dashboard
so triage (TP/FP, CWE, ASVS mapping) happens in one place. See
`methodology-and-threat-modeling.md` §5 and §7 for diff-review and triage.
