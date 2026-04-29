import logging
import os
from typing import Any

from openai import BadRequestError

logger = logging.getLogger(__name__)


def select_model_for_complexity(
    config: dict[str, Any], complexity_score: int
) -> str | None:
    """Select the appropriate model based on query complexity.

    Returns the model name to use, or None to use the default.

    When routing is disabled or FAST_MODEL env is not set, returns None
    (caller should use the default MODEL env var).
    """
    gen_cfg = config.get("generation", {})
    routing_cfg = gen_cfg.get("routing", {})

    if not routing_cfg.get("enabled", False):
        return None

    threshold = routing_cfg.get("complexity_threshold", 40)
    fast_env = routing_cfg.get("fast_model_env", "FAST_MODEL")
    strong_env = routing_cfg.get("strong_model_env", "MODEL")

    if complexity_score < threshold:
        fast_model = os.getenv(fast_env)
        if fast_model:
            logger.info(
                "Routing to fast model '%s' (complexity=%d < threshold=%d)",
                fast_model,
                complexity_score,
                threshold,
            )
            return fast_model

    strong_model = os.getenv(strong_env)
    if strong_model:
        logger.debug(
            "Routing to strong model '%s' (complexity=%d)",
            strong_model,
            complexity_score,
        )
    return strong_model


def openai_chat_completion(client, *, max_tokens, **kwargs):
    """Call OpenAI-compatible chat completions with max_tokens fallback.

    Tries max_tokens first (broadest compatibility), falls back to
    max_completion_tokens if the model rejects max_tokens (e.g. gpt-5.2, o1).
    """
    try:
        return client.chat.completions.create(max_tokens=max_tokens, **kwargs)
    except BadRequestError as e:
        if "max_tokens" in str(e) and "max_completion_tokens" in str(e):
            return client.chat.completions.create(
                max_completion_tokens=max_tokens, **kwargs
            )
        raise
