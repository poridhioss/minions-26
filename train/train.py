# ============================================================
# Legal Document Classification — Training Script
# Run this in Google Colab.
# Fine-tunes Legal-BERT on the LexGLUE SCOTUS dataset and
# keeps only 4 classes:
#   0 -> Criminal Procedure
#   1 -> Civil Rights
#   2 -> First Amendment
#   3 -> Economic Activity
# ============================================================

# 1. Install dependencies (Colab cell)
# !pip install -q transformers torch datasets mlflow scikit-learn

import os
import random
import numpy as np
import torch
import mlflow
import mlflow.pytorch
from torch.utils.data import DataLoader
from torch.optim import AdamW
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    get_linear_schedule_with_warmup,
)
from datasets import load_dataset
from sklearn.metrics import accuracy_score, f1_score

# ------------------------------------------------------------
# 0. Reproducibility
# ------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

# ------------------------------------------------------------
# 1. Config
# ------------------------------------------------------------
MODEL_NAME = "nlpaueb/legal-bert-base-uncased"
MAX_LENGTH = 512
BATCH_SIZE = 8
EPOCHS = 3
LR = 2e-5
SAVE_DIR = "./saved_model"

# Original LexGLUE SCOTUS label id -> our label id (0..3)
# SCOTUS original: 0=Criminal Procedure, 1=Civil Rights,
#                  2=First Amendment, ..., 8=Economic Activity
ORIGINAL_TO_NEW = {0: 0, 1: 1, 2: 2, 8: 3}
NEW_TO_NAME = {0: "Criminal Procedure",
               1: "Civil Rights",
               2: "First Amendment",
               3: "Economic Activity"}
NUM_LABELS = 4

# ------------------------------------------------------------
# 2. Load + filter LexGLUE SCOTUS
# ------------------------------------------------------------
print("Loading LexGLUE SCOTUS dataset...")
dataset = load_dataset("coastalcph/lex_glue", "scotus")
print("Original splits:", {k: len(v) for k, v in dataset.items()})

# Remap labels and drop any rows whose label is not in our 4 classes
def remap(example):
    orig = example["label"]
    if orig in ORIGINAL_TO_NEW:
        example["label"] = ORIGINAL_TO_NEW[orig]
        return example
    return None  # mark for filtering

dataset = dataset.map(remap).filter(lambda ex: ex["label"] is not None)
dataset = dataset.remove_columns([c for c in dataset["train"].column_names if c not in ("text", "label")])
print("After filter:", {k: len(v) for k, v in dataset.items()})
print("Example label distribution (train):")
print(dataset["train"].to_pandas()["label"].value_counts())

# ------------------------------------------------------------
# 3. Tokenize
# ------------------------------------------------------------
print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def tokenize(batch):
    return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=MAX_LENGTH)

dataset = dataset.map(tokenize, batched=True)
dataset = dataset.remove_columns(["text"])
dataset = dataset.with_format("torch")

train_loader = DataLoader(dataset["train"], batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(dataset["validation"], batch_size=BATCH_SIZE)
test_loader  = DataLoader(dataset["test"], batch_size=BATCH_SIZE)

# ------------------------------------------------------------
# 4. Build model + optimizer + scheduler
# ------------------------------------------------------------
print("Loading Legal-BERT model...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=NUM_LABELS
).to(device)

# IMPORTANT: AdamW comes from torch.optim (it was removed from transformers)
optimizer = AdamW(model.parameters(), lr=LR)

total_steps = len(train_loader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=int(0.1 * total_steps),
    num_training_steps=total_steps,
)

# ------------------------------------------------------------
# 5. Train + evaluate, with MLflow logging
# ------------------------------------------------------------
mlflow.set_tracking_uri("file:./mlruns")  # local mlruns/ folder inside Colab
mlflow.set_experiment("legal-doc-classifier")

def evaluate(loader):
    model.eval()
    preds, labels_list = [], []
    total_loss = 0.0
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            total_loss += outputs.loss.item()
            preds.extend(torch.argmax(outputs.logits, dim=-1).cpu().numpy())
            labels_list.extend(batch["labels"].cpu().numpy())
    avg_loss = total_loss / max(1, len(loader))
    acc = accuracy_score(labels_list, preds)
    f1 = f1_score(labels_list, preds, average="macro")
    return avg_loss, acc, f1

with mlflow.start_run():
    # Log hyperparameters
    mlflow.log_params({
        "model_name": MODEL_NAME,
        "max_length": MAX_LENGTH,
        "batch_size": BATCH_SIZE,
        "epochs": EPOCHS,
        "lr": LR,
        "num_labels": NUM_LABELS,
        "seed": SEED,
    })

    for epoch in range(1, EPOCHS + 1):
        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader):
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            running_loss += loss.item()

        train_loss = running_loss / max(1, len(train_loader))
        val_loss, val_acc, val_f1 = evaluate(val_loader)

        print(f"Epoch {epoch}/{EPOCHS} | "
              f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
              f"val_acc={val_acc:.4f} val_f1={val_f1:.4f}")

        mlflow.log_metrics({
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_accuracy": val_acc,
            "val_f1_score": val_f1,
        }, step=epoch)

    # Final test metrics
    test_loss, test_acc, test_f1 = evaluate(test_loader)
    print(f"TEST | loss={test_loss:.4f} acc={test_acc:.4f} f1={test_f1:.4f}")
    mlflow.log_metrics({
        "test_loss": test_loss,
        "test_accuracy": test_acc,
        "test_f1_score": test_f1,
    })

    # ------------------------------------------------------------
    # 6. Save model to MLflow AND locally
    # ------------------------------------------------------------
    mlflow.pytorch.log_model(model, "legal_bert_model")

    os.makedirs(SAVE_DIR, exist_ok=True)
    model.save_pretrained(SAVE_DIR)
    tokenizer.save_pretrained(SAVE_DIR)

    # Save a tiny label map so the API can decode predictions
    with open(os.path.join(SAVE_DIR, "label_map.txt"), "w") as f:
        for new_id, name in NEW_TO_NAME.items():
            f.write(f"{new_id}\t{name}\n")

    print(f"Model + tokenizer saved to {SAVE_DIR}")

# ------------------------------------------------------------
# 7. Zip the saved_model folder so we can download it from Colab
# ------------------------------------------------------------
# !zip -r saved_model.zip saved_model
# from google.colab import files
# files.download("saved_model.zip")
