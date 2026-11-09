# GraphQL & API Security

## GraphQL
Endpoints: `/graphql`, `/api/graphql`, `/v1/graphql`, `/graphiql`, `/query`.

### Introspection
```bash
# dump schema
curl -s https://TARGET/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{__schema{types{name fields{name}}}}"}'
graphql-cop -t https://TARGET/graphql          # misconfig scanner
clairvoyance https://TARGET/graphql            # recover schema when introspection OFF
```
If introspection is disabled, use **field suggestions** (error "Did you mean…")
to brute-force fields (clairvoyance automates this).

### Attacks
- **BOLA/IDOR via `node(id:)`** and object queries — fetch other users' objects
  by id; per-type authz often missing.
- **Excessive data exposure** — request more fields than the UI shows.
- **Mutation authz gaps** — call admin mutations as low-priv user.
- **Batching / aliasing to bypass rate-limits & brute force**:
```json
{"query":"mutation{a:login(u:\"x\",p:\"1\"){t} b:login(u:\"x\",p:\"2\"){t}}"}
```
  100 aliases = 100 password guesses in one request (defeats naive rate limits).
  **Safe test:** prove the control gap with a *small* batch (a handful of aliases)
  and stop — do NOT run a full password list or ignore lockout policy (that's a
  lockout-DoS against real accounts). Report the gap; don't exploit at scale.
- **DoS via deep nesting / circular queries** — report the *possibility*; do NOT
  actually flood in-scope prod.
- **Injection through arguments** — SQLi/NoSQLi reach resolvers; test as usual.
- **Query cost / pagination abuse** — huge `first:`/`limit:` to dump data.

## REST / API general
- **BOLA & BFLA** — the API's #1 issue; see access-control.md. Test every
  `{id}`, method, and admin route directly, bypassing the UI.
- **Excessive data exposure** — API returns full objects; client filters. Read
  the raw response for hidden PII/fields.
- **Mass assignment** — see access-control.md.
- **Improper versioning** — `/v1` unenforced while `/v2` is patched.
- **Undocumented / debug endpoints** — from JS, mobile app, Swagger/OpenAPI
  (`/swagger.json`, `/openapi.json`, `/api-docs`). Enumerate every operation.
- **Missing rate limits** on auth/OTP/expensive ops.
- **Auth token in URL / logs**; **no TLS**; **verbose errors** leaking internals.
- **HTTP method tampering** — `TRACE`, `OPTIONS` reveal; `HEAD`/verb confusion
  bypasses filters.

### Swagger/OpenAPI-driven testing
```bash
# pull spec, then hit every path as low-priv & unauth
curl -s https://TARGET/openapi.json -o api.json
# import into Burp / use Postman; diff authz across roles per operation.
```

## Real disclosed-report patterns
- GraphQL `node(id:)` returned any user's private object (global BOLA).
- Alias batching brute-forced OTP/login past rate limits.
- REST API returned password-hash / internal flags in the user object.
- `/api/v1/` left unauthenticated after `/v2/` was fixed.

## Severity
BOLA/BFLA data theft or privesc → High–Critical. Excessive exposure of PII →
Medium–High. Introspection-only / verbose errors → Low/Info.

## Remediation to recommend
Enforce object- and function-level authorization in resolvers/controllers;
disable introspection + field suggestions in prod; query cost limiting + depth
limits; disable aliasing-based amplification / add per-operation rate limits;
return only needed fields (explicit response schemas); keep all API versions
patched; require auth on every endpoint by default.
