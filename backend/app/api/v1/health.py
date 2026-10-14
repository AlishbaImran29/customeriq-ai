from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.db.session import DatabaseStatus, check_database

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: DatabaseStatus


def get_database_status() -> DatabaseStatus:
    return check_database()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database not reachable"}},
)
def health(
    response: Response, database: DatabaseStatus = Depends(get_database_status)
) -> HealthResponse:
    """Report whether the API is running and whether PostgreSQL is reachable."""
    if database != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database=database)
    return HealthResponse(status="ok", database=database)
