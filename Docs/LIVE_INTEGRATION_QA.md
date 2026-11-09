# Live integration verification — 9 November 2026

This follow-up uses real local services on the Mac mini, separate from production AIDA. It supplements the earlier automated QA report. Synthetic accounts, repositories and messages are used throughout; no external person receives test mail.

## Observed results

| Integration | Result | Evidence |
| --- | --- | --- |
| SMTP / Mailpit | Passed | Received test message body; HIGH finding, scan-complete and assessment-complete notifications; LOW severity suppressed |
| Email report | Passed | Assessment PDF delivered as an attachment |
| SMTP failure | Passed | Closed SMTP port returns an unsuccessful test result |
| Generic webhook | Passed | Real HTTP receiver, JSON event, HMAC-SHA256 signature, HTTP 503 failure surfaced |
| Keycloak 26.8.2 | Passed after correction | Authorization-code exchange, PKCE, signed ID token/JWKS and viewer provisioning |
| SSO access controls | Passed | Viewer cannot administer SSO or create AppSec projects; repeat login creates no duplicate user; disabled user denied |
| SSO + OTP | Passed | SSO issues a second-factor challenge rather than a full AIDA token; recovery-code verification completes login |
| SSO negative cases | Passed | Invalid state and replayed authorization code rejected |
| GitLab CE 19.5.3 private repositories | Passed | Real read-only PAT, two visible private repositories; third inaccessible repository hidden and denied |
| GitLab source scan | Passed | Allowlisted repository downloaded over verified HTTPS, full commit SHA matched, Python finding detected; JSON/HTML/SARIF exported |
| GitLab revocation | Passed | Repository allowlist revoke, token replacement, provider-side PAT revoke and connection disconnect enforced |
| Regression after SSO correction | Passed | 1,322 backend tests; one intentional duplicate-ZIP warning; 380.92 seconds |

## Defect discovered with a real identity provider

Keycloak includes the `at_hash` claim in its ID token. AIDA previously verified the ID token without passing the access token returned by the authorization-code exchange, so the JWT library rejected a valid login. The correction passes that access token into verification. It does **not** disable signature, issuer, audience, expiry or `at_hash` checks. New regression cases cover a matching token, a mismatching token and a missing token; the callback test asserts that the provider access token reaches the verifier.

## Isolation and interpretation

- The QA database, service network and credentials are separate from production. No production Docker socket is mounted into the test backend.
- Mailpit is a real SMTP receiver, but this does not certify Gmail/Google Workspace deliverability or its authentication policies. Gmail account creation is unnecessary for TOTP or local OIDC testing.
- Keycloak uses local development mode inside the QA network. This verifies AIDA's OIDC protocol behavior, not public TLS/DNS deployment of an enterprise IdP.
- A local GitLab verifies the GitLab implementation. It does not substitute for a live GitHub PAT test or certify every GitLab hosting configuration.
- Slack and Telegram vendor delivery still require their own authorized account/bot credentials; the generic webhook check is not claimed as Slack/Telegram delivery.

Setup references: [GitLab Docker installation](https://docs.gitlab.com/install/docker/installation/) and [Keycloak Docker quickstart](https://www.keycloak.org/getting-started/getting-started-docker).

GitLab fixture commit: `ef0973ea98b6c4f41312f207c0afc77219a46011`. The scan produced one baseline finding. The official ARM64 image manifest was `sha256:800f8ce577ac408d6810b9f09f2d5c8412c388b8dc7b77e3421d3c1b4641efd1`; downloaded layers were checked against their SHA-256 digests. HTTPS verification remained enabled; only the disposable QA backend trusted the local test certificate.
