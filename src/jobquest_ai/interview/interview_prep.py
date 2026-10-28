
"""Create personalized interview preparation plans."""

import os
from datetime import date
from typing import Literal
import re
from difflib import SequenceMatcher

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from jobquest_ai.preparation.skill_gap_analyzer import (
    SkillGapAnalysis,
    SkillGapAnalysisError,
    analyze_skill_gaps,
)
from jobquest_ai.preparation.study_plan import (
    StudyPlan,
    StudyPlanError,
    generate_study_plan,
)

load_dotenv()


class InterviewPrepError(Exception):
    """Raised when interview preparation planning fails."""


Priority = Literal["high", "medium", "low"]


class PreparationTask(BaseModel):
    """A personalized interview preparation activity."""

    topic: str
    priority: Priority
    estimated_hours: float = Field(gt=0, le=8)
    activity: str
    reason: str
    success_criteria: str


class PreparationTaskSet(BaseModel):
    """Preparation tasks generated for the target role."""

    tasks: list[PreparationTask] = Field(min_length=1, max_length=12)
    recommendations: list[str] = Field(default_factory=list, max_length=5)


class InterviewPrepPlan(BaseModel):
    target_role: str
    skill_gap_analysis: SkillGapAnalysis
    study_plan: StudyPlan
    practice_activities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

def _normalize_task_text(text: str) -> str:
    """Normalize task descriptions for duplicate comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _has_duplicate_objectives(
    tasks: list[PreparationTask],
) -> bool:
    """Check whether tasks contain substantially repeated objectives."""
    for index, task in enumerate(tasks):
        current_topic = _normalize_task_text(task.topic)
        current_activity = _normalize_task_text(task.activity)

        for previous in tasks[:index]:
            previous_topic = _normalize_task_text(previous.topic)
            previous_activity = _normalize_task_text(previous.activity)

            # Compare activities only when their topics match.
            if current_topic != previous_topic:
                continue

            similarity = SequenceMatcher(
                None,
                current_activity,
                previous_activity,
            ).ratio()

            if similarity >= 0.88:
                return True

    return False




def generate_preparation_tasks(
    target_role: str,
    job_description: str,
    analysis: SkillGapAnalysis,
) -> PreparationTaskSet:
    """Generate role-specific preparation tasks using Groq."""

    if not os.getenv("GROQ_API_KEY"):
        raise InterviewPrepError("GROQ_API_KEY is not configured.")

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
            PreparationTaskSet
        )

        prompt = f"""
You are an experienced technical interview preparation mentor.

Create a focused, realistic preparation task list for the candidate.

TARGET ROLE:
{target_role}

JOB DESCRIPTION:
{job_description}

SKILL GAP ANALYSIS:
{analysis.model_dump_json(indent=2)}

RULES FOR GENERATING TASKS:

1. JOB RELEVANCE
- Prioritize skills explicitly required or strongly implied by the job description.
- Use the skill gap analysis to identify candidate weaknesses and existing strengths.
- Do not invent job requirements or prioritize unrelated technologies.

2. DISTINCT TASKS
- Generate 4 to 8 tasks, depending on the number of important skill gaps.
- Each task must have a distinct learning objective and concrete deliverable.
- Multiple tasks may share a topic only when they teach genuinely different
  subskills that are important for this role.
- Avoid repeating the same project or exercise with slightly different wording.
- Cover the highest-priority gaps before adding lower-priority topics.

3. TECHNOLOGY CONSTRAINTS
- Use technologies explicitly mentioned in the job description when possible.
- Do not introduce Docker, Kubernetes, JWT refresh tokens, CI/CD, or other
  advanced tooling unless the job description or a clear role requirement
  justifies it.
- Prefer simple, accessible exercises over unnecessary infrastructure.
- Do not require deployment or a public GitHub repository for every task.

4. REALISTIC PREPARATION
- Each task must have a specific, achievable deliverable.
- Estimated hours must be greater than 0 and no more than 8.
- Assign more time to high-priority gaps and less time to smaller exercises.
- Do not assume the candidate has unlimited preparation time.
- Focus on interview readiness, not building an entire production system.

5. TASK QUALITY
- Write actionable activities with clear implementation or practice steps.
- Explain why each task matters for this particular role.
- Define measurable success criteria that the candidate can verify.
- Keep tasks focused enough to complete within their estimated hours.
- Include a maximum of 5 concise recommendations.

Return only output matching the required structured schema.
"""

        
        
        result = structured_llm.invoke(prompt)

        if _has_duplicate_objectives(result.tasks):
            retry_prompt = f"""
        {prompt}

        IMPORTANT: Your previous response contained duplicate task objectives.

        Generate a corrected preparation task list.

        Requirements:
        - Return 4 to 8 tasks.
        - Remove substantially repeated activities.
        - Tasks may share a topic only when their learning objectives differ.
        - Preserve coverage of the most important skill gaps.
        - Keep every task relevant to the job description.
        - Preserve the required structured output schema.
        """

            result = structured_llm.invoke(retry_prompt)

            if _has_duplicate_objectives(result.tasks):
                raise InterviewPrepError(
                    "Groq generated duplicate task objectives even after "
                    "one retry. Please try generating the plan again."
                )

        return result


    except InterviewPrepError:
        raise

    except Exception as exc:
        raise InterviewPrepError(
            f"Unable to generate preparation tasks: {exc}"
        ) from exc



def generate_interview_prep(
    target_role: str,
    job_description: str,
    resume_text: str,
    interview_date: date,
    daily_available_hours: float = 2.0,
    start_date: date | None = None,
) -> InterviewPrepPlan:
    """
    Analyze candidate skills and generate a personalized
    interview preparation plan.
    """

    if not isinstance(target_role, str) or not target_role.strip():
        raise InterviewPrepError(
            "target_role must be a non-empty string."
        )

    if (
        not isinstance(job_description, str)
        or not job_description.strip()
    ):
        raise InterviewPrepError(
            "job_description must be a non-empty string."
        )

    if not isinstance(resume_text, str) or not resume_text.strip():
        raise InterviewPrepError(
            "resume_text must be a non-empty string."
        )

    try:
        # Step 1: Analyze role requirements and candidate skills.
        analysis = analyze_skill_gaps(
            target_role=target_role,
            job_description=job_description,
            resume_text=resume_text,
        )

        # Step 2: Generate personalized preparation tasks with Groq.
        preparation_tasks = generate_preparation_tasks(
            target_role=target_role,
            job_description=job_description,
            analysis=analysis,
        )

        # Step 3: Schedule the generated tasks.
        # This requires study_plan.py to accept preparation_tasks.
        study_plan = generate_study_plan(
            analysis=analysis,
            interview_date=interview_date,
            daily_available_hours=daily_available_hours,
            start_date=start_date,
            preparation_tasks=preparation_tasks.tasks,
        )

        # Step 4: Collect activities from the scheduled plan.
        practice_activities = list(
            dict.fromkeys(
                task.activity
                for day in study_plan.days
                for task in day.tasks
            )
        )

        return InterviewPrepPlan(
            target_role=analysis.target_role,
            skill_gap_analysis=analysis,
            study_plan=study_plan,
            practice_activities=practice_activities,
            recommendations=preparation_tasks.recommendations,
        )

    except (SkillGapAnalysisError, StudyPlanError) as exc:
        raise InterviewPrepError(
            f"Unable to generate the interview preparation plan: {exc}"
        ) from exc
