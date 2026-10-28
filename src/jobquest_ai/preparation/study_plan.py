
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from jobquest_ai.preparation.skill_gap_analyzer import SkillGapAnalysis


Priority = Literal["high", "medium", "low"]


class StudyTask(BaseModel):
    """A single preparation task."""

    topic: str
    priority: Priority
    estimated_hours: float = Field(gt=0)
    activity: str
    reason: str


class DailyStudyPlan(BaseModel):
    """Study tasks scheduled for one day."""

    study_date: date
    tasks: list[StudyTask] = Field(default_factory=list)
    total_hours: float = Field(ge=0)


class StudyPlan(BaseModel):
    """Complete interview preparation schedule."""

    target_role: str
    start_date: date
    interview_date: date
    daily_available_hours: float
    total_available_hours: float
    scheduled_hours: float
    unscheduled_topics: list[str] = Field(default_factory=list)
    days: list[DailyStudyPlan] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class StudyPlanError(Exception):
    """Raised when a study plan cannot be generated."""


def _normalize_priority(value: str) -> Priority:
    """Convert different priority labels into a standard priority."""

    value = value.strip().lower()

    if value in {"high", "critical", "urgent"}:
        return "high"

    if value in {"medium", "moderate", "normal"}:
        return "medium"

    return "low"


def _estimate_hours(priority: Priority, category: str) -> float:
    """Estimate preparation time using priority and topic category."""

    category = category.lower()

    base_hours = {
        "high": 3.0,
        "medium": 2.0,
        "low": 1.0,
    }[priority]

    if any(
        keyword in category
        for keyword in ("programming", "coding", "technical", "algorithm")
    ):
        base_hours += 1.0

    return base_hours


def _activity_for_category(category: str) -> str:
    """Choose a practical learning activity for a topic."""

    category = category.lower()

    if any(
        keyword in category
        for keyword in ("programming", "coding", "technical", "algorithm")
    ):
        return "Study the concept, solve coding problems, and explain your solution."

    if any(keyword in category for keyword in ("behavioral", "hr", "communication")):
        return "Prepare examples from your experience and practise answering aloud."

    if any(keyword in category for keyword in ("project", "resume")):
        return "Review your project architecture, decisions, trade-offs, and challenges."

    return "Review the fundamentals, practise questions, and test your understanding."


def generate_study_plan(
    analysis: SkillGapAnalysis,
    interview_date: date,
    daily_available_hours: float = 2.0,
    start_date: date | None = None,
) -> StudyPlan:
    """
    Generate a deterministic daily preparation plan.

    Higher-priority gaps are scheduled first. Tasks can be split across
    multiple days, and daily study hours are never exceeded.
    """

    if not isinstance(analysis, SkillGapAnalysis):
        raise StudyPlanError(
            "analysis must be a valid SkillGapAnalysis object."
        )

    if not isinstance(interview_date, date):
        raise StudyPlanError("interview_date must be a date object.")

    if start_date is None:
        start_date = date.today()

    if not isinstance(start_date, date):
        raise StudyPlanError("start_date must be a date object.")

    if interview_date < start_date:
        raise StudyPlanError(
            "interview_date must be on or after start_date."
        )

    if (
        isinstance(daily_available_hours, bool)
        or not isinstance(daily_available_hours, (int, float))
        or daily_available_hours <= 0
        or daily_available_hours > 24
    ):
        raise StudyPlanError(
            "daily_available_hours must be greater than 0 and at most 24."
        )

    # Include the start date and interview date in the schedule.
    number_of_days = (interview_date - start_date).days + 1
    total_available_hours = number_of_days * float(daily_available_hours)

    # Prefer identified gaps. If no gaps were found, prepare all required skills.
    topics = []

    if analysis.potential_gaps:
        for gap in analysis.potential_gaps:
            priority = _normalize_priority(gap.priority)
            skill_name = gap.skill.strip()

            if not skill_name:
                continue

            matching_skill = next(
                (
                    skill
                    for skill in analysis.required_skills
                    if skill.name.strip().lower() == skill_name.lower()
                ),
                None,
            )

            category = matching_skill.category if matching_skill else "general"

            topics.append(
                {
                    "name": skill_name,
                    "priority": priority,
                    "hours": _estimate_hours(priority, category),
                    "activity": _activity_for_category(category),
                    "reason": gap.reason.strip()
                    or "Identified as a potential preparation gap.",
                }
            )
    else:
        for skill in analysis.required_skills:
            skill_name = skill.name.strip()

            if not skill_name:
                continue

            priority = _normalize_priority(skill.importance)

            topics.append(
                {
                    "name": skill_name,
                    "priority": priority,
                    "hours": _estimate_hours(priority, skill.category),
                    "activity": _activity_for_category(skill.category),
                    "reason": "Review this job requirement before the interview.",
                }
            )

    # Avoid scheduling the same topic more than once.
    unique_topics = {}
    for topic in topics:
        key = topic["name"].lower()
        if key not in unique_topics:
            unique_topics[key] = topic

    topics = list(unique_topics.values())

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    topics.sort(
        key=lambda topic: (
            priority_rank[topic["priority"]],
            -topic["hours"],
            topic["name"].lower(),
        )
    )

    daily_plans = [
        DailyStudyPlan(
            study_date=start_date + timedelta(days=day_index),
            total_hours=0.0,
        )
        for day_index in range(number_of_days)
    ]

    unscheduled_topics = []
    next_day_index = 0

    for topic in topics:
        remaining_hours = topic["hours"]
        first_day_for_topic = True

        while remaining_hours > 0:
            while (
                next_day_index < number_of_days
                and daily_plans[next_day_index].total_hours
                >= daily_available_hours
            ):
                next_day_index += 1

            if next_day_index >= number_of_days:
                unscheduled_topics.append(topic["name"])
                break

            day_plan = daily_plans[next_day_index]
            available_today = (
                float(daily_available_hours) - day_plan.total_hours
            )
            hours_today = min(remaining_hours, available_today)

            day_plan.tasks.append(
                StudyTask(
                    topic=topic["name"],
                    priority=topic["priority"],
                    estimated_hours=round(hours_today, 2),
                    activity=topic["activity"],
                    reason=(
                        topic["reason"]
                        if first_day_for_topic
                        else "Continue practising and reviewing this topic."
                    ),
                )
            )

            day_plan.total_hours = round(
                day_plan.total_hours + hours_today, 2
            )
            remaining_hours = round(remaining_hours - hours_today, 2)
            first_day_for_topic = False

    scheduled_hours = round(
        sum(day.total_hours for day in daily_plans), 2
    )

    recommendations = [
        "Practise explaining concepts aloud instead of only reading notes.",
        "Use coding exercises and mock questions to check understanding.",
    ]

    if unscheduled_topics:
        recommendations.append(
            "Available time is insufficient for every topic. "
            "Focus on high-priority topics first and review unscheduled topics "
            "if extra time becomes available."
        )

    if number_of_days > 1:
        recommendations.append(
            "Reserve some time near the interview for revision and a mock interview."
        )

    return StudyPlan(
        target_role=analysis.target_role,
        start_date=start_date,
        interview_date=interview_date,
        daily_available_hours=float(daily_available_hours),
        total_available_hours=round(total_available_hours, 2),
        scheduled_hours=scheduled_hours,
        unscheduled_topics=unscheduled_topics,
        days=daily_plans,
        recommendations=recommendations,
    )
