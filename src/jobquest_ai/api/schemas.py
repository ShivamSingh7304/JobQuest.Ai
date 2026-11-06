from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from jobquest_ai.resume.resume_tailor import TailoredResume


# ---------------------------------------------------------------------------
# AI chat (existing)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str


ReviewDecision = Literal["approve", "request_changes"]


class HumanFeedbackCreate(BaseModel):
    decision: ReviewDecision
    feedback: str | None = Field(default=None, max_length=32_000)
    conversation_id: int | None = Field(default=None, gt=0)
    message_id: int | None = Field(default=None, gt=0)
    workflow_name: str | None = Field(default=None, min_length=1, max_length=100)
    workflow_output_id: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    workflow_output_record_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target(self):
        conversation_target = (
            self.conversation_id is not None or self.message_id is not None
        )
        workflow_target = (
            self.workflow_name is not None
            or self.workflow_output_id is not None
            or self.workflow_output_record_id is not None
        )
        if conversation_target == workflow_target:
            raise ValueError(
                "Provide either a conversation/message target or a workflow output target."
            )
        if workflow_target and self.workflow_output_record_id is None and not (
            self.workflow_name and self.workflow_output_id
        ):
            raise ValueError(
                "workflow_name and workflow_output_id are required together unless workflow_output_record_id is provided."
            )
        return self


class HumanFeedbackUpdate(BaseModel):
    decision: ReviewDecision
    feedback: str | None = Field(default=None, max_length=32_000)


class HumanFeedbackResponse(BaseModel):
    id: int
    user_id: int
    decision: ReviewDecision
    feedback: str | None
    conversation_id: int | None
    message_id: int | None
    workflow_name: str | None
    workflow_output_id: str | None
    workflow_output_record_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalCheckResponse(BaseModel):
    approved: bool
    state: Literal["approved", "pending", "changes_requested"]
    message: str
    decision: ReviewDecision | None = None
    feedback: str | None = None


class WorkflowOutputCreate(BaseModel):
    workflow_name: str = Field(..., min_length=1, max_length=100)
    output_type: str = Field(..., min_length=1, max_length=50)
    output_key: str | None = Field(default=None, max_length=255)
    payload: dict[str, Any]
    status: Literal[
        "pending_review", "changes_requested", "approved", "superseded"
    ] = "pending_review"
    parent_output_id: int | None = Field(default=None, gt=0)


class WorkflowOutputRevisionCreate(BaseModel):
    payload: dict[str, Any]
    status: Literal[
        "pending_review", "changes_requested", "approved", "superseded"
    ] = "pending_review"


class WorkflowOutputResponse(BaseModel):
    id: int
    user_id: int
    workflow_name: str
    output_type: str
    output_key: str | None
    payload: dict[str, Any]
    status: str
    version: int
    parent_output_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResumeTailorRequest(BaseModel):
    job_description: str = Field(
        ...,
        min_length=1,
        max_length=15_000,
        description="The target job description.",
    )


class ResumeWorkflowResponse(BaseModel):
    """Persisted, reviewable result from resume analysis and tailoring."""

    workflow: str
    workflow_output_id: int
    status: str
    target_role: str
    resume_id: int | None = None
    analysis: dict[str, Any]
    tailoring: TailoredResume
    original_content_unchanged: bool
    human_review: dict[str, Any]
    next_steps: list[str]


class SaveTailoredResumeRequest(BaseModel):
    workflow_output_record_id: int = Field(..., gt=0)


class ResumeResponse(BaseModel):
    id: int
    user_id: int
    original_filename: str
    extracted_text: str | None
    parsed_data: dict[str, Any] | None
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TailoredResumeResponse(ResumeResponse):
    download_url: str


class JobMatchRequest(BaseModel):
    resume_id: int = Field(..., gt=0, description="The resume to match against.")
    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Role, keyword, or job search query.",
    )
    country: str = Field(
        default="India",
        min_length=1,
        max_length=100,
        description="Country used by the job search provider.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of ranked jobs to return.",
    )
    max_pages: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum number of provider pages to search.",
    )


class JobMatchResponse(BaseModel):
    query: str
    country: str
    total_count: int | None
    pages_fetched: int
    fetched_job_count: int
    rejected_job_count: int
    matched_job_count: int
    match_score_type: str
    jobs: list[dict]


