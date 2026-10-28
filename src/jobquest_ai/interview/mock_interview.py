
"""Run interactive mock interviews and evaluate answers after each question."""

import os
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from jobquest_ai.interview.question_generator import (
    InterviewQuestion,
    InterviewQuestionSet,
)

load_dotenv()


class MockInterviewError(Exception):
    """Raised when a mock interview operation fails."""


class CriterionScore(BaseModel):
    """Score awarded for one evaluation criterion."""

    criterion: str = Field(min_length=1)
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    feedback: str = Field(min_length=1)


class AnswerEvaluation(BaseModel):
    """Evaluation and feedback for a candidate's answer."""

    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    percentage: float = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    feedback: str = Field(min_length=1)
    criterion_scores: list[CriterionScore] = Field(min_length=1)


class InterviewResponse(BaseModel):
    """A candidate's answer and its evaluation."""

    question_id: str
    question: str
    answer: str
    evaluation: AnswerEvaluation
    answered_at: datetime


class InterviewQuestionView(BaseModel):
    """Question information safe to display to a candidate."""

    question_id: str
    question_number: int
    total_questions: int
    category: str
    difficulty: str
    question: str
    purpose: str


class MockInterviewSession(BaseModel):
    """State of a single mock interview session."""

    session_id: str
    target_role: str
    status: Literal["in_progress", "completed"] = "in_progress"
    questions: list[InterviewQuestion]
    current_question_index: int = 0
    responses: list[InterviewResponse] = Field(default_factory=list)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None


class InterviewTurnResult(BaseModel):
    """Result returned after an answer is evaluated."""

    evaluation: AnswerEvaluation
    next_question: InterviewQuestionView | None = None
    interview_completed: bool
    answered_questions: int
    total_questions: int


class InterviewReport(BaseModel):
    """Final summary of interview performance."""

    session_id: str
    target_role: str
    total_questions: int
    answered_questions: int
    total_score: float
    maximum_score: float
    overall_percentage: float
    strengths: list[str]
    improvement_areas: list[str]
    question_results: list[InterviewResponse]
    recommendations: list[str]
    started_at: datetime
    completed_at: datetime


def _get_current_question(
    session: MockInterviewSession,
) -> InterviewQuestionView:
    """Return the current question without exposing its model answer."""

    if session.status != "in_progress":
        raise MockInterviewError("The interview is already completed.")

    if session.current_question_index >= len(session.questions):
        raise MockInterviewError("No questions remain in this interview.")

    question = session.questions[session.current_question_index]

    return InterviewQuestionView(
        question_id=question.question_id,
        question_number=session.current_question_index + 1,
        total_questions=len(session.questions),
        category=question.category,
        difficulty=question.difficulty,
        question=question.question,
        purpose=question.purpose,
    )


def start_interview(
    question_set: InterviewQuestionSet,
) -> tuple[MockInterviewSession, InterviewQuestionView]:
    """Create a session and return the first question."""

    if not question_set.questions:
        raise MockInterviewError(
            "Cannot start an interview without questions."
        )

    session = MockInterviewSession(
        session_id=str(uuid4()),
        target_role=question_set.target_role,
        questions=question_set.questions,
    )

    first_question = _get_current_question(session)

    return session, first_question


