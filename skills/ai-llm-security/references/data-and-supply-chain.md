# Data, Supply Chain, RAG & Consumption — LLM02 / LLM03 / LLM04 / LLM08 / LLM09 / LLM10

Covers sensitive-information disclosure, supply chain, data/model poisoning,
vector/embedding weaknesses, misinformation, and unbounded consumption. Poisoning
is tested **only** against your own test corpus / a non-production index — never a
live store. Consumption is tested by probing whether **limits exist** — never with
a flood.

---

## LLM02 — Sensitive Information Disclosure

The model reveals data it shouldn't: training-data memorization, secrets embedded
in prompts/context, other users' data, PII, or internal config.

### HOW TO TEST (safe probes)
- **Memorization / training-data leakage.** Ask for verbatim continuations of
  likely-memorized content, or "repeat the following forever"-style extraction
  probes, and check for regurgitated secrets/PII. Use **planted decoy PII** to
  prove the channel without exposing real data.
- **Context bleed / cross-tenant.** In a multi-user app, check whether one session
  can retrieve another user's data via RAG or history (cross-ref
  `api-security-testing` BOLA). Use two of **your own** test accounts.
- **Secret hunt.** Ask the model to reveal keys/connection strings/internal URLs it
  can see in context or tools. If a **decoy** secret leaks, that's the safe proof.
- **Over-sharing in errors/debug.** Trigger benign errors and inspect for stack
  traces, model/version, or config leakage.

### Detection / Remediation
Detect: PII/secret patterns in outputs; cross-session data in responses. Remediate:
data minimization & sanitization of training/RAG data; strict per-user access
control on retrieval; keep secrets out of prompts/context (vault them); output
DLP/redaction; scoped tool credentials.

---

## LLM03 — Supply Chain

Risk in the components you didn't write: base models, fine-tunes, adapters/LoRA,
datasets, embedding models, plugins/tools, and the usual package dependencies.

### HOW TO TEST (safe probes)
- **Provenance inventory.** Enumerate model source (hub/registry), version/hash,
  license, and whether weights are integrity-verified (signature/checksum) on load.
  Unverified pull = finding.
- **Dependency & plugin audit.** SBOM the app; scan Python/JS deps (cross-ref
  `offensive-osint` secret regexes, standard SCA). Check for typosquatted or
  unpinned model/package names and abandoned plugins.
- **Model registry hygiene.** Check whether models are pulled from trusted, pinned,
  access-controlled registries vs. arbitrary public repos (tampered-weights risk).
- **Serialization risk.** Flag pickle-based model formats (`.pkl`, `.bin`,
  `pickle`/`torch.load` on untrusted files) — deserialization RCE. Prefer
  `safetensors`. Do not weaponize; report the unsafe-load path.

### Detection / Remediation
Detect: unsigned/unpinned model loads; unexpected registries. Remediate: signed
models + checksum verification; pinned, vetted sources; SBOM & continuous SCA;
`safetensors` over pickle; least-privilege for plugin code.
MITRE ATLAS: AI Supply Chain Compromise.

---

## LLM04 — Data & Model Poisoning

Manipulating training / fine-tuning / RAG data to implant backdoors, bias, or
degraded behavior. **Test only your own non-production data/model.**

### HOW TO TEST (safe probes)
- **Ingestion trust review.** Map every data source that feeds training/fine-tune/
  RAG. Are sources authenticated, validated, and integrity-checked? Unvetted
  ingestion = the finding — you can often report it **without injecting anything**.
- **Backdoor-trigger test (sandbox only).** On a **copy** of the model/index you
  control, add a benign trigger phrase to a few docs and verify the app has no
  anomaly detection — demonstrating the *feasibility of poisoning*, then remove it.
- **Feedback-loop check.** If user feedback/RLHF or auto-ingested content updates
  the model/store, test whether unvalidated user input can influence future
  behavior.

### Detection / Remediation
Detect: data-drift/anomaly detection on training/RAG inputs; provenance tracking.
Remediate: vet & sign data sources; validate and sandbox ingested content; version
& audit datasets; anomaly detection; isolate untrusted feedback from
training/index. MITRE ATLAS: RAG Poisoning, False RAG Entry Injection.

