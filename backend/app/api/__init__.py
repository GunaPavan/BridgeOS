"""API route modules."""

from app.api.agent import router as agent_router
from app.api.analytics import router as analytics_router
from app.api.bridges import router as bridges_router
from app.api.donors import router as donors_router
from app.api.integrations import router as integrations_router
from app.api.outreach import router as outreach_router
from app.api.patients import router as patients_router
from app.api.recommendations import router as recommendations_router
from app.api.schedule import router as schedule_router
from app.api.simulator import router as simulator_router
from app.api.stability import router as stability_router
from app.api.whatsapp import router as whatsapp_router

__all__ = [
    "bridges_router",
    "donors_router",
    "patients_router",
    "stability_router",
    "schedule_router",
    "recommendations_router",
    "analytics_router",
    "integrations_router",
    "simulator_router",
    "whatsapp_router",
    "agent_router",
    "outreach_router",
]
