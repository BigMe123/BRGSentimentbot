"""Explainability tools using gradient-based attributions."""

from __future__ import annotations

from typing import Dict

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

_tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
_model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased")
_model.eval()


def explain_article(text: str) -> Dict[str, float]:
    """Return simple gradient * input attributions for tokens."""

    inputs = _tokenizer(text, return_tensors="pt")
    input_ids = inputs["input_ids"]
    embeds = _model.get_input_embeddings()(input_ids)
    embeds.retain_grad()
    output = _model(inputs_embeds=embeds).logits[0, 1]
    output.backward()
    grads = embeds.grad[0]
    attributions = (grads * embeds[0]).sum(dim=-1)
    tokens = _tokenizer.convert_ids_to_tokens(input_ids[0])
    return {tok: float(attr) for tok, attr in zip(tokens, attributions)}
