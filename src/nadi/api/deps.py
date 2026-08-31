from fastapi import Header, HTTPException

from nadi.api.store import store
from nadi.domain.enums import OrgRole, WorkspaceRole
from nadi.domain.rbac import effective_permissions, require


def get_ctx(
    x_nadi_role: str = Header(default="ws_admin", alias="X-Nadi-Role"),
) -> dict:
    """Demo auth: pass X-Nadi-Role: ws_admin|editor|analyst|viewer|org_admin|org_auditor."""
    org_role = None
    ws_role = None
    try:
        if x_nadi_role.startswith("org_"):
            org_role = OrgRole(x_nadi_role)
        else:
            ws_role = WorkspaceRole(x_nadi_role)
            org_role = OrgRole.ORG_MEMBER
    except ValueError as e:
        raise HTTPException(status_code=401, detail="invalid role header") from e
    perms = effective_permissions(org_role, ws_role)
    return {
        "org": store.org,
        "workspace": store.workspace,
        "user": store.user,
        "perms": perms,
        "org_role": org_role,
        "ws_role": ws_role,
    }


def need(ctx: dict, perm: str) -> None:
    try:
        require(ctx["perms"], perm)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
