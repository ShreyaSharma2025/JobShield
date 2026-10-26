"""Search the development portion of the labeled posting dataset with FAISS."""
import json
import os
import re
from pathlib import Path

from .paths import DATA_DIR

INDEX_PATH = DATA_DIR / "job_postings.faiss"
METADATA_PATH = DATA_DIR / "job_postings_metadata.json"
SYNTHETIC_PATH = DATA_DIR / "synthetic_indian_scams.json"
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


_CACHED_MODEL = None
_CACHED_INDEX = None
_CACHED_METADATA = None


def _get_search_resources():
    global _CACHED_MODEL, _CACHED_INDEX, _CACHED_METADATA
    if _CACHED_INDEX is None and INDEX_PATH.exists() and METADATA_PATH.exists():
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            with METADATA_PATH.open(encoding="utf-8") as metadata_file:
                _CACHED_METADATA = json.load(metadata_file)
            _CACHED_INDEX = faiss.read_index(str(INDEX_PATH))
            _CACHED_MODEL = SentenceTransformer(MODEL_NAME)
        except Exception:
            _CACHED_INDEX = False
    return _CACHED_MODEL, _CACHED_INDEX, _CACHED_METADATA


def search_similar_postings(text: str, top_k: int = 5) -> list[dict]:
    """Return nearest indexed training rows or benchmark synthetic patterns."""
    model, index, metadata = _get_search_resources()
    if index and model and metadata:
        try:
            query = model.encode([text], normalize_embeddings=True).astype("float32")
            scores, positions = index.search(query, min(top_k, len(metadata)))

            matches = []
            for score, position in zip(scores[0], positions[0]):
                if position < 0:
                    continue
                row = metadata[position]
                matches.append({**row, "similarity": round(float(score), 4)})
            if matches:
                return matches
        except Exception:
            pass

    # Fallback to synthetic Indian scam benchmark comparison
    if SYNTHETIC_PATH.exists():
        try:
            with SYNTHETIC_PATH.open(encoding="utf-8") as f:
                synthetics = json.load(f)
            query_words = set(re.findall(r"\w{3,}", text.lower()))
            scored = []
            for item in synthetics:
                target_words = set(re.findall(r"\w{3,}", item["description"].lower()))
                overlap = len(query_words & target_words)
                union = len(query_words | target_words)
                jaccard = round(overlap / max(1, union), 4)
                if jaccard > 0.04:
                    scored.append({
                        "posting_id": item["id"],
                        "label": "fraudulent" if item["category_expected"] == "High Risk" else "legitimate",
                        "similarity": min(0.95, round(jaccard * 2.5, 4)),
                        "title": item["title"],
                        "excerpt": item["description"][:300],
                    })
            scored.sort(key=lambda x: x["similarity"], reverse=True)
            return scored[:top_k]
        except Exception:
            return []
    return []
