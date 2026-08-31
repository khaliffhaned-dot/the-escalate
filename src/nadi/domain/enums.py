from enum import Enum


class OrgTier(str, Enum):
    DESK = "desk"
    GROUP = "group"
    ENTERPRISE = "enterprise"


class OrgStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDED = "offboarded"


class OrgRole(str, Enum):
    ORG_ADMIN = "org_admin"
    ORG_AUDITOR = "org_auditor"
    ORG_MEMBER = "org_member"


class WorkspaceRole(str, Enum):
    WS_ADMIN = "ws_admin"
    EDITOR = "editor"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Lang(str, Enum):
    EN = "en"
    BM = "bm"
    ZH_HANT = "zh-hant"
    ZH_HANS = "zh-hans"
    TA = "ta"
    MIXED = "mixed"


class Platform(str, Enum):
    X = "x"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    NEWS = "news"
    TELEGRAM = "telegram"
    XIAOHONGSHU = "xiaohongshu"
    OTHER = "other"


class SentimentLabel(str, Enum):
    POS = "pos"
    NEU = "neu"
    NEG = "neg"
    MIXED = "mixed"


class ThreeRFlag(str, Enum):
    RACE = "race"
    RELIGION = "religion"
    ROYALTY = "royalty"


class PESO(str, Enum):
    PAID = "paid"
    EARNED = "earned"
    SHARED = "shared"
    OWNED = "owned"


class ObjectiveStatus(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    NOT_STARTED = "not_started"


class ContributionBand(str, Enum):
    OFF_TRACK = "off_track"
    AT_RISK = "at_risk"
    ON_TRACK = "on_track"
    EXCEEDING = "exceeding"


class WarRoomStatus(str, Enum):
    OPEN = "open"
    CONTAINED = "contained"
    CLOSED = "closed"
    TABLETOP = "tabletop"


class WarRoomSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HoldingStatus(str, Enum):
    DRAFT = "draft"
    LEGAL_REVIEW = "legal_review"
    APPROVED = "approved"
    SENT_EXTERNAL = "sent_external"
    SUPERSEDED = "superseded"


class ResidueChannel(str, Enum):
    TELEGRAM_PUBLIC = "telegram_public"
    POS_RETAIL = "pos_retail"
    OWNED_PAGE = "owned_page"
    SCREENSHOT = "screenshot"
    OTHER = "other"


class ResidueStatus(str, Enum):
    DETECTED = "detected"
    SWEEPING = "sweeping"
    SUPERSEDED_NOTE = "superseded_note"
    CLEARED = "cleared"
