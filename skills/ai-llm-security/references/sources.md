# Sources — public references consulted

Authorized, defensive AI-red-team / LLM-security content. All material below is
public. Consulted 2025–2026.

## OWASP — Top 10 for LLM Applications 2025 & GenAI Security Project
- OWASP Top 10 for LLM Applications (project home) —
  https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP Top 10 for LLM Applications 2025 (GenAI resource) —
  https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/
- OWASP Top 10 for LLMs 2025 — full PDF (v2025) —
  https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf
- OWASP GenAI Security Project — https://genai.owasp.org/
- Verified 2025 item list (LLM01–LLM10):
  LLM01 Prompt Injection · LLM02 Sensitive Information Disclosure ·
  LLM03 Supply Chain · LLM04 Data & Model Poisoning ·
  LLM05 Improper Output Handling · LLM06 Excessive Agency ·
  LLM07 System Prompt Leakage · LLM08 Vector & Embedding Weaknesses ·
  LLM09 Misinformation · LLM10 Unbounded Consumption.

## Secondary OWASP-2025 explainers (item names/examples cross-checked)
- SecureLayer7 — OWASP LLM Top 10 (2025) —
  https://securelayer7.net/learn/ai-security/owasp-llm-top-10
- Invicti — OWASP Top 10 for LLMs 2025 —
  https://www.invicti.com/blog/web-security/owasp-top-10-risks-llm-security-2025
- Promptfoo — OWASP LLM Top 10 —
  https://www.promptfoo.dev/docs/red-team/owasp-llm-top-10/
- Mend — 2025 OWASP Top 10 for LLM Applications quick guide —
  https://www.mend.io/blog/2025-owasp-top-10-for-llm-applications-a-quick-guide/
- Aembit — OWASP Top 10 for LLM Applications (2025) —
  https://aembit.io/blog/owasp-top-10-llm-risks-explained/

## MITRE ATLAS (adversarial techniques for AI systems)
- MITRE ATLAS — https://atlas.mitre.org/
- LLM Prompt Injection (AML.T0051) —
  https://www.startupdefense.io/mitre-atlas-techniques/aml-t0051-llm-prompt-injection
- ATLAS overview (Spring-2025 GenAI additions: RAG Poisoning, False RAG Entry
  Injection, LLM Prompt Crafting, AI Supply Chain Compromise) —
  https://www.vectra.ai/topics/mitre-atlas
- Repello — MITRE ATLAS AML.T techniques mapped to red-team ops —
  https://repello.ai/blog/mitre-atlas-framework

## NIST AI RMF
- NIST AI Risk Management Framework — https://www.nist.gov/itl/ai-risk-management-framework
- Risk assessment for LLMs/agents — OWASP + ATLAS + NIST AI RMF (Giskard) —
  https://www.giskard.ai/knowledge/risk-assessment-for-llms-and-ai-agents-owasp-mitre-atlas-and-nist-ai-rmf-explained

## Prompt injection — direct, indirect, RAG & MCP
- Lakera — Indirect Prompt Injection: the hidden threat —
  https://www.lakera.ai/blog/indirect-prompt-injection
- Microsoft — Protecting against indirect prompt injection in MCP —
  https://developer.microsoft.com/blog/protecting-against-indirect-injection-attacks-mcp/
- SoK: Security & Safety in the Model Context Protocol Ecosystem (arXiv) —
  https://arxiv.org/pdf/2512.08290
- MCP Pitfall Lab — MCP tool-server security under multi-vector attacks (arXiv) —
  https://arxiv.org/pdf/2604.21477
- ClawGuard — runtime security vs. indirect prompt injection for tool-augmented
  agents (arXiv) — https://arxiv.org/pdf/2604.11790
- Prompt Injection Attacks in LLMs & AI Agent Systems: comprehensive review (MDPI) —
  https://www.mdpi.com/2078-2489/17/1/54
- Notable public incidents referenced: Perplexity Comet content-leak,
  zero-click RCE in MCP-connected IDEs, MCP tool-poisoning, CVE-2025-59944.

## Jailbreak / guardrail-bypass methodology
- Startup House — LLM Jailbreaks 2024–2026: techniques, risks & defenses —
  https://startup-house.com/blog/llm-jailbreak-techniques
- Wraith — LLM Jailbreaks and Guardrail Bypass field guide —
  https://wraith.sh/learn/llm-jailbreak-guide
- JStorm — LLM jailbreak taxonomy —
  https://jstorm.org/blogs/llm-jailbreak-taxonomy/
- Techniques cross-referenced: DAN/roleplay, Crescendo, Skeleton Key,
  Echo Chamber, many-shot (long-context), payload splitting, encoding/
  low-resource-language, virtualization.

## Cross-referenced skills in this base
- `safe-testing-doctrine` (mandatory RoE) · `web-vuln-hunting` (XSS/SQLi/SSRF/RCE
  downstream) · `api-security-testing` (tool/endpoint layer, BOLA/BFLA) ·
  `cloud-security-testing` (metadata SSRF) · `security-reporting` (write-up) ·
  `pentest-methodology` (framework mapping).
