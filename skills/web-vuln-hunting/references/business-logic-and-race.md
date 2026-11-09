# Business Logic Flaws & Race Conditions

Scanners never find these. They come from understanding the app's intended
rules and violating them. Highest-signal on mature targets.

## Business logic test ideas
- **Negative / overflow / decimal amounts**: quantity `-1`, price `0`, huge
  values, `1e10`, fractional cents to round in your favor.
- **Coupon / discount stacking**: apply the same code N times, combine
  exclusive codes, apply after price lock, reuse single-use codes.
- **Currency / rounding**: buy in weak currency, exploit rounding per line item.
- **Workflow / step skipping**: jump to `/checkout/success` without paying;
  skip email verification, KYC, or approval steps; reorder multi-step flows.
- **State transition abuse**: cancel-after-ship, refund-then-keep, re-use a
  consumed token, downgrade/upgrade plan to gain credit.
- **Quantity vs. inventory**: order more than stock; reserve without paying.
- **Referral / loyalty abuse**: self-referral, refer deleted accounts, farm points.
- **Trial / limit bypass**: reset free-tier counters via new tenant/email-plus tricks.
- **Price/param tampering**: `price`, `amount`, `currency`, `product_id` in the
  request body trusted from client (see mass assignment in access-control.md).
- **Replay of signed requests** where the signature doesn't cover all fields.
- **Insufficient authorization on "confirm" steps** while "initiate" was checked.

## Race conditions (TOCTOU)
When a limited resource is checked then used non-atomically, parallel requests
can double-spend it.

Classic targets: apply gift card/coupon, withdraw/transfer funds, redeem points,
vote/like once, accept invite once, claim limited stock, MFA/OTP verify,
follow/unfollow counters, uniqueness checks (register same username twice).

### How to fire parallel requests
```
Burp Repeater → "Send group in parallel" (single-packet attack for HTTP/2)
Turbo Intruder: race-single-packet.py template (20–50 concurrent)
```
```python
# Turbo Intruder sketch — gate requests to land simultaneously
def queueRequests(target, wordlists):
    engine = RequestEngine(endpoint=target.endpoint, concurrentConnections=30,
                           engine=Engine.BURP2)
    for i in range(30):
        engine.queue(target.req, gate='race1')
    engine.openGate('race1')
```
Confirm by the resource being consumed more times than allowed (e.g. balance
goes negative, coupon applied twice). Use test accounts and minimal amounts.

## Real disclosed-report patterns
- Parallel coupon redemption → balance applied many times (single-packet race).
- Skipping payment step reached order-complete state.
- Negative quantity produced a credit / refund.
- Race on "invite accept" joined a user to multiple paid seats for free.

## Severity
Direct financial loss / fund theft → High–Critical. Limited abuse / minor
economic impact → Medium.

## Remediation to recommend
Server-side validation of every price/amount/quantity; atomic operations with
DB locks/transactions or idempotency keys; enforce state machines server-side;
rate-limit and single-use guarantees on redemption endpoints.
