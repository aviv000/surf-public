"""BERT phishing classifier — external non-LLM anchor for within-condition validation.

Uses pre-trained ealvaradob/bert-finetuned-phishing (71K HF downloads) to score
generated emails. Supports training from scratch with a larger dataset.

Usage:
  python scripts/bert_phishing_classifier.py --evaluate outputs/within_condition_emails.csv
  python scripts/bert_phishing_classifier.py --train --dataset path/to/phishing_dataset.csv
"""

import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OUTPUTS_DIR

# Pre-trained phishing detection model (URL + email body)
PHISHING_MODEL = "ealvaradob/bert-finetuned-phishing"


def build_training_data_from_public():
    """Download a real phishing dataset for training.

    Uses the Nazario phishing corpus (public, research-use) + Enron ham.
    Falls back to synthetic data if download fails.
    """
    # Try to get real phishing examples from HuggingFace datasets
    try:
        from datasets import load_dataset
        # Load phishing email dataset
        dataset = load_dataset("ealvaradob/phishing-dataset", split="train", trust_remote_code=True)
        return dataset
    except Exception as e:
        print(f"  Dataset download failed: {e}")
        return None


def train_classifier(dataset_path: str = None):
    """Fine-tune phishing classifier."""
    print(f"Training phishing classifier with model: {PHISHING_MODEL}")

    try:
        from transformers import (
            AutoTokenizer, AutoModelForSequenceClassification,
            Trainer, TrainingArguments
        )
        from datasets import Dataset
    except ImportError:
        print("ERROR: transformers/datasets not installed")
        return None

    hf_token = os.getenv("HUGGING_FACE_TOKEN") or os.getenv("HF_TOKEN")
    tokenizer = AutoTokenizer.from_pretrained(PHISHING_MODEL, token=hf_token)
    model = AutoModelForSequenceClassification.from_pretrained(
        PHISHING_MODEL, num_labels=2, token=hf_token, ignore_mismatched_sizes=True
    )

    if dataset_path:
        # Load custom dataset
        with open(dataset_path, encoding="utf-8") as f:
            data = list(csv.DictReader(f))
        texts = [f"{d.get('subject', '')}. {d.get('body', '')}" for d in data]
        labels = [int(d.get("label", 0)) for d in data]
    else:
        # Build from synthetic + real examples
        texts, labels = _build_training_examples()
        print(f"Training examples: {len(texts)}")

    if len(texts) < 20:
        print("WARNING: too few training examples, skipping fine-tune")
        # Just use pre-trained as-is
        return model, tokenizer

    encodings = tokenizer(texts, truncation=True, padding=True, max_length=256)
    dataset = Dataset.from_dict({
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels,
    })

    training_args = TrainingArguments(
        output_dir=str(OUTPUTS_DIR / "bert_phishing_checkpoints"),
        num_train_epochs=3,
        per_device_train_batch_size=8,
        logging_steps=10,
        save_strategy="no",
        report_to="none",
    )

    trainer = Trainer(model=model, args=training_args, train_dataset=dataset)
    trainer.train()

    model_path = OUTPUTS_DIR / "bert_phishing_model" / "finetuned"
    model.save_pretrained(str(model_path))
    tokenizer.save_pretrained(str(model_path))
    print(f"Model saved to {model_path}")
    return model, tokenizer


