---
title: Legal Document Classifier
emoji: ⚖️
colorFrom: indigo
colorTo: purple
sdk: static
pinned: false
license: mit
---

# ⚖️ Legal Document Classifier

A pure-client-side demo of a fine-tuned **Legal-BERT** checkpoint,
served from Hugging Face Spaces' free **Static SDK** tier.

This Space runs **zero Python** in the browser tab. The 418 MB
checkpoint is hosted on a separate Hugging Face Hub model repo,
and the HTML page calls HF Inference Endpoints directly from the
visitor's browser using a `text-classification` task.

Because Static SDK does not run any backend, there is:

- **No hardware to select** (Static is always free).
- **No sleep** (no Python process to put to sleep).
- **No `HF_TOKEN` secret** (Static Spaces cannot keep server-side
  secrets — set `window.HF_CONFIG.model` to a *public*
  inference-enabled Hub model, or to a private repo and ship the
  token literally in this page, accepting the visibility tradeoff).

## Configuration

Edit the `HF_CONFIG` object near the top of `index.html`:

```js
window.HF_CONFIG = {
  model: "your-username/legal-bert-scotus",
  token: ""  // leave empty for a public Hub model
};
```

## Local development

Open `index.html` in a browser — there is nothing to install or build.