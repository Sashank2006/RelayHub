# Results

## Labeled-sample evaluation

`code/evaluation/main.py` runs the router over the 30 labeled messages in
`dataset/sample_messages.csv` and reports action-level metrics plus schema
validation of `dataset/output.csv`.

Verified run (Aug 2026):

```
=== action confusion matrix (rows=predicted, cols=true) ===
pred\true    digest      mute    notify   total
   digest        11         0         0      11
     mute         0        10         0      10
   notify         0         0         9       9

=== per-class precision / recall / F1 on action ===
class       tp  fp  fn    prec     rec      f1
digest      11   0   0   1.000   1.000   1.000
mute        10   0   0   1.000   1.000   1.000
notify       9   0   0   1.000   1.000   1.000

action accuracy on labeled set: 1.000 (30/30)
message_type agreement on labeled set: 23/30

=== output schema / coverage check ===
columns exactly [...]: True
rows: 110 (expected 110)
every message_id covered: True
no duplicate message_id: True
all actions valid: True
confidence in [0,1] and non-null: True
evidence non-null: True
reason non-empty: True
```

## Interpretation

- **Action accuracy 30/30** — the router's `notify` / `digest` / `mute`
  decisions match the labeled set exactly.
- **Message-type agreement 23/30** — the 7 mismatches are *within the correct
  action* (e.g., `event` vs `urgent` for a tanker heads-up, `greeting` vs
  `forward` for a blessing), so they do not change the action score.
- **Schema/coverage** — `dataset/output.csv` is validated on every eval run.

## Caveats

- The labeled sample is a **held-out set built from the same users, groups,
  businesses, and media** as the 110-message test set, so the patterns it
  exercises overlap heavily with the test set. It is a strong *generalization
  signal*, not proof of performance on fully unseen data.
- Confidence values are heuristic, not calibrated probabilities.
- These numbers were produced by `python code/evaluation/main.py` on this
  repository state; they are not compared against hidden ground-truth labels,
  which only the challenge evaluator can see.
