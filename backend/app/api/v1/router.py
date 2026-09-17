from fastapi import APIRouter
from app.api.v1 import auth, customers, conversations, tickets, misc, channels, webchat, oauth, teams
from app.api.v1 import users as users_api
from app.api.v1 import automation as automation_api
from app.api.v1 import knowledge as knowledge_api
from app.api.v1 import analytics as analytics_api

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(conversations.router)
api_router.include_router(tickets.router)
api_router.include_router(misc.router)
api_router.include_router(channels.router)
api_router.include_router(oauth.router)
api_router.include_router(teams.router)
api_router.include_router(users_api.router)
api_router.include_router(automation_api.router)
api_router.include_router(knowledge_api.router)
api_router.include_router(analytics_api.router)
api_router.include_router(webchat.router)
