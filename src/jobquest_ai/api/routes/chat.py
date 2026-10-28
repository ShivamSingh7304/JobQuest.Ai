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

router = APIRouter(tags=["Chat"])


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
    try:
        agent = create_career_agent(db=db)
        response = agent.respond(current_user, payload.message)
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (CareerAgentError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

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
