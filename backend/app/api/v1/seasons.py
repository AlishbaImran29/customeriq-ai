"""Season Forecast endpoints: the forecast per season, and the weekly product sales it learns from."""

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.shipments import _read_limited
from app.db.session import get_db
from app.models import ProductSale
from app.models.shipment import SOURCE_DEMO
from app.schemas.seasons import (
    BackTestOut, ProductForecastOut, ProductSalesImportOut, ProductSalesSummaryOut, SeasonOut, SeasonsOut, WindowOut,
)
from app.schemas.shipments import DemoDeleteOut
from app.services import data_rules
from app.services.import_files import file_type_of
from app.services.product_sales_import import MAX_STORED_ERRORS, import_product_sales, load_weekly_sales
from app.services.season_forecast import SeasonResult, forecast_seasons
from app.services.seasons import SEASONS, Window

router = APIRouter(prefix="/seasons", tags=["seasons"])


def _window(w: Window | None) -> WindowOut | None:
    return WindowOut(start=w.start, end=w.end) if w else None


def _season(r: SeasonResult) -> SeasonOut:
    b = r.backtest
    return SeasonOut(
        id=r.season_id, name=r.name, status=r.status, reason=r.reason, target_year=r.target_year, window=_window(r.window),
        last_year_window=_window(r.last_year_window), forecast_date=r.forecast_date, products=r.products,
        backtest=BackTestOut(
            cases=b.cases, rows=b.rows, tested=b.tested, model_mae=b.model_mae, baseline_mae=b.baseline_mae,
            model_mape=b.model_mape, baseline_mape=b.baseline_mape, improvement=b.improvement, passed=b.passed,
        ),
        rows=[ProductForecastOut(product=p.product, last_year=p.last_year, forecast=p.forecast, low=p.low, high=p.high, advice=p.advice) for p in r.rows],
    )


@router.get("/forecast", response_model=SeasonsOut, summary="Units to expect per product in each coming season")
def forecast(source: str = Query("auto", pattern="^(auto|real|demo)$"), db: Session = Depends(get_db)) -> SeasonsOut:
    """A forecast appears only for a season where the model beat last year's sales on held-out seasons."""
    used, real, demo, sales = load_weekly_sales(db, source)
    results = forecast_seasons(sales, SEASONS)
    return SeasonsOut(
        source_used=used, real_weeks=real, demo_weeks=demo, data_from=sales.first, data_to=sales.data_end,
        min_group_count=data_rules.MIN_GROUP_COUNT, seasons=[_season(r) for r in results],
    )


@router.post("/sales/import", response_model=ProductSalesImportOut, status_code=status.HTTP_201_CREATED, summary="Import units sold per product")
async def import_file(file: UploadFile, db: Session = Depends(get_db)) -> ProductSalesImportOut:
    file_type = file_type_of((file.filename or "sales")[:255])
    content = await _read_limited(file)
    r = await run_in_threadpool(import_product_sales, db, content, file_type)
    return ProductSalesImportOut(
        rows_in_file=r.rows_in_file, weeks_created=r.weeks_created, weeks_updated=r.weeks_updated, rejected=r.rejected,
        products=r.products, first_week=r.first_week, last_week=r.last_week, error_count=r.error_count, errors=r.errors,
        errors_truncated=r.error_count > MAX_STORED_ERRORS,
    )


@router.get("/sales/summary", response_model=ProductSalesSummaryOut, summary="How much product data is saved")
def sales_summary(db: Session = Depends(get_db)) -> ProductSalesSummaryOut:
    total = db.scalar(select(func.count()).select_from(ProductSale)) or 0
    demo = db.scalar(select(func.count()).select_from(ProductSale).where(ProductSale.source == SOURCE_DEMO)) or 0
    return ProductSalesSummaryOut(product_weeks=int(total), demo_product_weeks=int(demo))


@router.delete("/sales/demo", response_model=DemoDeleteOut, summary="Delete the made-up demo product sales")
def delete_demo(db: Session = Depends(get_db)) -> DemoDeleteOut:
    """Only product sales marked as demo data; real ones are never touched."""
    deleted = db.execute(delete(ProductSale).where(ProductSale.source == SOURCE_DEMO)).rowcount or 0
    db.commit()
    return DemoDeleteOut(deleted=int(deleted))
