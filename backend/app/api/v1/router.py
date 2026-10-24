from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.api.v1 import analytics, assistant, auth, campaigns, cash, couriers, health, imports, internal, launch, launch_steps, messaging, messaging_automation, messaging_media, messaging_orders, order_risk, quick_orders, seasons, shipments, webhooks, whatsapp_import

api_router = APIRouter(prefix="/api/v1")

# Public: health check and the sign-in endpoints (which guard themselves).
api_router.include_router(health.router)
api_router.include_router(auth.router)
# Meta and mail apps cannot sign in: these two protect themselves (a signature, a signed token).
api_router.include_router(webhooks.router)
# The scheduler calls this with a shared secret (X-Scheduler-Secret), not a sign-in.
api_router.include_router(internal.router)

# Everything that touches customer data or the AI requires a signed-in user.
_signed_in = [Depends(require_user)]
api_router.include_router(imports.router, dependencies=_signed_in)
api_router.include_router(analytics.router, dependencies=_signed_in)
api_router.include_router(assistant.router, dependencies=_signed_in)
api_router.include_router(order_risk.router, dependencies=_signed_in)
api_router.include_router(quick_orders.router, dependencies=_signed_in)
api_router.include_router(whatsapp_import.router, dependencies=_signed_in)
api_router.include_router(shipments.router, dependencies=_signed_in)
api_router.include_router(couriers.router, dependencies=_signed_in)
api_router.include_router(cash.router, dependencies=_signed_in)
api_router.include_router(seasons.router, dependencies=_signed_in)
api_router.include_router(launch.router, dependencies=_signed_in)
api_router.include_router(launch_steps.router, dependencies=_signed_in)
api_router.include_router(messaging.router, dependencies=_signed_in)
api_router.include_router(messaging_orders.router, dependencies=_signed_in)
api_router.include_router(messaging_media.router, dependencies=_signed_in)
api_router.include_router(campaigns.router, dependencies=_signed_in)
api_router.include_router(messaging_automation.router, dependencies=_signed_in)
