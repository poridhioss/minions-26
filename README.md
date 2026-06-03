# Legal Document Classifier

End-to-end ML pipeline that classifies legal text into one of four
categories — **Criminal Procedure**, **Civil Rights**, **First Amendment**,
**Economic Activity** — using a fine-tuned **Legal-BERT** model served
through **FastAPI**, packaged with **Docker**, and tracked with **MLflow**.

The model is fine-tuned on the SCOTUS split of the
[LexGLUE](https://huggingface.co/datasets/coastalcph/lex_glue) benchmark,
then exported and served as a REST API for inference.

---

## What it does

Given a paragraph of legal text, the API returns the most likely SCOTUS
topic area along with a confidence score. The same `predict()` function
powers both the FastAPI endpoint and any client that can `POST` JSON, so
the model can be plugged into a web app, a notebook, or a CI smoke test
without changes.

---

## Architecture

```
                 +--------------------+
   Colab         |   train/train.py   |
   (GPU)         |  - load LexGLUE    |
                 |  - filter 4 labels |
                 |  - fine-tune       |
                 |    Legal-BERT      |
                 |  - log to MLflow   |
                 +---------+----------+
                           |
                           v
                  saved_model/  (zip, downloaded)
                           |
                           v
                 +--------------------+        +----------------+
   Local         |   app/main.py      |        |  saved_model/  |
   (Docker)      |   FastAPI          |<------>|  (Legal-BERT)  |
                 |   POST /predict    |        +----------------+
                 |                    |
                 |   app/             |
                 |   model_loader.py  |
                 |   - load once      |
                 |   - inference      |
                 +---------+----------+
                           |
                           v
                 +--------------------+
                 |  docker-compose    |
                 |  - api   :8000     |
                 |  - mlflow :5000    |
                 +--------------------+
```

---

## Project layout

```
legal-doc-classifier/
├── saved_model/          ← already-trained model (copied from Colab)
├── app/
│   ├── __init__.py       ← makes `app` a Python package
│   ├── main.py           ← FastAPI app (POST /predict)
│   └── model_loader.py   ← loads Legal-BERT and exposes predict()
├── train/
│   └── train.py          ← Colab training script
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

> **Note:** `saved_model/` is excluded from git (it is ~400 MB). Train the
> model in Colab first, then drop the resulting folder at the project root
> before running `docker compose up`.

---

## 1. Train the model in Google Colab

The training script lives at [`train/train.py`](./train/train.py). You can
also run it directly in a hosted Colab notebook — see the link in the
project description (or open `train/train.py` in Colab via
`File → Upload notebook`).

1. Open Google Colab and set the runtime to **GPU**:
   `Runtime → Change runtime type → T4 GPU`.
2. Upload `train/train.py` (or paste its contents into a single cell).
3. Install dependencies in a first cell:
   ```python
   !pip install -q transformers torch datasets mlflow scikit-learn
   ```
4. Run the training script. It will:
   - Load and filter the LexGLUE SCOTUS dataset to the 4 target classes.
   - Tokenize with `nlpaueb/legal-bert-base-uncased` (`max_length=512`).
   - Fine-tune for 3 epochs, batch size 8, learning rate 2e-5.
   - Log hyperparameters and metrics (accuracy, F1, loss) to MLflow.
   - Save the model + tokenizer to `./saved_model/`.
5. Download the folder:
   ```python
   !zip -r saved_model.zip saved_model
   from google.colab import files
   files.download("saved_model.zip")
   ```
6. Unzip the archive into the project root so the folder structure matches
   the layout above (the folder is named `saved_model/`).

---

## 2. Run locally with Docker

Requirements: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

From the project root:

```bash
docker-compose up --build
```

This starts two services:

| Service | Port | URL                         |
|---------|------|-----------------------------|
| `api`   | 8000 | http://localhost:8000       |
| `mlflow`| 5000 | http://localhost:5000       |

- The FastAPI docs are available at http://localhost:8000/docs
- The MLflow UI is available at http://localhost:5000

To stop both containers, press `Ctrl+C` and then run `docker-compose down`.

---

## 3. Test the API

Open a second PowerShell window once `docker compose up` shows the API
listening on port 8000.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
  -ContentType "application/json" `
  -Body '{"text": "The defendant was charged with assault and battery."}'
```

Expected response:

```json
label              confidence
-----              ----------
Criminal Procedure     0.8421
```

A health check is also available:

```powershell
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## 4. How it works

- **`train/train.py`** — fine-tunes `nlpaueb/legal-bert-base-uncased` on
  LexGLUE SCOTUS, keeping only labels `0, 1, 2, 8` (remapped to `0, 1, 2, 3`).
  Uses `AdamW` from `torch.optim` and `get_linear_schedule_with_warmup` from
  `transformers`. Logs everything to MLflow.
- **`app/model_loader.py`** — loads the tokenizer and model from
  `saved_model/` exactly once. `predict(text)` returns
  `(label_name, confidence)`.
- **`app/main.py`** — exposes a single `POST /predict` endpoint. The model
  is loaded during the FastAPI lifespan (at startup), not per request.
- **`Dockerfile`** — builds a slim `python:3.10` image, installs
  `requirements.txt`, copies the model and app, then launches uvicorn.
- **`docker-compose.yml`** — runs the API on port `8000` (with
  `MODEL_DIR=/app/saved_model`) and the MLflow tracking server on port
  `5000`.

---

## API response preview

```
PS> Invoke-RestMethod -Method Post -Uri "http://localhost:8000/predict" `
      -ContentType "application/json" `
      -Body '{"text":"The defendant was charged with assault and battery."}'

label              confidence
-----              ----------
Criminal Procedure     0.8421
```

> 📷 *Screenshot placeholder* — drop a `docs/screenshot.png` of the
> Swagger UI (`http://localhost:8000/docs`) or the response above and
> embed it like this:
> `![API response](docs/screenshot.png)`

---

## Requirements

- Docker (for the all-in-one local run)
- Python 3.10+ (only if you want to run uvicorn directly without Docker)
