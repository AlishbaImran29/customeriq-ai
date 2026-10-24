"""SQLAlchemy models. Importing this package registers every table on `Base`."""

from app.models.base import Base
from app.models.campaign import Campaign, CampaignRecipient, CatalogProduct
from app.models.courier_payment import CourierPayment
from app.models.customer_media import CustomerMedia
from app.models.customer import Customer
from app.models.import_job import ImportJob, ImportStatus
from app.models.journey import Journey, JourneyEnrollment, SchedulerState
from app.models.launch import (AiCache, CompetitorAd, CreativeItem, LaunchProduct, LaunchProject, TrendUpload, Vendor, VendorQuote)
from app.models.messaging import (ConsentEvent, CustomerConsent, IncomingMessage, Message, MessageTemplate, MessagingSettings)
from app.models.order import Order
from app.models.order_status import OrderStatusHistory, WebhookEvent
from app.models.order_risk_run import OrderRiskRun
from app.models.product_sale import ProductSale
from app.models.shipment import Shipment
from app.models.user import User, UserSession

__all__ = ["Journey", "JourneyEnrollment", "SchedulerState", "Campaign", "CampaignRecipient", "CatalogProduct", "CustomerMedia", "OrderStatusHistory", "WebhookEvent", "ConsentEvent", "CustomerConsent", "IncomingMessage", "Message", "MessageTemplate", "MessagingSettings", "AiCache", "Base", "CompetitorAd", "CreativeItem", "LaunchProduct", "Vendor", "VendorQuote", "LaunchProject", "TrendUpload", "CourierPayment", "Customer", "ImportJob", "ImportStatus", "Order", "OrderRiskRun", "ProductSale", "Shipment", "User", "UserSession"]
