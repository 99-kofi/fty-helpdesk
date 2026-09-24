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


def _retrieve_kb_articles(db, customer_message: str, limit: int = 4) -> list[dict]:
    """Learn from KB: retrieve most relevant articles for the message."""
    from sqlalchemy.orm import Session
    from app.models.knowledge import KnowledgeArticle
    from app.services.knowledge_seed import ensure_examples

    if hasattr(db, 'query'):
        ensure_examples(db)
    text = customer_message.lower()
    words = [w for w in text.split() if len(w) >= 3][:10]
    # Score each article by keyword overlap + category intent
    all_articles = db.query(KnowledgeArticle).all() if hasattr(db, 'query') else []
    scored: list[tuple[float, KnowledgeArticle]] = []
    for a in all_articles:
        hay = f"{a.category} {a.title} {a.body}".lower()
        score = sum(2.0 for w in words if w in hay)
        # Boost if intent keywords match category
        if 'ship' in text and a.category == 'Shipping':
            score += 3
        if any(k in text for k in ('return', 'refund', 'exchange')) and a.category == 'Returns':
            score += 3
        if any(k in text for k in ('pay', 'payment', 'momo', 'card')) and a.category == 'Payments':
            score += 3
        if score > 0:
            scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"title": a.title, "body": a.body, "category": a.category} for _, a in scored[:limit]]


def grounded_answer(customer_message: str, articles: list[dict], model: str | None = None, db=None) -> str | None:
    """Return a concise, friendly answer grounded in `articles`, or None on failure.

    `articles` is a list of {"title": str, "body": str, "category": str}.
    If `db` is provided and `articles` is empty, it will learn (retrieve) from the KB.
    """
    # Learn from KB if no articles provided but db is available
    if not articles and db is not None:
        articles = _retrieve_kb_articles(db, customer_message)
    if not articles:
        return None
    client = _hf_client()
    if client is None:
        return None
    # Provide the LLM with the richest KB context it can learn from
    kb_text = "\n\n".join(
        f"[{a['category']}] {a['title']}: {a['body'][:900]}" for a in articles[:4]
    )
    system = (
        "You are FTY HelpDesk AI — you have LEARNED from the Free The Youth Knowledge Base below. "
        "Your job is to find CONTEXTUAL SIMILARITY: even if the customer's wording is not exact, "
        "look for the closest meaning in the KB and answer from that context. For example, 'how long until it gets here' "
        "is similar to 'delivery times', 'can I send it back' is similar to 'return policy'. "
        "Answer from the most similar KB context you find. Only if there is truly no similar context at all — "
        "or the request needs human judgment (complaint, custom order, fraud) — say: 'Thanks for reaching out — I am escalating this to our sales team who will reply shortly. — FTY HelpDesk' "
        "Do not invent prices or timelines outside the KB, but do infer similar meanings. Be warm, concise, under 130 words, end with '— FTY HelpDesk' when you answer."
    )
    user = f"Learned Knowledge Base (your sole source of truth — find similar context even for imprecise phrasing):\n{kb_text}\n\nCustomer message: \"{customer_message}\"\n\nFind the most similar KB context and answer helpfully."
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
