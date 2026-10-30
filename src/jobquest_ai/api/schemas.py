from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


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

    @model_validator(mode="after")
    def validate_target(self):
        conversation_target = (
            self.conversation_id is not None or self.message_id is not None
        )
        workflow_target = (
            self.workflow_name is not None or self.workflow_output_id is not None
        )
        if conversation_target == workflow_target:
            raise ValueError(
                "Provide either a conversation/message target or a workflow output target."
            )
        if workflow_target and not (
            self.workflow_name and self.workflow_output_id
        ):
            raise ValueError(
                "workflow_name and workflow_output_id are required together."
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


class ResumeResponse(BaseModel):
    id: int
    user_id: int
    original_filename: str
    extracted_text: str | None
    parsed_data: dict[str, Any] | None
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


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


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=32_000)


class ApplicationResponse(BaseModel):
    id: int
    user_id: int
    job_id: int
    resume_id: int | None
    status: ApplicationStatus
    applied_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
