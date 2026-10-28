
"""Tests for JobQuest.Ai resume and retrieval tools."""

from unittest.mock import MagicMock, patch

import pytest

from jobquest_ai.tools.resume_tools import analyze_uploaded_resume
from jobquest_ai.tools.retrieval_tools import search_knowledge


# =========================================================
# Resume Tool Tests
# =========================================================

def test_resume_file_not_found():
    """A missing resume should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        analyze_uploaded_resume("nonexistent_resume.pdf")


def test_analyze_uploaded_resume_success(tmp_path):
    """A valid resume should be parsed and analyzed."""
    resume_file = tmp_path / "resume.pdf"
    resume_file.write_bytes(b"dummy PDF content")

    sample_text = (
        "Python developer with experience in Python, SQL, "
        "machine learning, and data analysis."
    )

    sample_analysis = {
        "skills": ["Python", "SQL", "Machine Learning"],
        "score": 85,
    }

    with (
        patch(
            "jobquest_ai.tools.resume_tools.parse_resume",
            return_value=sample_text,
        ) as mock_parser,
        patch(
            "jobquest_ai.tools.resume_tools.analyze_resume",
            return_value=sample_analysis,
        ) as mock_analyzer,
    ):
        result = analyze_uploaded_resume(str(resume_file))

    mock_parser.assert_called_once_with(str(resume_file))
    mock_analyzer.assert_called_once_with(sample_text)

    assert result["success"] is True
    assert result["file_name"] == "resume.pdf"
    assert result["analysis"] == sample_analysis


def test_resume_with_empty_extracted_text(tmp_path):
    """Empty extracted text should raise ValueError."""
    resume_file = tmp_path / "empty.pdf"
    resume_file.write_bytes(b"dummy PDF content")

    with patch(
        "jobquest_ai.tools.resume_tools.parse_resume",
        return_value="   ",
    ):
        with pytest.raises(ValueError, match="No readable text"):
            analyze_uploaded_resume(str(resume_file))


# =========================================================
# Retrieval Tool Tests
# =========================================================

def test_search_knowledge_success():
    """Relevant documents should be returned in a dictionary."""
    mock_document = MagicMock()
    mock_document.page_content = "Python is a programming language."
    mock_document.metadata = {
        "source": "python_guide.pdf",
        "page": 2,
    }

    with patch(
        "jobquest_ai.tools.retrieval_tools.retrieve",
        return_value=[mock_document],
    ) as mock_retrieve:
        result = search_knowledge(
            "  What is Python?  ",
            k=4,
        )

    mock_retrieve.assert_called_once_with("What is Python?", k=4)

    assert result["success"] is True
    assert result["query"] == "What is Python?"
    assert result["count"] == 1
    assert result["results"][0]["content"] == (
        "Python is a programming language."
    )
    assert result["results"][0]["source"] == "python_guide.pdf"
    assert result["results"][0]["page"] == 2


def test_search_knowledge_empty_query():
    """An empty query should raise ValueError."""
    with pytest.raises(ValueError, match="query cannot be empty"):
        search_knowledge("   ")


@pytest.mark.parametrize("invalid_k", [0, -1, 11, 2.5, True])
def test_search_knowledge_invalid_k(invalid_k):
    """Invalid result limits should raise ValueError."""
    with pytest.raises(ValueError, match="between 1 and 10"):
        search_knowledge("Python", k=invalid_k)


def test_search_knowledge_no_results():
    """No matching documents should return an empty results list."""
    with patch(
        "jobquest_ai.tools.retrieval_tools.retrieve",
        return_value=[],
    ) as mock_retrieve:
        result = search_knowledge("Unknown topic")

    mock_retrieve.assert_called_once_with("Unknown topic", k=4)

    assert result["success"] is True
    assert result["count"] == 0
    assert result["results"] == []
