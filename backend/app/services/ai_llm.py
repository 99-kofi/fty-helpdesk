"""KB-grounded LLM helper: uses Hugging Face Inference (OpenAI-compatible) when HF_TOKEN is set.

The DeepSeek model is prompted to answer *only* from the provided Knowledge Base
articles — it learns/references them, never hallucinates outside them.
Falls back to the simple article body if the LLM is not configured or fails.
"""
import os
import logging

log = logging.getLogger("fty.ai.llm")


def _hf_client():
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return None
    try:
        from openai import OpenAI

        return OpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=token,
        )
    except Exception as e:
        log.warning("HF client init failed: %s", e)
        return None


def grounded_answer(customer_message: str, articles: list[dict], model: str | None = None) -> str | None:
    """Return a concise, friendly answer grounded in `articles`, or None on failure.

    `articles` is a list of {"title": str, "body": str, "category": str}.
    """
    if not articles:
        return None
    client = _hf_client()
    if client is None:
        return None
    # Keep prompt small and explicit: reference only the provided KB.
    kb_text = "\n\n".join(
        f"[{a['category']}] {a['title']}: {a['body'][:800]}" for a in articles[:3]
    )
    system = (
        "You are FTY HelpDesk AI — a friendly, concise support assistant for Free The Youth. "
        "Answer the customer's message *only* using the Knowledge Base articles below. "
        "Do not invent policies, prices, or timelines outside them. If the answer is not in the articles, "
        "say you will escalate to a human agent. Keep replies under 120 words, warm and helpful, "
        "and end with '— FTY HelpDesk'."
    )
    user = f"Knowledge Base:\n{kb_text}\n\nCustomer message: {customer_message}\n\nAnswer helpfully, grounded in the KB."
    try:
        resp = client.chat.completions.create(
            model=model or os.environ.get("HF_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=260,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:
        log.warning("HF grounded answer failed: %s", e)
        return None
