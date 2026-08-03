# Message Notification Router

> This is the code-level guide. For the full project README (features,
> architecture, dataset, results), see [`../README.md`](../README.md).

Deterministic, multimodal, personalized router for HackerRank Orchestrate
(August 2026). For every incoming WhatsApp message it outputs one row of:

```text
message_id,action,message_type,reason,confidence,evidence_message_ids
```

- `notify` : interrupt the user now
- `digest` : useful but wait until later
- `mute`   : suppress (low-value, repetitive, unwanted, risky, or unsafe)

## How it works

The pipeline (see `main.py`) combines:

1. **Multimodal signals** — text keywords (word-boundary matched, deduped),
   OCR of image posters/screenshots, and ASR of voice notes.
2. **User context** — group membership, role, and per-group mute state.
3. **Business trust** — verification, official-vs-used domain match, account
   age, message volume, and user reports.
4. **User-business history** — opt-out / promo consent / dismissed counts,
   why-the-user-knows-the-account, and messages the user dismissed or muted
   after receiving.
5. **Message history retrieval** — evidence for repeated forwards, active
   sales threads, and repeat offers.

Decision rules are ordered: prompt-injection → risky-business/sensitive →
strong scam → chain forwards → promotion personalization (opt-out/dismissed/
muted/thread context) → trusted payment reminders → urgent/direct/time-bound
action → same-day events → business updates → digest fallback. No hardcoded
labels and no message-id-specific answers.

## Requirements

- Python 3.13
- `pandas`

OCR (`easyocr`) and ASR (`faster-whisper`) are used only in the optional
preprocess step. The committed cache `media_text.json` is used at run time, so
the router also runs on a machine without those libraries.

## Setup & run

```bash
# 1. (Optional) regenerate the OCR/ASR cache from raw media
python preprocess_media.py --dataset <path to dataset dir>

# 2. Produce dataset/output.csv
python main.py --dataset <path to dataset dir> --out <path to output.csv>
```

Both steps default to `../dataset` relative to `code/`.

## Evaluation

```bash
python evaluation/main.py
```

Runs the router over the 30 labeled messages in `dataset/sample_messages.csv`,
prints the action confusion matrix with per-class precision/recall/F1, and
validates the output schema (exact columns, full coverage, no duplicates,
confidence in [0,1]).

## Tests

```bash
# from the repository root
pytest tests/
```

See `tests/` for unit tests over signals, business-risk scoring, evidence
retrieval, and router behavior.
