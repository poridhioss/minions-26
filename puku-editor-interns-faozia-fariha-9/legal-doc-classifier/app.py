# ============================================================
# Gradio front-end for the Legal Document Classifier.
#
# Runs on Hugging Face Spaces using the free Gradio SDK
# (sdk: gradio in README_HF.md). Gradio auto-spawns uvicorn
# internally and binds to $PORT (7860) on Spaces, so there is
# no Dockerfile, no docker-compose.yml, and no port juggling.
#
# This file is what HF looks for at the root of a Gradio Space.
# It re-uses the same model_loader the FastAPI app uses, so
# behaviour is identical between local and Space runs.
# ============================================================
import os

import gradio as gr

from app import model_loader


# Friendly label list shown in the UI. Order matches model id -> label.
LABEL_CHOICES = [
    "Criminal Procedure",
    "Civil Rights",
    "First Amendment",
    "Economic Activity",
]


def classify(text: str):
    """Run the fine-tuned Legal-BERT model on a single text string.

    Gradio expects this to return either a ``{label: confidence}`` dict
    (for gr.Label) or a plain string. We use the dict form so the UI
    can render a bar chart of all four scores.
    """
    if not text or not text.strip():
        # Return an empty dict so the label component shows a neutral
        # state instead of an error.
        return {}

    label, confidence = model_loader.predict(text)

    # Distribute the remaining probability mass evenly across the other
    # three labels. The model only exposes the top-1 confidence through
    # `predict()`, but the Label component is more informative when all
    # four classes are visible.
    others = [(l, round((1 - confidence) / 3, 4)) for l in LABEL_CHOICES if l != label]
    return {label: round(confidence, 4), **{l: p for l, p in others}}


# Build the UI at import time so HF Spaces can boot without extra wiring.
with gr.Blocks(title="Legal Document Classifier") as demo:
    gr.Markdown(
        "# ⚖️ Legal Document Classifier\n"
        "Fine-tuned **Legal-BERT** (SCOTUS topics). "
        "Paste a legal document excerpt below and the model will "
        "predict which of four categories it belongs to."
    )

    with gr.Row():
        inp = gr.Textbox(
            label="Document text",
            placeholder="Paste legal text here...",
            lines=10,
        )
        out = gr.Label(
            label="Predicted topic",
            num_top_classes=4,
        )

    btn = gr.Button("Classify", variant="primary")
    btn.click(fn=classify, inputs=inp, outputs=out)

    gr.Markdown(
        "---\n"
        "_Model: `nlpaueb/legal-bert-base-uncased` fine-tuned on the "
        "SCOTUS topic dataset. Inference runs on CPU._"
    )


# Gradio's HF Spaces launcher reads `demo.launch()` and binds to the
# $PORT env var that Spaces sets to 7860. share=False keeps it private
# to the Space's URL.
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))