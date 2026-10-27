"""Retrieval-augmented generation tools."""

from langchain_core.tools import tool


@tool
def search_career_resources(
    query: str,
    topic: str = "career development",
) -> str:
    """Prepare a resource search; connect a document index to retrieve sources."""

    return (
        f"Resource search query: {query}\n"
        f"Topic: {topic}\n"
        "No resource index is connected yet. Add a retrieval backend to "
        "return sourced results."
    )


TOOLS = [search_career_resources]