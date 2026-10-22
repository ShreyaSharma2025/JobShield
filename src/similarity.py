"""Search the development portion of the labeled posting dataset with FAISS."""
import json
import os
from pathlib import Path

from .paths import DATA_DIR

INDEX_PATH = DATA_DIR / "job_postings.faiss"
METADATA_PATH = DATA_DIR / "job_postings_metadata.json"
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def search_similar_postings(text: str, top_k: int = 5) -> list[dict]:
    """Return nearest indexed training rows; empty means no index was built."""
    if not INDEX_PATH.exists() or not METADATA_PATH.exists():
        return []

    import faiss
    from sentence_transformers import SentenceTransformer

    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)
    index = faiss.read_index(str(INDEX_PATH))
    model = SentenceTransformer(MODEL_NAME)
    query = model.encode([text], normalize_embeddings=True).astype("float32")
    scores, positions = index.search(query, min(top_k, len(metadata)))

    matches = []
    for score, position in zip(scores[0], positions[0]):
        if position < 0:
            continue
        row = metadata[position]
        matches.append({**row, "similarity": round(float(score), 4)})
    return matches
