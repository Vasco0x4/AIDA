---
name: ai-llm-security
description: "Operational playbook for authorized security testing of AI / LLM applications, structured around the OWASP Top 10 for LLM Applications (2025) and OWASP GenAI guidance. Covers all ten risks — LLM01 Prompt Injection (direct & indirect), LLM02 Sensitive Information Disclosure, LLM03 Supply Chain, LLM04 Data & Model Poisoning, LLM05 Improper Output Handling (downstream XSS/SQLi/SSRF/RCE), LLM06 Excessive Agency (agentic/tool/MCP abuse, confused deputy), LLM07 System Prompt Leakage, LLM08 Vector & Embedding Weaknesses (RAG poisoning/leakage), LLM09 Misinformation, LLM10 Unbounded Consumption (safe cost/DoS control probing) — plus jailbreak/guardrail-bypass methodology and MCP / tool-calling injection testing. For each: HOW TO TEST with concrete SAFE benign probes, a public reference, detection, and remediation. Cross-references web-vuln-hunting and api-security-testing. Grounded in OWASP GenAI, MITRE ATLAS, NIST AI RMF, and public prompt-injection research. Authorized, in-scope engagements only — benign canary probes to demonstrate control gaps, never real harmful-content generation, data poisoning of production stores, or resource-exhaustion floods."
version: 1.0.0
triggers:
  - llm security
  - ai security
  - ai llm security
  - owasp llm top 10
  - owasp top 10 for llm applications
  - prompt injection
  - direct prompt injection
  - indirect prompt injection
  - jailbreak testing
  - jailbreak
  - guardrail bypass
  - system prompt leak
  - system prompt leakage
  - rag security
  - rag poisoning
  - vector embedding security
  - ai red team
  - ai red teaming
  - llm red team
  - excessive agency
  - agentic security
  - tool calling security
  - mcp security
  - model context protocol security
  - llm output handling
  - improper output handling
  - insecure output handling
  - sensitive information disclosure llm
  - training data leakage
  - model poisoning
  - data poisoning
  - supply chain llm
  - unbounded consumption
  - llm dos
  - model extraction
  - misinformation hallucination
  - ai chatbot testing
---

# AI / LLM Application Security Testing (Authorized — OWASP LLM Top 10 2025)

Operational playbook for finding, safely proving, and reporting vulnerabilities in
AI / LLM-backed applications — chatbots, copilots, RAG systems, and **agentic /
tool-using** assistants — framed around the **OWASP Top 10 for LLM Applications
(2025)**, OWASP GenAI Security Project, **MITRE ATLAS**, and **NIST AI RMF**.

The local project this skill base ships with (AIDA) is itself an AI assistant with
tool/command execution — the canonical shape of an app this skill tests. Treat
that as the running example: an LLM that reads untrusted input, calls tools, and
feeds its output into other systems.

This skill assumes the web/injection fundamentals in `web-vuln-hunting` and the
API framing in `api-security-testing`. It does **not** re-teach XSS/SQLi/SSRF
mechanics — it shows how an LLM becomes the *delivery vector* for them. Use them
together.

## ⚠️ Safety — inherits `safe-testing-doctrine` (read first)

This skill operates **only** under the base `safe-testing-doctrine`. Load it
before any active test. LLM-specific hard limits:

- **Test only authorized AI apps / endpoints / models in scope.** Third-party
  hosted models (OpenAI, Anthropic, etc.) reached *through* the target app are in
  scope only as the app exposes them — do not attack the upstream provider.
- **Benign canaries only — never produce real-world harm.** The goal is to
  demonstrate a **control gap**, not to generate weapons, malware, CSAM, or real
  PII. Prove a jailbreak with a **harmless canary** (e.g. get the model to emit a
  fixed benign token like `CANARY-INJECTION-OK`, reveal a *decoy* secret you
  planted, or say a banned-but-harmless phrase). If a probe would produce
  genuinely harmful output, **stop at the point of demonstrated bypass** and
  report the gap — do not complete the harmful generation.
