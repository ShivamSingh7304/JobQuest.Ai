
"""Tools for knowledge retrieval in JobQuest.Ai."""

from typing import Any

from langchain_core.tools import tool

from jobquest_ai.retrieval.retriever import retrieve


@tool
def search_knowledge(query: str, k: int = 4) -> dict[str, Any]:
    """
    Retrieve relevant documents for a user query.

    Args:
        query: The user's search question.
        k: Maximum number of documents to retrieve.

    Returns:
        A dictionary containing the query and retrieved results.
    """
    query = query.strip()

    if not query:
        raise ValueError("Search query cannot be empty.")

    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 10:
        raise ValueError("k must be an integer between 1 and 10.")

    documents = retrieve(query, k=k)

    results = []

    for doc in documents:
        results.append(
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source"),
                "page": doc.metadata.get("page"),
            }
        )

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results,
    }


TOOLS = [search_knowledge]
