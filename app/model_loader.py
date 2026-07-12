"""Loads the fine-tuned Legal-BERT model + tokenizer from ./saved_model/
exactly once and exposes a simple ``predict()`` function used by the FastAPI
app.

The checkpoint directory contains ``config.json``, ``pytorch_model.bin``
(or ``model.safetensors``) and any tokenizer files produced by
``train/train.py``.

Resolution order:
    1. ``$MODEL_DIR`` if it points at a non-empty directory.
    2. The bundled ``saved_model/`` directory if it is non-empty.
    3. A download from the Hugging Face Hub repo given by ``$HF_MODEL_ID``
       (useful on Hugging Face Spaces, where the 418 MB weights are kept
       out of the git repo and Docker image).
"""

import logging
import os
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

try:
    # huggingface_hub is a transitive dep of transformers, but we import
    # lazily so the module still loads cleanly where it is absent.
    from huggingface_hub import snapshot_download
except ImportError:  # pragma: no cover
    snapshot_download = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Resolve the model directory exactly once at import time.
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = Path(os.environ.get("MODEL_DIR", BASE_DIR / "saved_model"))
HF_MODEL_ID = os.environ.get("HF_MODEL_ID", "").strip()

LABEL_NAMES = [
    "Criminal Procedure",  # id 0
    "Civil Rights",        # id 1
    "First Amendment",     # id 2
    "Economic Activity",   # id 3
]

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Loaded once, at import time. main.py will call load() during startup so
# the model is ready before the first request arrives.
_tokenizer = None
_model = None


def _download_from_hub(target: Path) -> Path:
    """Pull the entire checkpoint from the configured HF Hub repo.

    Useful on Hugging Face Spaces, where the 418 MB weights are kept out
    of the git repo and Docker image. Returns the on-disk directory.
    """
    if not HF_MODEL_ID:
        raise FileNotFoundError(
            f"No Legal-BERT checkpoint found in {MODEL_DIR}. "
            "To fetch from the Hub set $HF_MODEL_ID to '<user>/<repo>' "
            "(and $HF_TOKEN if the repo is private)."
        )
    if snapshot_download is None:
        raise RuntimeError(
            "huggingface_hub is required for HF Hub fallback but is not "
            "installed. Install it with `pip install huggingface_hub`."
        )

    token = os.environ.get("HF_TOKEN") or None
    logger.info("Downloading Legal-BERT from Hub repo %s -> %s", HF_MODEL_ID, target)
    snapshot_download(
        repo_id=HF_MODEL_ID,
        local_dir=str(target),
        token=token,
    )
    return target


def _resolve_model_dir() -> Path:
    """Pick a usable checkpoint directory.

    Order:
        1. Existing, non-empty ``$MODEL_DIR`` (or default ``./saved_model``).
        2. Empty / missing local dir + ``$HF_MODEL_ID`` set -> download.
        3. Otherwise raise with an actionable message.
    """
    if MODEL_DIR.exists() and any(MODEL_DIR.iterdir()):
        return MODEL_DIR

    if HF_MODEL_ID:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        return _download_from_hub(MODEL_DIR)

    raise FileNotFoundError(
        f"No Legal-BERT checkpoint found in {MODEL_DIR}. "
        "Either bundle the trained files in ./saved_model/ or set "
        "$HF_MODEL_ID to a Hub repo containing the checkpoint."
    )


def load():
    """Load the tokenizer and model from disk (or the Hub). Idempotent."""
    global _tokenizer, _model
    if _model is not None:
        return _tokenizer, _model

    resolved = _resolve_model_dir()
    logger.info("Loading Legal-BERT from %s", resolved)

    _tokenizer = AutoTokenizer.from_pretrained(resolved)
    _model = AutoModelForSequenceClassification.from_pretrained(resolved).to(DEVICE)
    _model.eval()
    logger.info("Legal-BERT ready on %s", DEVICE)
    return _tokenizer, _model


def predict(text: str):
    """Classify a single piece of legal text.

    Returns:
        (label_name, confidence) where confidence is a float in [0, 1].
    """
    tokenizer, model = load()

    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512,
    ).to(DEVICE)

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]
        pred_id = int(torch.argmax(probs).item())
        confidence = float(probs[pred_id].item())

    label_name = LABEL_NAMES[pred_id]
    return label_name, confidence
