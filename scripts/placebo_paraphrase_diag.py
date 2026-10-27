"""Placebo-paraphrase embedding diagnostic.

Computes cosine similarity between the S+C- originals and their matched
placebo paraphrases (100 personas) with gemini-embedding-001, to check
whether the placebo cell measures original-text preference or degraded
paraphrases. Reference values from the paper: entity-strip similarity
0.889 (sd 0.025), content-axis similarity 0.665 (sd 0.057).

Result as of 2026-10-15: mean 0.993, sd 0.003, min 0.981 - the
paraphrase is a near-identical semantic match, so the placebo measures
original-text preference (the paper's Placebo Pair subsection cites
this).

Usage: .venv/bin/python scripts/placebo_paraphrase_diag.py
Run from the repo root. Requires GEMINI_API_KEY in .env.
Saves: outputs/n100/placebo_para_sims.csv
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)  # stale shell keys burned us before

from google import genai  # noqa: E402
from config import OUTPUTS_DIR  # noqa: E402


def embed_batch(client, texts, batch=100):
    out = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        r = client.models.embed_content(
            model="gemini-embedding-001",
            contents=chunk,
            config={"output_dimensionality": 768},
        )
        out.extend([np.array(e.values, dtype=float) for e in r.embeddings])
    return out


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    orig = pd.read_csv(OUTPUTS_DIR / "dissociation_emails_100.csv")
    para = pd.read_csv(OUTPUTS_DIR / "n100" / "placebo_emails.csv")
    df = orig[["target_id", "S+C-_body"]].merge(para, on="target_id")
    print(f"pairs: {len(df)}")

    texts = list(df["S+C-_body"].astype(str)) + list(df["para_body"].astype(str))
    embs = embed_batch(client, texts)
    n = len(df)
    A = np.stack(embs[:n])
    B = np.stack(embs[n:])
    A = A / np.linalg.norm(A, axis=1, keepdims=True)
    B = B / np.linalg.norm(B, axis=1, keepdims=True)
    sims = (A * B).sum(axis=1)

    print(f"cosine similarity paraphrase-vs-original: "
          f"mean={sims.mean():.3f} sd={sims.std():.3f} "
          f"min={sims.min():.3f} max={sims.max():.3f}")
    print("reference: entity-strip 0.889 (sd 0.025), "
          "content axis 0.665 (sd 0.057)")

    out = pd.DataFrame({"target_id": df["target_id"], "para_similarity": sims})
    out_path = OUTPUTS_DIR / "n100" / "placebo_para_sims.csv"
    out.to_csv(out_path, index=False)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
