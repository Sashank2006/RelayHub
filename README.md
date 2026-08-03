# Message Notification Router

A deterministic, multimodal routing engine that decides — for every incoming
WhatsApp-style message — whether the user should be interrupted **now**
(`notify`), see it **later** (`digest`), or never see it at all (`mute`).

Built for the **HackerRank Orchestrate (August 2026)** challenge. Routes all
110 messages in `dataset/messages.csv` with personalized, explainable
decisions. No LLM in the runtime path; every decision is produced by an
auditable, ordered rule engine over real signals.

```
message_id,action,message_type,reason,confidence,evidence_message_ids
```

## Overview

WhatsApp is noisy: family chats, society notices, school updates, co-worker
incidents, business promotions, image posters, voice notes, and scams all
arrive in one stream. Treating every message the same produces two bad
outcomes — important messages get missed, and unwanted or risky messages
interrupt the user.

This router personalizes the decision per receiving user. The same sale poster
may be `notify` for one user and `mute` for another; a payment reminder may be
legitimate from a trusted group admin but risky from an unknown sender; a muted
family group can still contain an urgent direct mention. Clear scam and safety
risk is muted regardless of the user's usual engagement.

## Features

- **Multimodal understanding** — text signals, OCR of image
  posters/screenshots (`easyocr`), and ASR of voice notes (`faster-whisper`),
  so a field-trip consent image or a spam voice call-back is understood, not
  ignored.
- **Sender trust scoring** — per-business risk from verification status,
  official-vs-used domain mismatch, account/domain age, message volume, and
  user reports.
- **Full personalization** — per-group mute state and roles, business opt-out /
  promo consent / dismissal history, and messages the user dismissed or muted
  after receiving.
- **History-based evidence** — every decision carries `evidence_message_ids`
  retrieved by Jaccard similarity + contextual bonuses (same sender/business/
  group), so reasons are traceable to concrete past messages.
- **Safety-first routing** — prompt-injection, OTP/QR/bank-detail scams, and
  high-report unverified senders are muted before any notify logic runs.
- **Deterministic and reproducible** — identical `output.csv` every run; no
  sampling, no API calls, no hardcoded labels.
- **Evaluation harness** — `code/evaluation/main.py` reports an action
  confusion matrix, per-class precision/recall/F1, and full schema validation.

## Tech Stack

| Concern | Technology |
|---|---|
| Language | Python 3.13 |
| Data | pandas |
| Image OCR (optional preprocess) | easyocr |
| Voice ASR (optional preprocess) | faster-whisper |
| Runtime decisioning | Deterministic rule engine (no LLM) |
| Tests | pytest |

## Architecture

The router is a single-pass pipeline: normalize each message's text plus its
OCR/ASR transcripts, compute ~15 categorical signals from word-boundary-matched
keyword lexicons, then run an ordered set of decision rules.

```mermaid
flowchart TD
    A[messages.csv] --> B[Normalize text + OCR/ASR transcripts]
    B --> C[Signal extraction: scam, promo, urgent, event, payment, chain, ...]
    C --> D[Context: user, group mute/role, business risk, history]
    D --> E[Ordered decision rules]
    E --> F1[mute: scam / spam / forward / promotion]
    E --> F2[notify: urgent / payment / event / business_update]
    E --> F3[digest: business_update / event / personal / greeting]
    F1 --> G[output.csv rows with reason + evidence ids]
    F2 --> G
    F3 --> G
```

### Decision-rule ordering

Order matters: the first matching rule wins, so safety runs first.

1. Prompt-injection / routing-override content → `mute scam`
2. Risky business + sensitive ask (OTP/QR/bank details) → `mute scam`
3. Strong scam content (sensitive/link/QR) → `mute scam`
4. Chain forwards & high-count blessing/health forwards → `mute forward`
5. Promotion personalization (opt-out / dismissed / muted / sales-thread
   continuation) → `mute` or `digest promotion`
6. Legitimate payment reminder from a trusted admin with a same-day deadline →
   `notify payment`
7. Urgent / direct-mention / time-bound action → `notify urgent` or `event`
8. Admin school circulars (text or OCR) → `notify event`
9. Business updates gated by why-the-user-knows-the-account → `notify` or
   `digest`
10. Digest fallback for low-priority personal/group content

## Project Structure

