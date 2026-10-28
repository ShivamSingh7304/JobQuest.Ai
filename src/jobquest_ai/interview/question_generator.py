
"""Generate structured interview questions using Groq."""

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

load_dotenv()


QuestionCategory = Literal[
    "technical",
    "behavioral",
    "hr",
    "resume",
]

QuestionDifficulty = Literal[
    "easy",
    "medium",
    "hard",
]


class QuestionGenerationError(Exception):
    """Raised when interview question generation fails."""


class EvaluationCriterion(BaseModel):
    """One criterion used to evaluate a candidate's answer."""

    criterion: str = Field(
        min_length=1,
        description="A specific aspect of the answer to evaluate.",
    )
    expected_elements: list[str] = Field(
        min_length=1,
        description="Important concepts or evidence expected in the answer.",
    )
    max_score: int = Field(
        gt=0,
        le=10,
        description="Maximum points awarded for this criterion.",
    )


class InterviewQuestion(BaseModel):
    """An interview question with a reference answer and scoring rubric."""

    question_id: str = Field(
        min_length=1,
        description="Unique identifier within the generated question set.",
    )
    category: QuestionCategory
    difficulty: QuestionDifficulty
    question: str = Field(min_length=1)
    purpose: str = Field(
        min_length=1,
        description="What this question is intended to assess.",
    )
    model_answer: str = Field(
        min_length=1,
        description="A reference answer, not the only acceptable answer.",
    )
    evaluation_rubric: list[EvaluationCriterion] = Field(
        min_length=1,
        description="Criteria used to assess a candidate's response.",
    )
    follow_up_questions: list[str] = Field(default_factory=list)


class InterviewQuestionSet(BaseModel):
    """A validated collection of generated interview questions."""

    target_role: str = Field(min_length=1)
    questions: list[InterviewQuestion] = Field(
        min_length=1,
        max_length=30,
    )


def generate_interview_questions(
    target_role: str,
    job_description: str,
    resume_text: str,
    question_count: int = 10,
    categories: list[QuestionCategory] | None = None,
    difficulty: QuestionDifficulty = "medium",
) -> InterviewQuestionSet:
    """
    Generate interview questions tailored to a role and candidate.

    Questions include reference answers and evaluation rubrics.
    """

    if not isinstance(target_role, str) or not target_role.strip():
        raise QuestionGenerationError(
            "target_role must be a non-empty string."
        )

    if (
        not isinstance(job_description, str)
        or not job_description.strip()
    ):
        raise QuestionGenerationError(
            "job_description must be a non-empty string."
        )

    if not isinstance(resume_text, str) or not resume_text.strip():
        raise QuestionGenerationError(
            "resume_text must be a non-empty string."
        )

    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or not 1 <= question_count <= 30
    ):
        raise QuestionGenerationError(
            "question_count must be an integer between 1 and 30."
        )

    selected_categories = (
        categories
        if categories is not None
        else ["technical", "behavioral", "hr", "resume"]
    )

    valid_categories = {
        "technical",
        "behavioral",
        "hr",
        "resume",
    }

    if (
        not isinstance(selected_categories, list)
        or not selected_categories
        or any(
            category not in valid_categories
            for category in selected_categories
        )
    ):
        raise QuestionGenerationError(
            "categories must contain valid interview categories."
        )

    if difficulty not in {"easy", "medium", "hard"}:
        raise QuestionGenerationError(
            "difficulty must be easy, medium, or hard."
        )

    if not os.getenv("GROQ_API_KEY"):
        raise QuestionGenerationError(
            "GROQ_API_KEY is not configured."
        )

    model_name = os.getenv(
        "GROQ_MODEL",
        "llama-3.3-70b-versatile",
    )

    try:
        llm = ChatGroq(
            model=model_name,
            temperature=0.2,
        )

        structured_llm = llm.with_structured_output(
            InterviewQuestionSet
        )

        prompt = f"""
You are an experienced technical interviewer and interview coach.

Generate exactly {question_count} distinct interview questions.

TARGET ROLE:
{target_role}

JOB DESCRIPTION:
{job_description}

CANDIDATE RESUME:
{resume_text}

QUESTION CATEGORIES:
{selected_categories}

DIFFICULTY:
{difficulty}

REQUIREMENTS:

1. ROLE RELEVANCE
- Base technical questions on skills required by the job description.
- Use the resume to identify projects, experience, and claims worth exploring.
- Do not invent candidate experience or job requirements.

2. CATEGORY COVERAGE
- Generate questions only from the requested categories.
- Technical questions should assess relevant technical knowledge and problem-solving.
- Behavioral questions should explore actions, decisions, and outcomes.
- HR questions should address motivation, communication, and role fit.
- Resume questions should investigate actual projects, responsibilities,
  technologies, and claims in the supplied resume.
- If a category is not relevant to the supplied information, avoid
  inventing facts to create a question.

3. QUALITY
- Questions must be clear, distinct, and suitable for the requested difficulty.
- Avoid repeated questions phrased differently.
- Include a mixture of conceptual understanding and practical application
  when appropriate for the role.
- Do not make every technical question depend on a specific framework
  unless the job description requires it.

4. MODEL ANSWERS
- Provide a correct, useful reference answer for each question.
- Explain the reasoning where appropriate.
- For behavioral questions, provide an answer structure or illustrative
  example, not fabricated claims about the candidate.
- A model answer is a reference, not the only acceptable response.

5. EVALUATION RUBRICS
- Provide criteria that can be used to score the candidate's answer.
- Each criterion must have expected elements and a positive maximum score.
- Use concrete, observable criteria rather than vague descriptions.
- Keep the rubric relevant to the question.

6. FOLLOW-UP QUESTIONS
- Include relevant follow-up questions when useful.
- Do not repeat the original question.

Use unique question IDs within this question set.
Return only output matching the required structured schema.
"""

        result = structured_llm.invoke(prompt)

        if len(result.questions) != question_count:
            raise QuestionGenerationError(
                "The model returned an unexpected number of questions: "
                f"expected {question_count}, received "
                f"{len(result.questions)}."
            )

        if len(
            {
                question.question_id
                for question in result.questions
            }
        ) != len(result.questions):
            raise QuestionGenerationError(
                "The model returned duplicate question IDs."
            )

        if any(
            question.category not in selected_categories
            for question in result.questions
        ):
            raise QuestionGenerationError(
                "The model returned a question outside the requested "
                "categories."
            )

        return result

    except QuestionGenerationError:
        raise

    except Exception as exc:
        raise QuestionGenerationError(
            f"Unable to generate interview questions: {exc}"
        ) from exc
