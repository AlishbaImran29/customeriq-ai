from fastapi import APIRouter, Depends

from app.api.deps import require_user
from app.api.v1 import analytics, assistant, auth, couriers, health, imports, order_risk, quick_orders, shipments, whatsapp_import

api_router = APIRouter(prefix="/api/v1")

# Public: health check and the sign-in endpoints (which guard themselves).
api_router.include_router(health.router)
api_router.include_router(auth.router)

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
