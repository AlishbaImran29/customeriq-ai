from datetime import datetime
from typing import Literal

from app.schemas.imports import CamelModel


class UserOut(CamelModel):
    id: str
    email: str
    name: str
    last_login_at: datetime | None
    role: Literal["owner", "staff", "viewer"] = "viewer"
    # False while the owner has not approved a new account yet: it cannot see any data until then.
    is_active: bool = True