```
.
├── README.md                    # This file
├── LICENSE                      # MIT
├── AGENTS.md                    # AI-tooling/logging contract (challenge infra)
├── problem_statement.md         # Original challenge spec
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Test + optional preprocess dependencies
├── code/
│   ├── main.py                  # Router engine + CLI entry point
│   ├── preprocess_media.py      # Optional OCR/ASR cache generation
│   ├── media_text.json          # Committed OCR/ASR cache (needed for output)
│   ├── evaluation/
│   │   └── main.py              # Evaluation harness (metrics + schema checks)
│   └── README.md                # Code-level run instructions
├── tests/                       # pytest suite
│   ├── test_signals.py
│   ├── test_business_risk.py
│   ├── test_evidence.py
│   └── test_router.py
├── docs/
│   ├── architecture.md          # Detailed pipeline and rule documentation
│   └── results.md               # Verified evaluation results
├── dataset/                     # Input data (CSVs + media), see below
└── .github/
    └── workflows/ci.yml         # CI: install → run → evaluate → test
```

## Getting Started

### Prerequisites

- Python 3.13+
- `pip`

### Installation

```bash
git clone <your-repo-url>
cd hackerrank-orchestrate-august26

python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### Running the Project

```bash
# Write predictions to dataset/output.csv (110 rows)
python code/main.py

# The output file is git-ignored; it is regenerated deterministically.
```

If `dataset/media/` files exist and you want to regenerate the OCR/ASR cache
from scratch (requires `easyocr` and `faster-whisper`):

```bash
pip install -r requirements-dev.txt
python code/preprocess_media.py --dataset dataset
```

### Testing

```bash
pip install -r requirements-dev.txt
pytest tests/
```

### Evaluating

```bash
python code/evaluation/main.py
```

This runs the router over the 30 labeled messages in
`dataset/sample_messages.csv` and prints an action confusion matrix with
per-class precision/recall/F1, plus schema/coverage validation of
`dataset/output.csv`.

## Usage

```python
# Use the engine programmatically
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath("code"))   # the code/ dir (not a package name)
import main as router

ctx = router.load_context("dataset")
media = router.load_media_text()
msgs = pd.read_csv("dataset/messages.csv")
for _, msg in msgs.iterrows():
    decision = router.route(msg, ctx, media)
    print(decision["message_id"], decision["action"], decision["message_type"], decision["confidence"])
```

## Dataset

All participant-facing input lives in `dataset/` (provided by the challenge):

- `messages.csv` — the 110 incoming messages to route
- `sample_messages.csv` — 30 labeled examples used for evaluation
- `users.csv`, `groups.csv`, `group_members.csv` — user and group context
- `business_accounts.csv`, `user_business_history.csv` — business trust and
  relationship context
- `message_history.csv`, `message_events.csv` — historical messages and user
  reactions (used for evidence and personalization)
- `images.csv`, `voice_notes.csv`, `media/` — raw media for OCR/ASR

See [`problem_statement.md`](./problem_statement.md) for the full schema.

## Results

Verified on the labeled sample set (`dataset/sample_messages.csv`, 30 messages):

| Metric | Value |
|---|---|
| Action accuracy | **30 / 30 (100%)** |
| Precision / Recall / F1 per action | **1.0 / 1.0 / 1.0** for notify, digest, mute |
| Message-type agreement | 23 / 30 |
| Output schema / coverage checks | Pass (110 rows, exact columns, no dupes) |

Full numbers and caveats: [`docs/results.md`](./docs/results.md).

## Roadmap

- **Completed** — multimodal signal extraction, business risk scoring,
  history-based evidence, full 110-message routing, evaluation harness.
- **Planned** — split the monolithic `code/main.py` into focused modules
  (`signals.py`, `context.py`, `rules.py`); add a test for every decision rule;
  cold-start handling for users with no message history.
- **Known limitations** — keyword lexicons need maintenance for new slang and
  evolving scam phrasings; no trainable/adaptive layer; confidence values are
  heuristic, not calibrated.

## Contributing

Open an issue for bugs or proposals, then a pull request. Add tests for any
new rule or keyword change and run `pytest tests/` before submitting. See
[`.github/pull_request_template.md`](.github/pull_request_template.md).

## License

[MIT](./LICENSE) — copyright holder placeholder; update before publishing.
