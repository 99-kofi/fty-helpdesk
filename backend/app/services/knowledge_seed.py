"""Seed the FTY knowledge base with real FAQ examples.
Run on first admin login and on Vercel cold start if empty.
"""
from sqlalchemy.orm import Session
from app.models.knowledge import KnowledgeArticle

EXAMPLES = [
    ("Shipping", "Where do you ship?", "We ship across Ghana (Accra, Kumasi, Tamale, Takoradi + all regions) and worldwide on request. Ghana deliveries are typically 1-3 business days in Accra and 2-5 days elsewhere. International shipping times vary by destination."),
    ("Shipping", "How much is delivery?", "Delivery within Accra is GHS 30. Outside Accra is GHS 40-60 depending on region. International shipping is calculated at checkout. Free delivery is available during selected promos — ask an agent for current offers."),
    ("Shipping", "How do I track my order?", "Once your order ships, we will share a tracking number via the channel you ordered on (Instagram, WhatsApp, or email). Reply with your order number if you did not receive it and an agent will resend your tracking link."),
    ("Returns", "What is your return policy?", "You may return unworn items in original condition within 7 days of delivery for a refund or exchange. Sale items and items marked final sale cannot be returned. Contact an agent to initiate a return and you will receive a return authorization."),
    ("Returns", "How do exchanges work?", "To exchange for a different size or color, contact support within 7 days with your order number. We will hold the new item and share a return label or drop-off point. Exchanges are processed once the original item is received."),
    ("Returns", "My order arrived damaged or wrong. What do I do?", "We are sorry — please send a photo of the issue plus your order number. We will arrange a free replacement or refund immediately and escalate the case to Customer Support."),
    ("Payments", "What payment methods do you accept?", "We accept Mobile Money, Visa/Mastercard, and bank transfer. Cash on delivery is available in selected areas. If your payment failed, please retry or contact an agent — we can share an alternative payment link."),
    ("Products", "How do your sizes run?", "Our apparel is true to size. The hoodie and tees run slightly oversized for a relaxed fit. Check the size guide in each product post — an agent can also advise by height and weight if you are between sizes."),
    ("Products", "Do you restock sold-out items?", "Popular items are restocked regularly. Follow our Instagram or ask an agent to be added to the restock waitlist for your size and color — we will notify you as soon as it is back."),
    ("General", "Where is the FTY store?", "FTY is primarily online with pop-ups announced on Instagram. For wholesale, collaboration, or visit inquiries, message an agent and we will share current location and hours."),
    ("General", "How fast do you reply?", "We aim to reply within 1 hour during business hours (9am-8pm GMT). Messages sent late at night are answered first thing the next morning. Urgent order issues are prioritized automatically."),
]


def ensure_examples(db: Session) -> int:
    if db.query(KnowledgeArticle).first():
        return 0
    for category, title, body in EXAMPLES:
        db.add(KnowledgeArticle(category=category, title=title, body=body))
    db.commit()
    return len(EXAMPLES)
