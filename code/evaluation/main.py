"""Evaluation workflow for the Message Notification Router.

Loads the 30 labeled messages in dataset/sample_messages.csv, runs the same
router used for the submission, and reports:

  * action-level confusion matrix
  * per-class precision / recall / F1 on action
  * message_type agreement on labeled samples
  * schema / coverage checks on the produced dataset/output.csv

Run:  python code/evaluation/main.py
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main as router  # noqa: E402


def labeled_metrics(rows, labeled):
    lbl = labeled.set_index("message_id")
    y_true = [lbl.loc[r["message_id"], "action"] for r in rows]
    y_pred = [r["action"] for r in rows]
    classes = sorted(set(y_true) | set(y_pred))

    print("\n=== action confusion matrix (rows=predicted, cols=true) ===")
    header = "pred\\true" + "".join(f"{c:>10}" for c in classes) + f"{'total':>8}"
    print(header)
    for pc in classes:
        row = [sum(1 for t, p in zip(y_true, y_pred) if t == c and p == pc) for c in classes]
        tot = sum(1 for p in y_pred if p == pc)
        print(f"{pc:>9}" + "".join(f"{v:>10}" for v in row) + f"{tot:>8}")

    print("\n=== per-class precision / recall / F1 on action ===")
    print(f"{'class':<10}{'tp':>4}{'fp':>4}{'fn':>4}{'prec':>8}{'rec':>8}{'f1':>8}")
    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"{c:<10}{tp:>4}{fp:>4}{fn:>4}{prec:>8.3f}{rec:>8.3f}{f1:>8.3f}")

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)
    print(f"\naction accuracy on labeled set: {acc:.3f} ({sum(1 for t, p in zip(y_true, y_pred) if t == p)}/{len(y_true)})")

    mtype_agree = sum(
        1 for r in rows
        if str(lbl.loc[r["message_id"], "message_type"]).strip().lower()
        == str(r["message_type"]).strip().lower()
    )
    print(f"message_type agreement on labeled set: {mtype_agree}/{len(rows)}")


def schema_check(output_path, messages_path):
    out = pd.read_csv(output_path)
    msgs = pd.read_csv(messages_path)
    ids = set(msgs["message_id"])
    print("\n=== output schema / coverage check ===")
    cols = ["message_id", "action", "message_type", "reason", "confidence", "evidence_message_ids"]
    ok_cols = list(out.columns) == cols
    print(f"columns exactly {cols}: {ok_cols}")
    print(f"rows: {len(out)} (expected {len(msgs)})")
    print(f"every message_id covered: {set(out['message_id']) == ids}")
    print(f"no duplicate message_id: {out['message_id'].is_unique}")
    valid_actions = {"notify", "digest", "mute"}
    print(f"all actions valid: {set(out['action']).issubset(valid_actions)}")
    conf_ok = out["confidence"].between(0, 1, inclusive="both").all()
    print(f"confidence in [0,1] and non-null: {conf_ok and out['confidence'].notna().all()}")
    print(f"evidence non-null: {out['evidence_message_ids'].notna().all()}")
    print(f"reason non-empty: {out['reason'].astype(str).str.len().gt(0).all()}")
    return ok_cols and set(out["message_id"]) == ids and out["message_id"].is_unique


def main():
    dataset_dir = os.path.join(ROOT, "..", "dataset")
    sample_path = os.path.join(dataset_dir, "sample_messages.csv")
    messages_path = os.path.join(dataset_dir, "messages.csv")
    output_path = os.path.join(dataset_dir, "output.csv")

    labeled = pd.read_csv(sample_path)
    ctx = router.load_context(dataset_dir)
    media = router.load_media_text()

    rows = []
    for _, m in labeled.iterrows():
        rows.append(router.route(m, ctx, media))

    labeled_metrics(rows, labeled)
    schema_check(output_path, messages_path)


if __name__ == "__main__":
    main()
