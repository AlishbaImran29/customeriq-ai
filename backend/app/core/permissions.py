"""Who may do what. ONE table, enforced on the server for every signed-in request (hiding a button is never the protection).

ROLES   viewer < staff < owner
VIEWER  can look at everything except the owner-only pages, and can run the harmless "ask / test" actions (they change nothing).
STAFF   can do the daily work: add orders, move leads, manage returns, send messages through the normal checks.
OWNER   can do everything, including: settings, anything that deletes, erases customers, exports, recording refunds,
        switching automations on, and managing who has which role.

`minimum_role(method, path)` answers "which role is needed for this request". The rules are plain data below so they can be read,
tested and explained: add a pattern to change what a role may do.
"""

import re

ROLES = ("viewer", "staff", "owner")
RANK = {role: i for i, role in enumerate(ROLES)}

# Looking is for everyone signed in, except these pages of the owner.
OWNER_ONLY_READS = (
    r"^/api/v1/customer-records/(audit|export\.csv)$",
)

# Changing nothing: a viewer may use these (a dry-run test, a check).
VIEWER_SAFE_WRITES = (
    r"^/api/v1/workflows/(validate|test)$",
    r"^/api/v1/auth/.*$",
)

# Only the owner. (Every DELETE is owner-only too, below.)
OWNER_ONLY_WRITES = (
    r"^/api/v1/messaging/settings$",
    r"^/api/v1/messaging/test-send$",
    r"^/api/v1/customer-records/(anonymise|delete)$",
    r"^/api/v1/refunds/\d+/record$",
    r"^/api/v1/workflows/\d+/(enable|disable)$",
    r"^/api/v1/profit/settings$",
    r"^/api/v1/email-auto/settings$",
    r"^/api/v1/meta-ads/(audiences/push|events/send|ad-spend/sync)$",
)

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(re.match(p, path) for p in patterns)


def minimum_role(method: str, path: str) -> str:
    method = method.upper()
    if method in _READ_METHODS:
        return "owner" if _matches(path, OWNER_ONLY_READS) else "viewer"
    if method == "DELETE" or _matches(path, OWNER_ONLY_WRITES):
        return "owner"
    if _matches(path, VIEWER_SAFE_WRITES):
        return "viewer"
    return "staff"


def allowed(role: str | None, method: str, path: str) -> bool:
    """Is a user with this role allowed to make this request? An unknown role is allowed nothing."""
    return role in RANK and RANK[role] >= RANK[minimum_role(method, path)]
