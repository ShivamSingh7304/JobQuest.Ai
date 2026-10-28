from unittest.mock import patch

import pytest

from jobquest_ai.workflows.resume_workflow import run_resume_workflow


def test_resume_workflow_success(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"dummy content")

    mock_result = {
        "success": True,
        "file_name": "resume.pdf",
        "analysis": {
            "skills": ["Python", "SQL"],
            "score": 85,
        },
    }

    with patch(
        "jobquest_ai.workflows.resume_workflow.analyze_uploaded_resume",
        return_value=mock_result,
    ) as mock_analyze:
        result = run_resume_workflow(str(resume))

    mock_analyze.assert_called_once_with(str(resume))
    assert result["success"] is True
    assert result["workflow"] == "resume_analysis"
    assert result["status"] == "awaiting_review"
    assert result["analysis"]["skills"] == ["Python", "SQL"]
    assert result["human_review"]["required"] is True
    assert result["human_review"]["status"] == "pending"
    assert result["next_action"] == "review_resume_analysis"


@pytest.mark.parametrize("file_path", ["", "   ", None, 123])
def test_resume_workflow_rejects_empty_or_invalid_path(file_path):
    with pytest.raises(ValueError, match="cannot be empty"):
        run_resume_workflow(file_path)


def test_resume_workflow_analysis_failure(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"dummy content")

    with patch(
        "jobquest_ai.workflows.resume_workflow.analyze_uploaded_resume",
        return_value={"success": False},
    ):
        with pytest.raises(ValueError, match="could not be completed"):
            run_resume_workflow(str(resume))


@pytest.mark.parametrize("tool_result", [{"success": True}, {"success": True, "analysis": None}])
def test_resume_workflow_rejects_missing_analysis(tmp_path, tool_result):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"dummy content")

    with patch(
        "jobquest_ai.workflows.resume_workflow.analyze_uploaded_resume",
        return_value=tool_result,
    ):
        with pytest.raises(ValueError, match="missing the analysis data"):
            run_resume_workflow(str(resume))


def test_resume_workflow_rejects_invalid_tool_result(tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"dummy content")

    with patch(
        "jobquest_ai.workflows.resume_workflow.analyze_uploaded_resume",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="invalid result"):
            run_resume_workflow(str(resume))


def test_resume_workflow_missing_file_raises(tmp_path):
    resume = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError, match="Resume file not found"):
        run_resume_workflow(str(resume))
