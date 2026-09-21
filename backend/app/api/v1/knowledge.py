"""Knowledge base (Phase 3): approved FTY answers backing agents + AI."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.knowledge import KnowledgeArticle

router = APIRouter(tags=["knowledge"], dependencies=[Depends(require_role("admin"))])


class ArticleIn(BaseModel):
    category: str
    title: str
    body: str


class ArticlePatch(BaseModel):
    category: str | None = None
    title: str | None = None
    body: str | None = None


def _out(a: KnowledgeArticle) -> dict:
    return {"id": a.id, "category": a.category, "title": a.title, "body": a.body}


@router.get("/knowledge")
def list_articles(q: str | None = None, category: str | None = None, db: Session = Depends(get_db)):
    from app.services.knowledge_seed import ensure_examples

    # First real fetch seeds the example FAQs so the feature is self-explanatory.
    ensure_examples(db)
    query = db.query(KnowledgeArticle)
    if category:
        query = query.filter(KnowledgeArticle.category == category)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (KnowledgeArticle.title.ilike(like)) | (KnowledgeArticle.body.ilike(like))
        )
    return [_out(a) for a in query.order_by(KnowledgeArticle.id.desc()).limit(100).all()]


@router.get("/knowledge/categories")
def list_categories(db: Session = Depends(get_db)):
    return sorted({r[0] for r in db.query(KnowledgeArticle.category).distinct().all()})


@router.post("/knowledge", dependencies=[Depends(require_role("admin", "manager"))])
def create_article(data: ArticleIn, db: Session = Depends(get_db)):
    a = KnowledgeArticle(category=data.category, title=data.title, body=data.body)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _out(a)


@router.patch("/knowledge/{article_id}", dependencies=[Depends(require_role("admin", "manager"))])
def patch_article(article_id: int, data: ArticlePatch, db: Session = Depends(get_db)):
    a = db.get(KnowledgeArticle, article_id)
    if not a:
        raise HTTPException(404, "Article not found")
    if data.category is not None:
        a.category = data.category
    if data.title is not None:
        a.title = data.title
    if data.body is not None:
        a.body = data.body
    db.commit()
    return _out(a)


@router.delete("/knowledge/{article_id}", dependencies=[Depends(require_role("admin", "manager"))])
def delete_article(article_id: int, db: Session = Depends(get_db)):
    a = db.get(KnowledgeArticle, article_id)
    if a:
        db.delete(a)
        db.commit()
    return {"ok": True}