class SaveJobRequest(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    company_name: str = Field(..., min_length=1, max_length=255)
    application_url: HttpUrl
    description: str | None = Field(default=None, max_length=100_000)
    excerpt: str | None = Field(default=None, max_length=10_000)
    location_restrictions: list[str] = Field(default_factory=list, max_length=50)
    employment_type: str | None = Field(default=None, max_length=100)
    seniority: str | None = Field(default=None, max_length=100)
    published_at: str | None = Field(default=None, max_length=100)

    @field_validator("seniority", mode="before")
    @classmethod
    def normalize_seniority(cls, value):
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return value

    @field_validator("published_at", mode="before")
    @classmethod
    def normalize_published_at(cls, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return value


class SavedJobResponse(BaseModel):
    job_id: int
    external_job_id: str
    source: str
    title: str
    company: str
    description: str | None
    location: str | None
    employment_type: str | None
    apply_url: str | None
    posted_at: datetime | None

    model_config = {"from_attributes": True}


ApplicationStatus = Literal[
    "saved",
    "pending_approval",
    "approved",
    "submitted",
    "interviewing",
    "rejected",
    "offer",
    "withdrawn",
]


class ApplicationCreate(BaseModel):
    job_id: int = Field(..., gt=0)
    resume_id: int | None = Field(default=None, gt=0)
    status: ApplicationStatus = "saved"
    notes: str | None = Field(default=None, max_length=32_000)
    workflow_output_record_id: int | None = Field(default=None, gt=0)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=32_000)
    workflow_output_record_id: int | None = Field(default=None, gt=0)


class ApplicationResponse(BaseModel):
    id: int
    user_id: int
    job_id: int
    resume_id: int | None
    workflow_output_record_id: int | None = Field(
        default=None,
        validation_alias="workflow_output_id",
        serialization_alias="workflow_output_record_id",
    )
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    company: str | None = None
    role: str | None = None

    model_config = {"from_attributes": True}


class ApplicationPreparationResponse(BaseModel):
    application_id: int
    workflow: str
    company: str
    role: str
    job_id: int | None
    resume_id: int | None
    job_description: str | None
    workflow_output_id: int
    status: str
    readiness_checklist: str
    approval: dict[str, Any]
    next_steps: list[str]
    submission_allowed: bool


class OverviewApplication(BaseModel):
    id: int
    role: str
    company: str
    stage: str
    status: str
    updated_at: datetime


class OverviewResponse(BaseModel):
    active_applications: int
    interviewing_applications: int
    saved_opportunities: int
    resume_count: int
    recent_applications: list[OverviewApplication]


class CalendarConnectionResponse(BaseModel):
    connected: bool
    authorization_url: str | None = None


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start: str
    end: str
    date_label: str
    time_label: str
    location: str | None = None
    description: str | None = None
    link: str | None = None
    conference_url: str | None = None
    all_day: bool = False


class CalendarEventsResponse(BaseModel):
    connected: bool
    time_zone: str
    calendar_name: str | None = None
    events: list[CalendarEventResponse]


InterviewCategory = Literal["technical", "behavioral", "hr", "resume"]
InterviewDifficulty = Literal["easy", "medium", "hard"]


class InterviewGenerateRequest(BaseModel):
    resume_id: int = Field(..., gt=0)
    target_role: str = Field(..., min_length=1, max_length=255)
    job_description: str = Field(..., min_length=1, max_length=15_000)
    question_count: int = Field(default=5, ge=1, le=30)
    categories: list[InterviewCategory] | None = None
    difficulty: InterviewDifficulty = "medium"


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=20_000)


class InterviewStartResponse(BaseModel):
    session_id: str
    workflow_output_id: int
    target_role: str
    status: str
    question: dict[str, Any]


class InterviewTurnResponse(BaseModel):
    session_id: str
    evaluation: dict[str, Any]
    next_question: dict[str, Any] | None
    interview_completed: bool
    answered_questions: int
    total_questions: int


class InterviewReportResponse(BaseModel):
    report: dict[str, Any]


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class ConversationCreate(BaseModel):
    title: str | None = Field(
        default=None, max_length=255, description="Optional conversation title."
    )


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageCreate(BaseModel):
    role: Literal["user", "assistant"] = Field(
        ..., description="Who sent the message."
    )
    content: str = Field(..., min_length=1, max_length=32_000)


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationWithMessagesResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}
