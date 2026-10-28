import os
from unittest.mock import Mock, patch

from jobquest_ai.resume.resume_analyzer import (
    ResumeAnalysis,
    _build_analyzer,
)


@patch.dict(
    os.environ,
    {"GROQ_API_KEY": "test-key", "GROQ_MODEL": "test-model"},
)
def test_build_analyzer_uses_json_mode():
    chat_model = Mock()
    structured_output = Mock()
    chat_model.with_structured_output.return_value = structured_output

    with patch(
        "jobquest_ai.resume.resume_analyzer.ChatGroq",
        return_value=chat_model,
    ) as chat_groq:
        analyzer = _build_analyzer()

    chat_groq.assert_called_once_with(
        model="test-model",
        temperature=0,
        api_key="test-key",
    )
    chat_model.with_structured_output.assert_called_once_with(
        ResumeAnalysis,
        method="json_mode",
    )
    assert analyzer is structured_output