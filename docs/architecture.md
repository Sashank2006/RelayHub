# Architecture

This document describes how `code/main.py` decides an action
(`notify` / `digest` / `mute`) for every incoming message. It is a
single-pass, deterministic pipeline with no LLM or non-determinism in the
runtime path.

## 1. Pipeline overview

```
message + OCR(image) + ASR(voice)
        │
        ▼
normalize(text)              → lowercased, punctuation-stripped, single-spaced
        │
        ▼
content_signals(...)         → dict of integer counts per signal family
        │
        ▼
load_context(dataset)        → pre-built indexes: users, groups, members,
        │                      businesses, user-business history, message
        │                      history, message events, dismissed-business set
        ▼
decide(msg, sig, ctx)        → (action, message_type, reason, confidence)
        │
        ▼
find_evidence(...)           → top historical message_ids (Jaccard + bonuses)
```

Each output row is `message_id, action, message_type, reason, confidence,
evidence_message_ids`.

## 2. Signal extraction

`content_signals()` counts how many keywords in each lexicon match the
normalized text (text + OCR + ASR combined). Matching is **word-boundary
based** (`\b...\b`) so substrings such as `test` inside `latest`, `rs` inside
`others`, or `won` inside `won't` do not inflate counts. Each keyword is
matched once per message (deduplicated after normalization).

Signal families:

| Signal | Purpose | Example lexicons |
|---|---|---|
| `scam` | suspicious / scam indicators | OTP, verification code, QR, bit.ly, bank details, payout, blocked, restricted |
| `pressure` | urgency manipulation | block, expire, lock, penalty, tonight, jaldi, abhi |
| `promo` | marketing / selling | offer, discount, sale, coupon, cashback, limited time, selling, price |
| `promo_strong` | unambiguous promo | off won't wait, subscribe, coupon, limited time |
| `chain` | chain-forward indicators | forward to, share this, 10 people, do not ignore, blessing |
| `urgent` | time-sensitive language | call now, today, before 5 pm, leaving in, incident, alert threshold |
| `negation` | "no urgency" phrases | nothing urgent, no rush, no pressure, no need to reply |
| `event` | schedule / event nouns | maintenance, tanker, fire alarm, school, meeting, pickup, trip |
| `personal` | interpersonal chatter | hi, dinner, call me, can you, family |
| `greeting` | greetings / blessings | good morning, have a good day, bless |
| `payment` | payment nouns | payment, due, fee, receipt, upi, bill, charge |
| `fwd` | forwarded-count signal | from `forwarded_count` column |

Additional boolean signals computed inside `decide()`:

- `timebound` — same-day deadline phrases (`by 6 pm`, `closes at 5 pm`,
  `tonight`, `today`, `leaves in 10 min`, `by tomorrow`, ...).
- `action_now` — actionable verbs (`collect`, `confirm`, `call`, `submit`,
  `pickup`, `pay`, `come`, `check`, ...).
- `sensitive_ask` — requests for identity/money details (`share your otp`,
  `confirm password and otp`, `send bank details`, `scan and pay`, ...), with
  negation handling so "no payment or OTP required" is not treated as a scam.
- `strong_work` — on-call/work-incident phrases (`stay online`, `incident`,
  `build is failing`, `alert threshold`, `rollback`, ...).
- `direct_mention` — the receiving user is `@`-mentioned.

## 3. Context and personalization

`load_context()` builds indexes from the dataset CSVs:

- `biz_idx` — `business_accounts.csv` rows keyed by `business_id`.
- `ub_idx` — `user_business_history.csv` rows keyed by `(user_id, business_id)`.
- `ev_idx` — `message_events.csv` rows keyed by `message_id`.
- `hist_idx` — per-user lists of `message_history.csv` rows.
- `gm_idx` — `group_members.csv` rows keyed by `(group_id, user_id)`.
- `dismissed_biz` — a set of `(user_id, business_id)` pairs where the user
  muted after a message or dismissed an unopened message from that business
  (drives repeat-offer suppression).

### Business risk score

`business_risk()` starts at 0 and adds penalties, then `trust = 1 - min(1, risk)`:

| Condition | Penalty |
|---|---|
| Not verified (`verified == 0`) | +0.35 |
| Sender domain ≠ official domain | +0.35 |
| Account age < 60 days | +0.25 |
| Sender-domain age < 60 days | +0.15 |
| ≥10 user reports, volume-scaled | `+min(0.35, reports/sent * 100 * 0.5)` |

Thresholds used by the rules:

- `risk >= 0.5` + sensitive content → `mute scam`
- `risk >= 0.9` + unverified + ≥15 reports + no opened engagement → `mute spam`

## 4. Evidence retrieval

`find_evidence()` scores every historical message for the user:

```
score = jaccard(tokens(current), tokens(historical))
      + 0.45  if same business
      + 0.40  if same sender
      + 0.30  if same group
      + 0.05  if same conversation_type
      + 0.15  if user replied to it
      + 0.05  if user opened it
      + 0.20  if user reported it
      + 0.10  if user muted after it
```

The top two scores are included only if `score >= 0.35`; otherwise the field
is `none`. The same-context bonuses mean a past message from the same sender,
business, or group is much easier to include than a purely text-similar one.

## 5. Decision-rule ordering (safety first)

Rules are evaluated top to bottom; the first match returns.

| # | Rule | Result |
|---|---|---|
| 1 | Prompt-injection / routing-override keywords | `mute scam` |
| 2 | Risky business (`risk>=0.5`) + sensitive ask / QR / scam | `mute scam` |
| 2b | Unverified, ≥15 reports, no opened engagement | `mute spam` |
| 3 | Strong scam: sensitive ask, scam>=4, link+scam, pressure+scam | `mute scam` |
| 4 | Chain forward / blessing & health forwards | `mute forward` |
| 5 | Promotion: business>=2 hits or group>=2 hits; opt-out, dismissed, muted, or dismissed-business → `mute promotion`; else `digest promotion` (group admin same-day deadlines are excluded so `offer letter` deadlines stay `notify`) |
| 5c | Sales-thread continuation: same sender has prior sale messages in the group | `digest promotion` / `mute promotion` if group muted |
| 5b | Trusted-admin payment reminder + same-day deadline, no link | `notify payment` |
| 6 | Urgent / direct-mention / work-incident + timebound or action | `notify urgent` or `notify event` |
| 7 | Non-business same-day actionable event | `notify event` |
| 7b | Admin school circular (text or OCR "consent form" / "field trip") | `notify event` |
| 8 | Business update gated by `why_user_knows_account` (order/delivery/booking) | `notify event` / `notify business_update` / `digest business_update` |
| 10 | Digest fallback: greeting / event / payment / forward / personal | `digest ...` |

The critical invariant: **scam and injection rules always run before any
notify rule**, so a payment-looking scam can never reach `notify payment`, and
an "admin" payment scam is caught before the trusted-admin payment rule.

## 6. Confidence

`_conf(base, *mods)` returns a value clamped to `[0, 1]`. Each rule starts from
a base confidence (0.68–0.98) and applies small deterministic modifiers (e.g.,
direct mention, scam-signal strength, opt-out state). Confidences are
heuristic, not calibrated probabilities.

## 7. Reproducibility

- The OCR/ASR cache `code/media_text.json` is committed, so output does not
  depend on model availability at run time.
- All matching and scoring is deterministic; no randomness anywhere.
- `python code/main.py` regenerates `dataset/output.csv` byte-for-byte.
