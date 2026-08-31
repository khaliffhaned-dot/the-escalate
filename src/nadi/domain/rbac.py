"""Tenant isolation + RBAC — locked matrix."""

from __future__ import annotations

from nadi.domain.enums import OrgRole, WorkspaceRole

# Permission catalogue
ORG_MANAGE = "org.manage"
ORG_BILLING = "org.billing"
ORG_SSO = "org.sso"
ORG_USERS = "org.users"
ORG_AUDIT_READ = "org.audit.read"
ORG_WORKSPACES_CREATE = "org.workspaces.create"
ORG_EXPORT_GOVERNANCE = "org.export.governance"

WS_READ = "ws.read"
WS_MENTIONS_READ = "ws.mentions.read"
WS_MENTIONS_EXPORT = "ws.mentions.export"
WS_MENTIONS_CODE = "ws.mentions.code"
WS_ALERTS_MANAGE = "ws.alerts.manage"
WS_CONNECTORS_MANAGE = "ws.connectors.manage"
WS_USERS_MANAGE = "ws.users.manage"
WS_EVALUATION_READ = "ws.evaluation.read"
WS_EVALUATION_OBJECTIVES = "ws.evaluation.objectives"
WS_EVALUATION_LOCK = "ws.evaluation.lock"
WS_BRIEF_RUN = "ws.brief.run"
WS_TAXONOMY_MANAGE = "ws.taxonomy.manage"
WS_WAR_ROOM = "ws.war_room"
WS_REPORTS_RUN = "ws.reports.run"

ORG_ROLE_PERMS: dict[OrgRole, frozenset[str]] = {
    OrgRole.ORG_ADMIN: frozenset(
        {
            ORG_MANAGE,
            ORG_BILLING,
            ORG_SSO,
            ORG_USERS,
            ORG_AUDIT_READ,
            ORG_WORKSPACES_CREATE,
            ORG_EXPORT_GOVERNANCE,
            WS_USERS_MANAGE,
            WS_EVALUATION_READ,  # roll-up only unless also ws member
        }
    ),
    OrgRole.ORG_AUDITOR: frozenset({ORG_AUDIT_READ, ORG_EXPORT_GOVERNANCE, WS_EVALUATION_READ}),
    OrgRole.ORG_MEMBER: frozenset(),
}

WS_ROLE_PERMS: dict[WorkspaceRole, frozenset[str]] = {
    WorkspaceRole.WS_ADMIN: frozenset(
        {
            WS_READ,
            WS_MENTIONS_READ,
            WS_MENTIONS_EXPORT,
            WS_MENTIONS_CODE,
            WS_ALERTS_MANAGE,
            WS_CONNECTORS_MANAGE,
            WS_USERS_MANAGE,
            WS_EVALUATION_READ,
            WS_EVALUATION_OBJECTIVES,
            WS_EVALUATION_LOCK,
            WS_BRIEF_RUN,
            WS_TAXONOMY_MANAGE,
            WS_WAR_ROOM,
            WS_REPORTS_RUN,
        }
    ),
    WorkspaceRole.EDITOR: frozenset(
        {
            WS_READ,
            WS_MENTIONS_READ,
            WS_MENTIONS_EXPORT,
            WS_MENTIONS_CODE,
            WS_ALERTS_MANAGE,
            WS_EVALUATION_READ,
            WS_EVALUATION_OBJECTIVES,
            WS_BRIEF_RUN,
            WS_WAR_ROOM,
            WS_REPORTS_RUN,
        }
    ),
    WorkspaceRole.ANALYST: frozenset(
        {
            WS_READ,
            WS_MENTIONS_READ,
            WS_EVALUATION_READ,
            WS_BRIEF_RUN,
        }
    ),
    WorkspaceRole.VIEWER: frozenset(
        {
            WS_READ,
            WS_MENTIONS_READ,
            WS_EVALUATION_READ,
        }
    ),
}


def effective_permissions(
    org_role: OrgRole | None,
    ws_role: WorkspaceRole | None,
) -> frozenset[str]:
    perms: set[str] = set()
    if org_role:
        perms |= ORG_ROLE_PERMS.get(org_role, frozenset())
    if ws_role:
        perms |= WS_ROLE_PERMS.get(ws_role, frozenset())
    return frozenset(perms)


def require(perms: frozenset[str], needed: str) -> None:
    if needed not in perms:
        raise PermissionError(f"missing permission: {needed}")
