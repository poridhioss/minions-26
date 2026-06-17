"""Demo script: logs three different experiments under "Demo Project".

Run it with:

    python sample_run.py

The script is idempotent in spirit (it just appends new rows), so running it
more than once is fine — you'll just see more rows on the dashboard.

Wipes the database first so the demo data is always the same shape.
"""

from __future__ import annotations

import math
import os

from database import init_db
from tracker import start_run

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "experiments.db")


def _wipe_db() -> None:
    """Start from a clean slate so the demo is reproducible."""
    if not os.path.exists(DB_PATH):
        return
    try:
        os.remove(DB_PATH)
        print(f"Removed existing {DB_PATH}")
    except OSError as exc:
        print(f"(Could not remove {DB_PATH}: {exc}; continuing.)")


def _simulate(run, *, start_acc: float, start_loss: float,
              epochs: int, drift: float, label: str) -> None:
    """Emit a small synthetic training curve."""
    print(f"  [{label}] {epochs} epochs, start_acc={start_acc:.2f}, "
          f"start_loss={start_loss:.2f}")
    for epoch in range(epochs):
        # Accuracy climbs, loss falls — with a tiny cosine-shaped wobble.
        acc = min(0.999, start_acc + drift * epoch
                  + 0.005 * math.sin(epoch / 2))
        loss = max(0.001, start_loss - drift * epoch
                   - 0.005 * math.cos(epoch / 2))
        run.log_epoch("accuracy", acc, epoch)
        run.log_epoch("loss",     loss, epoch)


def run_success_small_lr() -> None:
    """Slow but steady: tiny learning rate, many epochs."""
    run = start_run(
        name="Demo · small-LR run",
        project="Demo Project",
        tags="demo,small-lr,baseline",
        notes="Slow but stable baseline. Used as a control run.",
    )
    run.log_params({
        "model":        "resnet18",
        "optimizer":    "sgd",
        "lr":           0.0005,
        "batch_size":   64,
        "epochs":       20,
        "weight_decay": 1e-4,
    })
    _simulate(run, start_acc=0.55, start_loss=1.20, epochs=20,
              drift=0.018, label="small-LR")
    run.finish(metrics={"accuracy": 0.91, "loss": 0.18, "f1": 0.90})
    print(f"  -> finished run id={run.id} status=completed")


def run_success_big_model() -> None:
    """Stronger model, more aggressive learning, best result."""
    run = start_run(
        name="Demo · big-model run",
        project="Demo Project",
        tags="demo,big-model,best",
        notes="Best run so far. Larger model + AdamW.",
    )
    run.log_params({
        "model":        "resnet50",
        "optimizer":    "adamw",
        "lr":           0.003,
        "batch_size":   32,
        "epochs":       15,
        "weight_decay": 5e-4,
    })
    _simulate(run, start_acc=0.60, start_loss=1.10, epochs=15,
              drift=0.022, label="big-model")
    run.finish(metrics={"accuracy": 0.96, "loss": 0.12, "f1": 0.95})
    print(f"  -> finished run id={run.id} status=completed")


def run_failed_overfit() -> None:
    """Aggressive learning rate that blows up — finishes with status='failed'."""
    run = start_run(
        name="Demo · overfit run",
        project="Demo Project",
        tags="demo,overfit,bad",
        notes="Learning rate too high. Loss diverged around epoch 4.",
    )
    run.log_params({
        "model":        "resnet18",
        "optimizer":    "sgd",
        "lr":           0.5,        # intentionally silly
        "batch_size":   16,
        "epochs":       10,
        "weight_decay": 0.0,
    })
    # Accuracy stalls and loss explodes.
    for epoch in range(10):
        acc = 0.40 + 0.02 * epoch
        loss = 1.0 + (0.4 ** epoch) * 5   # loss diverges
        run.log_epoch("accuracy", acc, epoch)
        run.log_epoch("loss",     loss, epoch)
    # Manually mark as failed (we never call .finish with status="completed").
    run.finish(metrics={"accuracy": 0.52, "loss": 5.0}, status="failed")
    print(f"  -> finished run id={run.id} status=failed")


def main() -> None:
    _wipe_db()
    # Re-create the schema after the wipe. tracker.py's module-level init_db()
    # only runs once per process, so we must call it again here to be safe.
    init_db()
    print("Seeding 3 demo runs into 'Demo Project'…")
    run_success_small_lr()
    run_success_big_model()
    run_failed_overfit()
    print("\nDone. Open the dashboard at http://127.0.0.1:5000/")


if __name__ == "__main__":
    main()
