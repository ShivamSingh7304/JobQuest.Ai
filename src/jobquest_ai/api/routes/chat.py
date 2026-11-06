import json
import json
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobquest_ai.agent.agent_factory import AgentConfigurationError, create_career_agent
from jobquest_ai.agent.career_agent import CareerAgentError
from jobquest_ai.api.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    ConversationWithMessagesResponse,
    MessageCreate,
    MessageResponse,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.conversation_message_repository import (
    ConversationMessageRepository,
)
from jobquest_ai.database.repositories.conversation_repository import (
    ConversationRepository,
)
from jobquest_ai.tools.job_tools import (
    rank_saved_jobs,
    reset_job_context,
    set_job_context,
)

router = APIRouter(tags=["Chat"])
logger = logging.getLogger(__name__)

_SAVED_JOB_QUERY = re.compile(
    r"\b(saved jobs?|saved opportunities|which .*job.*fit|most fit)\b",
    re.IGNORECASE,
)


def _saved_job_response(db: Session, user_id: int) -> str:
    token = set_job_context(db, user_id)
    try:
        result = json.loads(rank_saved_jobs.invoke({}))
    finally:
        reset_job_context(token)

    jobs = result.get("jobs", [])
    if not jobs:
        return "You do not have any saved jobs to compare yet. Save a job from Job Discovery first."

    if not result.get("resume_available"):
        return "You have saved jobs, but I need a parsed resume before I can rank which one fits you best."

    lines = ["## Best matches among your saved jobs", ""]
    for index, job in enumerate(jobs[:5], start=1):
        score = float(job.get("match_score", 0))
        title = job.get("title") or "Untitled role"
        company = job.get("company") or "Unknown company"
        skills = job.get("matched_skills") or []
        skill_text = ", ".join(skills[:5]) if skills else "No explicit skill overlap found"
        lines.append(f"{index}. **{title}** at **{company}** — **{score:.0f}% match**")
        lines.append(f"   - Matching evidence: {skill_text}")
    lines.extend([
        "",
        "This is a relative ranking based on your parsed resume, not a hiring probability.",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_owned_conversation(
    conversation_id: int,
    current_user: User,
    db: Session,
):
    """Fetch a conversation and verify ownership; raise 404/403 otherwise."""
    repo = ConversationRepository(db)
    conversation = repo.get_by_id(conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation.",
        )
    return conversation


# ---------------------------------------------------------------------------
# AI chat (existing)
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ChatResponse:
    if _SAVED_JOB_QUERY.search(payload.message):
        try:
            response = _saved_job_response(db, current_user.id)
            logger.info("saved_job_ranking_completed user_id=%s", current_user.id)
            return ChatResponse(response=response)
        except Exception as exc:
            logger.exception("saved_job_ranking_failed user_id=%s", current_user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saved jobs could not be ranked right now.",
            ) from exc

    try:
        logger.info("chat_started user_id=%s message_length=%s", current_user.id, len(payload.message))
        agent = create_career_agent(db=db)
        response = agent.respond(current_user, payload.message)
    except AgentConfigurationError as exc:
        logger.exception("chat_agent_configuration_failed user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (CareerAgentError, ValueError) as exc:
        logger.exception("chat_failed user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info("chat_completed user_id=%s response_length=%s", current_user.id, len(response))
    return ChatResponse(response=response)


# ---------------------------------------------------------------------------
# Conversations — CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
def create_conversation(
    payload: ConversationCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversationResponse:
    repo = ConversationRepository(db)
    conversation = repo.create(user_id=current_user.id, title=payload.title)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List the current user's conversations",
)
def list_conversations(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ConversationResponse]:
    repo = ConversationRepository(db)
    conversations = repo.list_by_user(
        user_id=current_user.id, skip=skip, limit=limit
    )
    return [ConversationResponse.model_validate(c) for c in conversations]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithMessagesResponse,
    summary="Retrieve a conversation with its full message history",
)
def get_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> ConversationWithMessagesResponse:
    conversation = _get_owned_conversation(conversation_id, current_user, db)
    messages = ConversationMessageRepository(db).list_by_conversation(
        conversation_id=conversation_id, skip=skip, limit=limit
    )
    return ConversationWithMessagesResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update a conversation's title",
)
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversationResponse:
    conversation = _get_owned_conversation(conversation_id, current_user, db)
    repo = ConversationRepository(db)
    updated = repo.update_title(conversation, payload.title)
    return ConversationResponse.model_validate(updated)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all its messages",
)
def delete_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    conversation = _get_owned_conversation(conversation_id, current_user, db)
    ConversationRepository(db).delete(conversation)


# ---------------------------------------------------------------------------
# Messages — append & list
# ---------------------------------------------------------------------------

@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a message to a conversation",
)
def add_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MessageResponse:
    _get_owned_conversation(conversation_id, current_user, db)
    try:
        message = ConversationMessageRepository(db).add(
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return MessageResponse.model_validate(message)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    summary="List messages in a conversation (ordered oldest→newest)",
)
def list_messages(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[MessageResponse]:
    _get_owned_conversation(conversation_id, current_user, db)
    messages = ConversationMessageRepository(db).list_by_conversation(
        conversation_id=conversation_id, skip=skip, limit=limit
    )
    return [MessageResponse.model_validate(m) for m in messages]
