---
title: Legal Document Classifier
emoji: ⚖️
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# ⚖️ Legal Document Classifier

A fine-tuned **Legal-BERT** checkpoint served through a tiny **Gradio**
UI. Paste any legal-text excerpt, click **Classify**, and the model
predicts one of four SCOTUS topic areas:

- Criminal Procedure
- Civil Rights
- First Amendment
- Economic Activity

This Space runs on the **free CPU tier** of Hugging Face Spaces (16 GB
RAM, 2 vCPUs). No credit card required. The 418 MB checkpoint is kept
out of the git repo and pulled from a separate HF Hub model repo at
startup.

## How it works

pp.py is a small Gradio front-end that calls the same
pp/model_loader.py the FastAPI app uses, so inference behaviour is
identical.

model_loader resolves the checkpoint in this order:

1. $MODEL_DIR if it points at a non-empty directory.
2. The bundled ./saved_model/ if it is non-empty.
3. $HF_MODEL_ID set to a Hub model repo (default on Spaces).

## Required Space secrets

Set these in **Settings → Variables and secrets** of your Space:

| Variable      | Required      | Example                              |
| ------------- | ------------- | ------------------------------------ |
| HF_MODEL_ID | Yes           | your-username/legal-bert-scotus    |
| HF_TOKEN    | If private    | your HF access token                 |

PORT is set automatically by Spaces to 7860. Do not override it.