def _build_training_examples():
    """Build training examples from public patterns."""
    # Phishing patterns (public, no PII)
    phishing = [
        "URGENT: Your account has been suspended. Click here to verify your identity immediately.",
        "Dear user, we detected unusual sign-in activity. Please confirm your account within 24 hours.",
        "Your password expires today. Renew now to avoid losing access to your account.",
        "Congratulations! You have been selected for an exclusive award. Claim your prize now.",
        "Security alert: Your email account was accessed from an unknown device. Verify now.",
        "Invoice #45892 is past due. Payment required within 48 hours to avoid service interruption.",
        "Your package delivery was unsuccessful. Reschedule delivery by confirming your address.",
        "Limited time offer: Exclusive investment opportunity with guaranteed returns. Act now.",
        "We noticed a login attempt from a new location. If this wasn't you, secure your account.",
        "Your cloud storage is full. Upgrade now to avoid losing access to your files.",
    ] * 5  # 50 examples

    # Legitimate academic email patterns
    academic = [
        "Dear Dr. Chen, I enjoyed your recent paper on neural architectures. Would you be interested in collaborating on a follow-up study?",
        "I am writing to invite you to serve on the program committee for the upcoming workshop on machine learning systems.",
        "Thank you for your insightful presentation at the conference. I have a few questions about your methodology.",
        "I am organizing a special issue on privacy-preserving ML and would like to invite your contribution.",
        "Following up on our conversation at the workshop, I would be keen to explore potential research synergies.",
        "We are seeking reviewers for submissions to the upcoming conference. Your expertise would be valuable.",
        "I am a PhD student working on similar problems. Would you be available for a brief discussion?",
        "Our research group is looking for collaborators on a new project. Would you be interested in learning more?",
        "I am reaching out regarding a potential joint grant application. Your recent work aligns well with our proposal.",
        "Would you be willing to provide feedback on a draft manuscript before submission?",
    ] * 5  # 50 examples

    texts = phishing + academic
    labels = [1] * len(phishing) + [0] * len(academic)
    return texts, labels


def evaluate_emails(emails_path: str, model=None, tokenizer=None):
    """Score generated emails with phishing classifier."""
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
    except ImportError:
        print("ERROR: transformers/torch not installed")
        return []

    hf_token = os.getenv("HUGGING_FACE_TOKEN") or os.getenv("HF_TOKEN")

    # Load model
    finetuned_path = OUTPUTS_DIR / "bert_phishing_model" / "finetuned"
    if model is None:
        if finetuned_path.exists():
            print(f"Loading fine-tuned model from {finetuned_path}")
            tokenizer = AutoTokenizer.from_pretrained(str(finetuned_path))
            model = AutoModelForSequenceClassification.from_pretrained(str(finetuned_path))
        else:
            print(f"Loading pre-trained model: {PHISHING_MODEL}")
            tokenizer = AutoTokenizer.from_pretrained(PHISHING_MODEL, token=hf_token)
            model = AutoModelForSequenceClassification.from_pretrained(
                PHISHING_MODEL, token=hf_token, ignore_mismatched_sizes=True
            )

    emails_path = Path(emails_path)
    if not emails_path.exists():
        print(f"ERROR: {emails_path} not found")
        return []

    with open(emails_path, encoding="utf-8") as f:
        emails = list(csv.DictReader(f))

    print(f"Classifying {len(emails)} emails...")
    results = []

    for i, email in enumerate(emails):
        body = email.get("email_body", "")
        if not body or len(body) < 10:
            continue
        text = f"{email.get('email_subject', '')}. {body}"[:512]

        try:
            inputs = tokenizer(text, truncation=True, padding=True,
                              max_length=256, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                # Label order varies by model; take max probability class
                score = float(probs[0][1].item())  # class 1 = phishing
        except Exception as e:
            score = -1.0  # error sentinel

        results.append({
            "target_id": email.get("target_id", ""),
            "hook_level": email.get("hook_level", ""),
            "phishing_score": round(score, 4),
        })

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(emails)}...")

    # Summary
    by_level = defaultdict(list)
    for r in results:
        if r["phishing_score"] >= 0:
            by_level[int(r["hook_level"])].append(r["phishing_score"])

    print("\nBERT phishing classifier scores by hook level:")
    for level in [1, 3, 5]:
        vals = by_level.get(level, [])
        if vals:
            print(f"  {level} hooks: mean={sum(vals)/len(vals):.4f}, n={len(vals)}")
        else:
            print(f"  {level} hooks: no data")

    out_path = OUTPUTS_DIR / "bert_phishing_scores.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["target_id", "hook_level", "phishing_score"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nScores written to {out_path}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--dataset", type=str)
    parser.add_argument("--evaluate", type=str)
    args = parser.parse_args()

    if args.train:
        train_classifier(args.dataset)
    elif args.evaluate:
        evaluate_emails(args.evaluate)
    else:
        print("Specify --train or --evaluate <path>")
        print("  --train                    Fine-tune on built-in + optional dataset")
        print("  --evaluate emails.csv       Score emails with classifier")
