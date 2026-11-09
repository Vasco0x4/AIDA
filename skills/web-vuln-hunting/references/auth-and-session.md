# Authentication & Session: JWT / OAuth / SAML / Password Reset / MFA

Account-takeover class — consistently top-paid on bug-bounty platforms.

## JWT attacks
```bash
jwt_tool <token> -M at          # run all checks
jwt_tool <token> -X a           # alg:none
jwt_tool <token> -C -d wordlist # crack HS256 secret
```
Checklist:
- **alg:none** — set header `{"alg":"none"}`, strip signature, keep trailing dot.
- **HS/RS confusion** — server expects RS256 but accepts HS256 signed with the
  public key as HMAC secret (forge any claim). `jwt_tool -X k -pk public.pem`.
- **Weak HMAC secret** — crack HS256 with rockyou/`jwt.secrets` lists.
- **`kid` injection** — path traversal (`kid:"../../dev/null"` → empty key),
  SQLi, or command injection in key lookup.
- **`jku`/`x5u` header** — point to attacker-hosted JWKS to supply your own key.
- **Claim tampering** — change `sub`/`role`/`user_id`/`admin` after breaking sig.
- **No expiry / not-checked `exp`** — replay old tokens; missing `aud`/`iss` checks.

## OAuth 2.0 / OIDC
- **`redirect_uri` manipulation** — append/replace to attacker domain, path
  traversal, `redirect_uri=https://client.com.attacker.com`, open-redirect chain
  on the client to leak `code`/token.
- **State parameter missing/static** → CSRF on the OAuth flow (account linking ATO).
- **Code/token leakage** via Referer, open redirect, or `response_type=token` in URL.
- **Authorization code reuse / no PKCE** on public clients.
- **Scope escalation** — request broader scopes than UI; consent bypass.
- **Account linking** — link attacker's social login to victim account, or
  pre-account-takeover before victim registers.
- **`prompt=none` / silent auth** abuse; mismatched `client_id`.

## SAML
- **Signature stripping / XML Signature Wrapping (XSW)** — move/duplicate signed
  assertion so parser validates one node but consumes attacker's.
- **Comment injection** in `NameID` (`admin@x.com<!---->.evil`) → user confusion.
- **`alg`/canonicalization** downgrade; XXE in SAML XML (see injection.md).
Tools: SAML Raider (Burp), samltool.

## Password reset flaws
- **Host header poisoning** — `Host:`/`X-Forwarded-Host: attacker.com` makes the
  reset link point to attacker; victim clicks → token to you.
- **Token predictability / no expiry / reuse / not invalidated** after use.
- **Token leakage** via Referer to third-party resources on the reset page.
- **User/email swap** — change `email`/`user_id` in the reset-confirm request to
  set another user's password (IDOR in reset).
- **Response leaks the token** or the new password in JSON.

## MFA / 2FA bypass
- Missing enforcement on the API even when UI requires it (call post-login endpoint directly).
- **OTP brute force** — no rate-limit / no lockout on the verify endpoint.
- **Response manipulation** — `{"mfa":false}`→`true`, `2fa_passed:true`.
- **Backup-code / remember-device** flaws; OTP reuse; race on OTP verification.
- **Flow skip** — go straight to the authenticated area URL after step 1.

## Session management
- Session fixation (session id not rotated after login).
- Tokens not invalidated on logout / password change.
- Long/no expiry, predictable ids, missing `HttpOnly`/`Secure`/`SameSite`.
- Concurrent-session and JWT-revocation gaps.

## Rate limiting / brute force
Test login, OTP, reset, coupon, invite endpoints. Bypass IP throttles with
rotating `X-Forwarded-For`, casing/whitespace on username, or HTTP/2 multiplex.
**Safe test:** send only a *small controlled sample* (enough to show no limit /
no lockout exists), never an actual flood or full brute force, and stay under the
account-lockout threshold−1 — locking out real users is a DoS (see
`safe-testing-doctrine`). For OTP/MFA brute (above), the same applies: a handful
of attempts proves the missing rate-limit; report the gap rather than cracking it.

## Real disclosed-report patterns
- Reset link host-header poisoning → mass ATO.
- OAuth `redirect_uri` bypass leaking `code` via open redirect → ATO.
- JWT `alg:none` accepted → forge admin.
- MFA verify endpoint had no rate limit → 6-digit OTP brute in minutes.

## Severity
Any pre-auth ATO / auth bypass → Critical. Reset/MFA bypass needing interaction
→ High. Session hardening gaps alone → Low/Medium.

## Remediation to recommend
Validate `redirect_uri` against exact allow-list + enforce PKCE & `state`; pin
JWT `alg`, verify `exp/aud/iss`, rotate secrets, avoid `kid`/`jku` from input;
single-use, short-TTL, user-bound reset tokens; server-side host allow-list;
enforce MFA at the API layer with rate-limits and lockouts.
