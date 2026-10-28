
import sys

from jobquest_ai.retrieval.retriever import (
    index_documents,
    retrieve,
)

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

# STEP 1: Index your built-in knowledge base.
index_result = index_documents(
    source_path="ai-roadmap.pdf",
    metadata={"category": "interview_preparation"},
)

print("Indexing result:")
print(index_result["chunks_created"], "chunks created")
print(index_result["chunks_indexed"], "chunks indexed")

# STEP 2: Ask a question.
results = retrieve(
    query="How should I prepare for a ai developer interview?",
    top_k=3,
)

# STEP 3: Inspect the retrieved evidence.
for number, result in enumerate(results, start=1):
    print(f"\nResult {number}")
    print("Source:", result["source"])
    print("Score:", result["score"])
    print("Content:", result["content"])
