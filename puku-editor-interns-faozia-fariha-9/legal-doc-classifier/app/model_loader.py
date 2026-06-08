# ============================================================
# Loads the fine-tuned Legal-BERT model + tokenizer from
# ./saved_model/ exactly once and exposes a simple predict()
# function used by the FastAPI app.
# ============================================================

import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# Path to the folder produced by train/train.py.
# Resolve relative to THIS file so it works both locally and inside Docker,
# where files live at /app/app/model_loader.py and /app/saved_model/.
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("MODEL_DIR", os.path.join(BASE_DIR, "..", "saved_model"))

# Human-readable label names in the order produced by the trainer.
# These match the NEW_TO_NAME dictionary used during training.
LABEL_NAMES = [
    "Criminal Procedure",   # id 0
    "Civil Rights",         # id 1
    "First Amendment",      # id 2
    "Economic Activity",    # id 3
]

# Device: GPU if available, otherwise CPU
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Load tokenizer + model once, at import time.
# main.py will call load() during startup so the model is ready
# before the first request arrives.
_tokenizer = None
_model = None


def load():
    """Load the tokenizer and model from disk. Idempotent."""
    global _tokenizer, _model
    if _model is not None:
        return _tokenizer, _model

    _tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    _model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).to(DEVICE)
    _model.eval()  # inference mode (disables dropout etc.)
    return _tokenizer, _model


def predict(text: str):
    """
    Classify a single piece of legal text.

    Returns:
        (label_name, confidence) where confidence is a float in [0, 1].
    """
    tokenizer, model = load()

    # Tokenize the input the same way we did during training.
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512,
    ).to(DEVICE)

    with torch.no_grad():
        outputs = model(**inputs)
        # Softmax turns raw logits into a probability distribution.
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)[0]
        pred_id = int(torch.argmax(probs).item())
        confidence = float(probs[pred_id].item())

    label_name = LABEL_NAMES[pred_id]
    return label_name, confidence
