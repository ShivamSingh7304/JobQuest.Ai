"""Application startup warm-up for expensive local and remote clients."""

import logging
import time

logger = logging.getLogger(__name__)


def warm_up_components() -> None:
    """Initialize reusable model clients before the first user request.

    Warm-up failures are logged but do not prevent the API from starting. Groq
    model weights are hosted remotely, so this initializes the client only;
    Hugging Face embeddings are loaded locally and are actually warmed up.
    """
    started = time.perf_counter()

    try:
        from jobquest_ai.retrieval.embeddings import get_embeddings

        embeddings = get_embeddings()
        embeddings.embed_query("JobQuest.Ai startup warm-up")
        logger.info("embedding_model_warmup_completed")
    except Exception:
        logger.exception("embedding_model_warmup_failed")

    try:
        from jobquest_ai.retrieval.vector_store import get_qdrant_vector_store

        get_qdrant_vector_store()
        logger.info("vector_store_warmup_completed")
    except Exception:
        logger.exception("vector_store_warmup_failed")

    try:
        from jobquest_ai.agent.agent_factory import create_career_agent

        create_career_agent()
        logger.info("llm_client_warmup_completed")
    except Exception:
        logger.exception("llm_client_warmup_failed")

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info("application_warmup_completed duration_ms=%.2f", duration_ms)
