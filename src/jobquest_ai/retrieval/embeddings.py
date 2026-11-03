
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings


DEFAULT_EMBEDDING_MODEL = (
    "sentence-transformers/all-MiniLM-L6-v2"
)


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """
    Return a shared embedding model for document indexing
    and query retrieval.
    """
    return HuggingFaceEmbeddings(
        model_name=DEFAULT_EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def embed_text(text: str) -> list[float]:
    """Convert one text string into an embedding vector."""

    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    return get_embeddings().embed_query(text)


def get_embedding_dimension() -> int:
    """Return the embedding model's vector dimension."""
    return len(embed_text("JobQuest.Ai embedding dimension check"))
