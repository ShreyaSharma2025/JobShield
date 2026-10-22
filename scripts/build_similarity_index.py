"""Create a train-only FAISS index and held-out CSVs from EMSCAD/Kaggle data."""
import json
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import train_test_split

SOURCE = Path("data/fake_job_postings.csv")
DATA_DIR = Path("data")
TEXT_COLUMNS = [
    "title", "location", "employment_type", "required_experience", "required_education",
    "company_profile", "description", "requirements", "benefits",
]
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit("Place the downloaded CSV at data/fake_job_postings.csv first.")

    frame = pd.read_csv(SOURCE).fillna("")
    if "fraudulent" not in frame.columns:
        raise SystemExit("Expected a 'fraudulent' label column in the dataset.")
    text_columns = [column for column in TEXT_COLUMNS if column in frame.columns]
    if not text_columns:
        raise SystemExit("No recognized job-posting text columns were found.")

    frame["_text"] = frame[text_columns].astype(str).agg(" ".join, axis=1).str.strip()
    frame = frame.loc[frame["_text"].str.len() > 0].copy().reset_index(drop=True)
    frame["_label"] = frame["fraudulent"].astype(str).str.strip().str.lower().isin({"1", "true", "fraudulent"}).astype(int)

    train, held_out = train_test_split(
        frame, test_size=0.30, random_state=42, stratify=frame["_label"]
    )
    validation, test = train_test_split(
        held_out, test_size=0.50, random_state=42, stratify=held_out["_label"]
    )

    model = SentenceTransformer(MODEL_NAME)
    vectors = model.encode(train["_text"].tolist(), batch_size=64, normalize_embeddings=True, show_progress_bar=True)
    vectors = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(DATA_DIR / "job_postings.faiss"))

    metadata = []
    for source_row, row in train.iterrows():
        metadata.append({
            "posting_id": f"emscad-{source_row}",
            "label": "fraudulent" if row["_label"] else "legitimate",
            "title": str(row.get("title", ""))[:160],
            "excerpt": str(row.get("description", ""))[:500],
        })
    (DATA_DIR / "job_postings_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")

    for name, split in (("validation", validation), ("test", test)):
        split[["_text", "_label"]].to_csv(DATA_DIR / f"{name}_postings.csv", index=False)

    print(f"Indexed {len(train)} training postings. Validation: {len(validation)}. Test: {len(test)}.")
    print("Only the training split was placed in FAISS; held-out rows remain outside the index.")


if __name__ == "__main__":
    main()
