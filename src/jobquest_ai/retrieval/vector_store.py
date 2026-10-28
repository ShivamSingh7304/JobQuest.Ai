
import os
import uuid
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from jobquest_ai.retrieval.embeddings import (
    get_embeddings,
    get_embedding_dimension,
)


def _get_qdrant_path() -> str:
    """Resolve the persistent local Qdrant storage path."""

    configured_path = os.getenv(
        "QDRANT_PATH",
        "data/qdrant",
    )

    path = Path(configured_path).resolve()
    path.mkdir(parents=True, exist_ok=True)

    return str(path)


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    """Return a shared persistent Qdrant client."""

    return QdrantClient(path=_get_qdrant_path())


@lru_cache(maxsize=1)
def get_qdrant_vector_store() -> QdrantVectorStore:
    """Create or connect to the JobQuest knowledge collection."""

    collection_name = os.getenv(
        "QDRANT_COLLECTION",
        "jobquest_knowledge",
    )

    client = get_qdrant_client()
    embeddings = get_embeddings()

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=get_embedding_dimension(),
                distance=models.Distance.COSINE,
            ),
        )

    return QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
        distance=models.Distance.COSINE,
    )


def _document_id(document: Document) -> str:
    """
    Generate a stable ID from source and content.
    Identical chunks from the same source get the same ID.
    """
    source = str(document.metadata.get("source", "unknown"))
    content = document.page_content

    value = f"{source}\0{content}"

    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def add_documents(documents: list[Document]) -> list[str]:
    """Insert or update document chunks in Qdrant."""

    if not documents:
        return []

    vector_store = get_qdrant_vector_store()

    ids = [_document_id(document) for document in documents]

    return vector_store.add_documents(
        documents=documents,
        ids=ids,
    )


def get_collection_name() -> str:
    """Return the configured collection name."""
    return os.getenv(
        "QDRANT_COLLECTION",
        "jobquest_knowledge",
    )
