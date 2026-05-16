"""Factory for text LLM clients used by agents (fact-check, etc.)."""

from app.agent_kit.utility_classes.xai_text_query import XAITextQuery


def get_text_llm() -> XAITextQuery:
    """
    Return a client implementing ``get_raw_response(system_prompt, user_message)``.

    Currently uses xAI (same stack as article generation). Swap implementation here
    if you move fact-checking to another provider.
    """
    return XAITextQuery()
