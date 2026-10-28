from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobquest_ai.agent.agent_factory import AgentConfigurationError, create_career_agent
from jobquest_ai.agent.career_agent import CareerAgentError
from jobquest_ai.api.schemas import ChatRequest, ChatResponse
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User

router = APIRouter(tags=["Chat"])


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