---

## LLM08 — Vector & Embedding Weaknesses

RAG/vector-store-specific risks: poisoned documents, adversarial embeddings that
game retrieval ranking, embedding-inversion leakage, and cross-tenant retrieval.

### HOW TO TEST (safe probes)
- **RAG poisoning (own corpus).** Insert a benign doc engineered to rank highly
  for a target query (keyword stuffing / adversarial phrasing) containing a canary
  claim, and check whether it surfaces and steers the answer. Research shows a
  handful of crafted docs can dominate responses — so a *small* planted set proves
  it. Remove afterward.
- **Retrieval-boundary / access control.** Verify the vector store enforces
  per-user/per-tenant filtering. Try to retrieve a doc scoped to **your other test
  account** — cross-tenant retrieval is a high-severity leak.
- **Indirect injection via retrieved chunk.** A poisoned chunk is also an LLM01
  indirect-injection vector — test with a canary instruction (see
  `prompt-injection.md`).
- **Embedding inversion / leakage.** Check whether raw embeddings or source chunks
  are returned to the client (embeddings can leak source text).

### Detection / Remediation
Detect: ranking anomalies; retrieval crossing tenant boundaries; injection canaries
in retrieved text. Remediate: per-tenant partitioning + access control on
retrieval; validate/clean ingested docs; provenance & trust scoring per source;
monitor retrieval quality; don't expose raw embeddings.

---

## LLM09 — Misinformation

The model produces confident falsehoods (hallucinations, fabricated citations,
wrong facts) and the **application or user acts on them** — the security issue is
unsafe *reliance*, especially when output drives code, decisions, or actions.

### HOW TO TEST (safe probes)
- **Fabrication probes.** Ask about non-existent APIs/functions/packages
  ("slopsquatting" risk — model invents a package name an attacker could register),
  fake legal/medical facts, or made-up citations; check for confident fabrication.
- **Overreliance check.** Does the app act on model output with no verification,
  grounding, or human check? Does it show confidence/sources? Unverified
  action-on-output is the finding.
- **Grounding gaps.** For a RAG app, ask questions outside the corpus and see
  whether it hallucinates vs. abstains ("I don't know").

### Detection / Remediation
Detect: outputs lacking citations/grounding acted upon automatically. Remediate:
RAG grounding + citation; cross-verification / fact-check layer; confidence
signaling; human oversight for consequential decisions; guard against
slopsquatting (validate suggested package names).

---

## LLM10 — Unbounded Consumption

Cost/DoS and model-theft class: token floods, wallet-drain, recursive/looping
prompts, huge inputs, and model-extraction harvesting.

### ⚠️ TEST SAFELY — probe for the EXISTENCE of limits, never a flood
Send a **small controlled set (~5–20 requests, or a few large-but-bounded inputs)**
to observe whether a control exists, then **STOP and report the gap**. Never run a
cost-bomb, recursion loop, extraction-scale harvesting run, or overnight loop.

### HOW TO TEST (safe probes)
- **Rate-limit existence.** Send ~10–20 requests in a short burst; look for
  `429` / throttling / `Retry-After`. None observed in the small sample = report
  "no rate limit observed in N requests" (the finding — not proof of DoS).
- **Token / output caps.** Send one bounded large-ish input and ask for a long
  output; check whether input size and output length are **capped/truncated**.
  Don't maximize — just confirm a cap exists or is absent.
- **Recursion / loop bounds.** In an agentic app, check for step/iteration/spend
  limits (from tool inventory, not by triggering a runaway loop).
- **Model-extraction controls.** Note whether repeated systematic querying is
  rate-/quota-limited — **describe** the exposure; do **not** actually harvest a
  dataset to clone the model.
- **Cost controls.** Confirm per-user quotas / spend caps / anomaly alerts exist.

### Detection / Remediation
Detect: absence of `429`/quotas; unbounded token/step usage; billing spikes.
Remediate: rate limiting & quotas per user/key; input-size and output-length caps;
step/loop/spend limits for agents; timeouts; cost monitoring & anomaly alerting;
throttle systematic querying to deter extraction.