- **LLM10 Unbounded Consumption — probe for the EXISTENCE of limits, never a
  flood.** Send a **small controlled set (~5–20 requests / a few large-but-bounded
  inputs)** to observe whether rate-limits, token caps, quotas, or output-size
  caps exist. Observe `429`/throttling/truncation, then **STOP and report**.
  Never run a cost-bomb, recursion loop, model-extraction harvesting run, or
  overnight loop. "No limit observed in N requests" is the finding.
- **No poisoning of production models or stores.** Data/model poisoning (LLM04)
  and RAG/vector poisoning (LLM08) are tested **only** against your own test
  corpus / a non-production index / a documented sandbox — never by writing
  adversarial content into a live knowledge base, fine-tuning set, or shared
  vector store.
- **No exfiltrating real user data.** Indirect-injection exfil chains are proven
  with **planted decoy secrets and a canary sink you control**, never with real
  user records, session tokens, or credentials.
- **Least-intrusive proof, responsible disclosure, cleanup.** Remove any planted
  documents / test accounts / decoy files afterward and list them in the report.

If a probe risks harmful content, real data exposure, service degradation, or
persistent state change, **stop and report the gap** rather than push through.

## How to use this skill

1. **Map the AI surface** before testing. Identify: the model/provider, the system
   prompt boundary, every **untrusted input channel** (user chat, uploaded
   files/docs, retrieved web/RAG content, tool results, email/calendar,
   MCP servers), every **tool/action** the model can invoke and with what
   privilege, and every **downstream sink** the model's output flows into (HTML
   render, SQL, shell, HTTP client, another agent).
2. **Pick the risk** from the index table and open its reference file.
3. Each reference gives, per item: **HOW TO TEST** (concrete safe probes),
   **public reference**, **detection**, **remediation**.
4. Cross-reference `web-vuln-hunting` for the downstream vuln (LLM05) and
   `api-security-testing` for the tool/endpoint layer (LLM06).
5. Report with `security-reporting`; map findings to OWASP LLM Top 10 + MITRE
   ATLAS technique IDs.

## OWASP Top 10 for LLM Applications 2025 — index

| ID | Risk | Reference file |
|----|------|----------------|
| **LLM01** | Prompt Injection (direct & indirect) | `references/prompt-injection.md` |
| **LLM07** | System Prompt Leakage | `references/prompt-injection.md` |
| **LLM05** | Improper Output Handling (→ downstream XSS/SQLi/SSRF/RCE) | `references/output-and-agency.md` |
| **LLM06** | Excessive Agency (tool/plugin/MCP abuse, confused deputy) | `references/output-and-agency.md` |
| **LLM02** | Sensitive Information Disclosure (training-data / secret leakage) | `references/data-and-supply-chain.md` |
| **LLM03** | Supply Chain (model/dependency provenance) | `references/data-and-supply-chain.md` |
| **LLM04** | Data & Model Poisoning | `references/data-and-supply-chain.md` |
| **LLM08** | Vector & Embedding Weaknesses (RAG poisoning / leakage) | `references/data-and-supply-chain.md` |
| **LLM09** | Misinformation (hallucination, unsafe reliance) | `references/data-and-supply-chain.md` |
| **LLM10** | Unbounded Consumption (safe cost/DoS control probing) | `references/data-and-supply-chain.md` |

Jailbreak / guardrail-bypass methodology and MCP / tool-calling injection testing
are cross-cutting and covered in `references/prompt-injection.md` and
`references/output-and-agency.md`.

## Framework cross-mapping (for the report)

- **OWASP LLM Top 10 2025** — application-level vulnerability taxonomy (this skill).
- **MITRE ATLAS** — adversary tactics/techniques for AI systems (e.g.
  `AML.T0051` LLM Prompt Injection, plus the Spring-2025 additions: RAG Poisoning,
  False RAG Entry Injection, LLM Prompt Crafting, AI Supply Chain Compromise).
- **NIST AI RMF** — governance/risk functions (Govern/Map/Measure/Manage); use
  ATLAS + OWASP to populate the Measure function.
- **OWASP GenAI Security Project** — parent project for the LLM Top 10 and agentic
  guidance.

See `references/sources.md` for all consulted public URLs.
