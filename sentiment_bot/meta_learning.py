from __future__ import annotations

from typing import List

from datasets import Dataset


class MAMLTrainer:
    """Very small-scale MAML fine-tuner using HuggingFace Trainer."""

    def __init__(self, model_name: str = "distilbert-base-uncased") -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name, num_labels=2
        )

    def _tokenise(self, ds: Dataset) -> Dataset:
        return ds.map(
            lambda e: self.tokenizer(e["text"], truncation=True, padding="max_length"),
            batched=True,
        )

    def meta_train(self, tasks: List[Dataset]) -> None:
        from transformers import Trainer, TrainingArguments

        args = TrainingArguments(
            output_dir="/tmp/meta", per_device_train_batch_size=2, num_train_epochs=1
        )
        for task in tasks:
            enc = self._tokenise(task)
            trainer = Trainer(model=self.model, args=args, train_dataset=enc)
            trainer.train()

    def adapt(self, few_examples: Dataset) -> None:
        from transformers import Trainer, TrainingArguments

        args = TrainingArguments(
            output_dir="/tmp/adapt", per_device_train_batch_size=2, num_train_epochs=1
        )
        enc = self._tokenise(few_examples)
        trainer = Trainer(model=self.model, args=args, train_dataset=enc)
        trainer.train()