def evaluate_answer(
    question: InterviewQuestion,
    answer: str,
) -> AnswerEvaluation:
    """Evaluate one answer using Groq and the question's scoring rubric."""

    if not isinstance(answer, str) or not answer.strip():
        raise MockInterviewError("The answer must not be empty.")

    if not os.getenv("GROQ_API_KEY"):
        raise MockInterviewError("GROQ_API_KEY is not configured.")

    model_name = os.getenv(
        "GROQ_MODEL",
        "llama-3.3-70b-versatile",
    )

    try:
        llm = ChatGroq(
            model=model_name,
            temperature=0.1,
        )

        evaluator = llm.with_structured_output(AnswerEvaluation)

        rubric = [
            criterion.model_dump()
            for criterion in question.evaluation_rubric
        ]

        prompt = f"""
You are a fair, evidence-based interview evaluator.

Evaluate the candidate's answer to the question below.

QUESTION:
{question.question}

QUESTION CATEGORY:
{question.category}

QUESTION DIFFICULTY:
{question.difficulty}

QUESTION PURPOSE:
{question.purpose}

REFERENCE ANSWER:
{question.model_answer}

EVALUATION RUBRIC:
{rubric}

CANDIDATE ANSWER:
{answer}

EVALUATION RULES:

1. Evaluate only what the candidate actually said.
2. The reference answer is guidance, not the only acceptable answer.
3. Give credit for technically correct alternative approaches.
4. Score every rubric criterion separately.
5. Each criterion's score must be between zero and its max_score.
6. The total score must equal the sum of criterion scores.
7. The maximum score must equal the sum of rubric max_score values.
8. The percentage must equal total score / maximum score * 100.
9. Identify strengths, specific improvements, and important missing concepts.
10. Feedback must be constructive, clear, and specific.
11. Do not award credit for concepts that the candidate did not explain.
12. Do not penalize reasonable alternative terminology or approaches.

Return a structured evaluation matching the required schema.
"""

        result = evaluator.invoke(prompt)

        expected_max_score = sum(
            criterion.max_score
            for criterion in question.evaluation_rubric
        )

        expected_score = sum(
            criterion_score.score
            for criterion_score in result.criterion_scores
        )

        returned_criteria = [
            item.criterion.strip().casefold()
            for item in result.criterion_scores
        ]
        expected_criteria = [
            item.criterion.strip().casefold()
            for item in question.evaluation_rubric
        ]

        if sorted(returned_criteria) != sorted(expected_criteria):
            raise MockInterviewError(
                "The evaluator returned criteria that do not match "
                "the question's rubric."
            )

        for score, rubric_item in zip(
            result.criterion_scores,
            question.evaluation_rubric,
        ):
            if score.score > rubric_item.max_score:
                raise MockInterviewError(
                    "The evaluator awarded more points than a criterion "
                    "allows."
                )

        if abs(result.max_score - expected_max_score) > 0.01:
            raise MockInterviewError(
                "The evaluator returned an incorrect maximum score."
            )

        if abs(result.score - expected_score) > 0.01:
            raise MockInterviewError(
                "The total score does not match the criterion scores."
            )

        expected_percentage = (
            expected_score / expected_max_score * 100
        )

        if abs(result.percentage - expected_percentage) > 0.1:
            raise MockInterviewError(
                "The evaluator returned an incorrect percentage."
            )

        return result

    except MockInterviewError:
        raise

    except Exception as exc:
        raise MockInterviewError(
            f"Unable to evaluate the answer: {exc}"
        ) from exc


def submit_answer(
    session: MockInterviewSession,
    answer: str,
) -> InterviewTurnResult:
    """Evaluate an answer, save it, and advance the interview."""

    if session.status != "in_progress":
        raise MockInterviewError(
            "Cannot submit an answer to a completed interview."
        )

    if not isinstance(answer, str) or not answer.strip():
        raise MockInterviewError("The answer must not be empty.")

    if session.current_question_index >= len(session.questions):
        raise MockInterviewError("No questions remain in this interview.")

    question = session.questions[session.current_question_index]

    # Evaluate before changing session state. If evaluation fails,
    # the candidate can retry without losing the current question.
    evaluation = evaluate_answer(question, answer)

    response = InterviewResponse(
        question_id=question.question_id,
        question=question.question,
        answer=answer.strip(),
        evaluation=evaluation,
        answered_at=datetime.now(timezone.utc),
    )

    session.responses.append(response)
    session.current_question_index += 1

    completed = (
        session.current_question_index >= len(session.questions)
    )

    next_question = None

    if completed:
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
    else:
        next_question = _get_current_question(session)

    return InterviewTurnResult(
        evaluation=evaluation,
        next_question=next_question,
        interview_completed=completed,
        answered_questions=len(session.responses),
        total_questions=len(session.questions),
    )


def generate_interview_report(
    session: MockInterviewSession,
) -> InterviewReport:
    """Generate a report from the answers evaluated so far."""

    if session.status != "completed":
        raise MockInterviewError(
            "Complete the interview before generating the final report."
        )

    if not session.responses:
        raise MockInterviewError(
            "The interview has no evaluated answers."
        )

    total_score = sum(
        response.evaluation.score
        for response in session.responses
    )

    maximum_score = sum(
        response.evaluation.max_score
        for response in session.responses
    )

    percentage = (
        total_score / maximum_score * 100
        if maximum_score
        else 0.0
    )

    strengths = list(
        dict.fromkeys(
            strength
            for response in session.responses
            for strength in response.evaluation.strengths
        )
    )

    improvement_areas = list(
        dict.fromkeys(
            improvement
            for response in session.responses
            for improvement in response.evaluation.improvements
        )
    )

    recommendations = [
        f"Review: {area}"
        for area in improvement_areas
    ]

    if percentage < 50:
        recommendations.append(
            "Revisit the fundamentals for the target role and practise "
            "explaining concepts aloud."
        )
    elif percentage < 75:
        recommendations.append(
            "Practise applying concepts to realistic problems and "
            "strengthen explanations with concrete examples."
        )
    else:
        recommendations.append(
            "Continue practising advanced scenarios and concise, "
            "well-structured explanations."
        )

    return InterviewReport(
        session_id=session.session_id,
        target_role=session.target_role,
        total_questions=len(session.questions),
        answered_questions=len(session.responses),
        total_score=round(total_score, 2),
        maximum_score=round(maximum_score, 2),
        overall_percentage=round(percentage, 2),
        strengths=strengths,
        improvement_areas=improvement_areas,
        question_results=session.responses,
        recommendations=recommendations,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )
