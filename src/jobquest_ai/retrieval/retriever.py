import logging
from pathlib import Path
from typing import Any
from qdrant_client import models
from jobquest_ai.retrieval.ingestion import (
    load_and_split_documents,
)
from jobquest_ai.retrieval.vector_store import (
    add_documents,
    get_qdrant_vector_store,
)

logger = logging.getLogger(__name__)
class RetrievalError(Exception):
    """Raised when indexing or retrieval fails."""

def index_documents(
    source_path: str | Path,
    metadata: dict[str, Any] | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> dict[str, Any]:
    """
    Load, split, and index one file or a directory of documents.

    Optional metadata can label documents, for example:
    {"technology": "Python", "version": "3.12"}
    """

    logger.info("retrieval_index_started source=%s", source_path)
    try:
        chunks = load_and_split_documents(
            source_path=source_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            metadata=metadata,
        )

        ids = add_documents(chunks)

        result = {
            "source_path": str(source_path),
            "chunks_created": len(chunks),
            "chunks_indexed": len(ids),
            "document_ids": ids,
        }
        logger.info("retrieval_index_completed chunks=%s indexed=%s", len(chunks), len(ids))
        return result

    except Exception as exc:
        logger.exception("retrieval_index_failed source=%s", source_path)
        raise RetrievalError(
            f"Document indexing failed: {exc}"
        ) from exc


def retrieve(
    query: str,
    top_k: int = 5,
    technology: str | None = None,
    version: str | None = None,
    metadata_filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve relevant document chunks for a query.

    Returns a list of dictionaries containing:
    content, source, metadata, and score.

    Score is the raw score returned by the vector-store
    integration, not a percentage or guaranteed probability.
    """

    logger.info("retrieval_started query_length=%s top_k=%s", len(query) if isinstance(query, str) else 0, top_k)
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    filters = dict(metadata_filters or {})

    if technology is not None:
        filters["technology"] = technology

    if version is not None:
        filters["version"] = version

    qdrant_filter = None

    if filters:
        qdrant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key=f"metadata.{key}",
                    match=models.MatchValue(value=value),
                )
                for key, value in filters.items()
            ]
        )

    try:
        vector_store = get_qdrant_vector_store()

        results = vector_store.similarity_search_with_score(
            query=query.strip(),
            k=top_k,
            filter=qdrant_filter,
        )

        retrieved = []

        for document, score in results:
            retrieved.append(
                {
                    "content": document.page_content,
                    "source": document.metadata.get("source"),
                    "metadata": document.metadata,
                    "score": float(score),
                }
            )

        logger.info("retrieval_completed result_count=%s", len(retrieved))
        return retrieved

    except Exception as exc:
        logger.exception("retrieval_failed")
        raise RetrievalError(
            f"Knowledge retrieval failed: {exc}"
        ) from exc
