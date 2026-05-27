"""
Embeddings + FAISS vector store.
Chunks text, embeds with all-MiniLM-L6-v2, stores in FAISS with metadata.
"""
import json
import logging
import pickle
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import EMBEDDING_MODEL, FAISS_INDEX_DIR, CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
INDEX_PATH = FAISS_INDEX_DIR / "index.faiss"
META_PATH = FAISS_INDEX_DIR / "metadata.pkl"

_model: SentenceTransformer | None = None
_index: faiss.IndexFlatL2 | None = None
_metadata: list[dict] = []


def _get_model() -> SentenceTransformer | None:
    global _model
    import os
    if os.getenv("DISABLE_EMBEDDINGS", "").lower() in ("1", "true", "yes"):
        return None
    if _model is None:
        logger.info("[Embedder] Loading model: %s", EMBEDDING_MODEL)
        try:
            _model = SentenceTransformer(EMBEDDING_MODEL)
        except Exception as exc:
            logger.warning("[Embedder] Model load failed — embeddings disabled: %s", exc)
            return None
    return _model


def _get_index() -> tuple[faiss.IndexFlatL2, list[dict]]:
    global _index, _metadata
    if _index is not None:
        return _index, _metadata

    if INDEX_PATH.exists() and META_PATH.exists():
        _index = faiss.read_index(str(INDEX_PATH))
        with open(META_PATH, "rb") as f:
            _metadata = pickle.load(f)
        logger.info("[Embedder] Loaded index: %d vectors", _index.ntotal)
    else:
        dim = _get_model().get_sentence_embedding_dimension()
        _index = faiss.IndexFlatL2(dim)
        _metadata = []
        logger.info("[Embedder] Created new FAISS index (dim=%d)", dim)

    return _index, _metadata


def _save_index():
    index, meta = _get_index()
    faiss.write_index(index, str(INDEX_PATH))
    with open(META_PATH, "wb") as f:
        pickle.dump(meta, f)


def _chunk_text(text: str) -> list[str]:
    """Sentence-aware chunking with sliding window overlap."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    chunks = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        words = sentence.split()
        if current_len + len(words) > CHUNK_SIZE and current:
            chunks.append(". ".join(current) + ".")
            # Keep overlap sentences
            overlap_words = 0
            overlap: list[str] = []
            for s in reversed(current):
                overlap_words += len(s.split())
                if overlap_words >= CHUNK_OVERLAP:
                    break
                overlap.insert(0, s)
            current = overlap
            current_len = sum(len(s.split()) for s in current)
        current.append(sentence)
        current_len += len(words)

    if current:
        chunks.append(". ".join(current) + ".")

    return chunks or [text[:2000]]


def embed_and_store(text: str, metadata: dict[str, Any]):
    """Chunk text, embed, and add to FAISS index."""
    model = _get_model()
    if model is None:
        return

    chunks = _chunk_text(text)
    if not chunks:
        return
    index, meta = _get_index()

    vectors = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)
    vectors = np.array(vectors, dtype="float32")

    index.add(vectors)
    for i, chunk in enumerate(chunks):
        meta.append({**metadata, "chunk_index": i, "text": chunk})

    _save_index()
    logger.info("[Embedder] Stored %d chunks from %s", len(chunks), metadata.get("source", "?"))


def embed_transactions_as_text():
    """Convert all stored transactions to text chunks and embed them."""
    from backend.storage.database import db
    with db() as conn:
        rows = conn.execute(
            "SELECT date, description, amount, category, transaction_type FROM transactions"
        ).fetchall()

    lines = [
        f"Date: {r['date']} | Merchant: {r['description']} | "
        f"Amount: {r['amount']} | Category: {r['category']} | Type: {r['transaction_type']}"
        for r in rows
    ]
    if not lines:
        return

    text = "\n".join(lines)
    embed_and_store(text, {"source": "transactions_structured"})
    logger.info("[Embedder] Embedded %d transaction rows", len(lines))


def search(query: str, top_k: int = 5) -> list[dict]:
    """Search FAISS for the top-k most relevant chunks."""
    model = _get_model()
    if model is None:
        return []

    index, meta = _get_index()

    if index.ntotal == 0:
        return []

    query_vec = model.encode([query], normalize_embeddings=True)
    query_vec = np.array(query_vec, dtype="float32")

    distances, indices = index.search(query_vec, min(top_k, index.ntotal))
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        entry = dict(meta[idx])
        entry["score"] = float(1 / (1 + dist))  # convert L2 distance to similarity score
        results.append(entry)

    return results
