from fastapi import APIRouter, Depends

from app.api.deps import enforce_role, require_user
from app.api.v1 import analytics, auth, campaigns, email_auto, email_public, carts, cash, couriers, customer_records, health, imports, inbox, internal, inventory, leads, messaging, messaging_automation, messaging_cod, messaging_media, messaging_orders, meta_ads, model_report, order_risk, profit, quick_orders, returns, seasons, shipments, webhooks, workflows

api_router = APIRouter(prefix="/api/v1")

# Public: health check and the sign-in endpoints (which guard themselves).
api_router.include_router(health.router)
api_router.include_router(auth.router)
# Meta and mail apps cannot sign in: these two protect themselves (a signature, a signed token).
api_router.include_router(webhooks.router)
api_router.include_router(email_public.router)    # the COD email buttons: a signed token, no sign-in
# The scheduler calls this with a shared secret (X-Scheduler-Secret), not a sign-in.
api_router.include_router(internal.router)

# Everything that touches customer data or the AI requires a signed-in user.
_signed_in = [Depends(require_user), Depends(enforce_role)]
api_router.include_router(imports.router, dependencies=_signed_in)
api_router.include_router(analytics.router, dependencies=_signed_in)
api_router.include_router(order_risk.router, dependencies=_signed_in)
api_router.include_router(quick_orders.router, dependencies=_signed_in)
api_router.include_router(shipments.router, dependencies=_signed_in)
api_router.include_router(couriers.router, dependencies=_signed_in)
api_router.include_router(cash.router, dependencies=_signed_in)
api_router.include_router(seasons.router, dependencies=_signed_in)
api_router.include_router(messaging.router, dependencies=_signed_in)
api_router.include_router(messaging_orders.router, dependencies=_signed_in)
api_router.include_router(messaging_media.router, dependencies=_signed_in)
api_router.include_router(campaigns.router, dependencies=_signed_in)
api_router.include_router(messaging_automation.router, dependencies=_signed_in)
api_router.include_router(model_report.router, dependencies=_signed_in)
api_router.include_router(inventory.router, dependencies=_signed_in)
api_router.include_router(messaging_cod.router, dependencies=_signed_in)
api_router.include_router(customer_records.router, dependencies=_signed_in)
api_router.include_router(workflows.router, dependencies=_signed_in)
api_router.include_router(leads.router, dependencies=_signed_in)
api_router.include_router(carts.router, dependencies=_signed_in)
api_router.include_router(returns.router, dependencies=_signed_in)
api_router.include_router(profit.router, dependencies=_signed_in)
api_router.include_router(inbox.router, dependencies=_signed_in)
api_router.include_router(meta_ads.router, dependencies=_signed_in)
api_router.include_router(email_auto.router, dependencies=_signed_in)
