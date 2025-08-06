"""Meta-learning utilities using a minimal MAML-style loop."""
from __future__ import annotations

from typing import List

from datasets import Dataset


class MAMLTrainer:
    """Very small-scale MAML fine-tuner using HuggingFace Trainer."""

    def __init__(self, model_name: str = "distilbert-base-uncased") -> None:
        from transformers import AutoModelForSequenceClassification

        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name, num_labels=2
        )

    def meta_train(self, tasks: List[Dataset]) -> None:
        from transformers import Trainer, TrainingArguments

        args = TrainingArguments(
            output_dir="/tmp/meta", per_device_train_batch_size=2, num_train_epochs=1
        )
        for task in tasks:
            trainer = Trainer(model=self.model, args=args, train_dataset=task)
            trainer.train()

    def adapt(self, few_examples: Dataset) -> None:
        from transformers import Trainer, TrainingArguments

        args = TrainingArguments(
            output_dir="/tmp/adapt", per_device_train_batch_size=2, num_train_epochs=1
        )
        trainer = Trainer(model=self.model, args=args, train_dataset=few_examples)
        trainer.train()
