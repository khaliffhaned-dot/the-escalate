"""Listed-issuer state for a war room (Bursa Malaysia Main / ACE Market).

A war room for a listed company carries four things the rest of the product
does not know about:

* a **materiality assessment**: the Bursa disclosure decision path, recorded;
* an **insider lock**: who now holds unannounced information, and whether each
  person has been told not to deal;
* a **regulatory clock board**: every notification deadline that is running;
* a **trading-halt record**: what the desk decided about asking Bursa for a halt.

Same discipline as the rest of NADI: this module *records and prompts*, it never
files. There is no code path that submits anything to Bursa, the PDPC, NACSA or
any other regulator, and `auto_file` is forced to False on read as well as write.
Every deadline here is an aid to a human owner, tagged with how well it has been
corroborated. None of it replaces the Company Secretary or counsel.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class Market(str, Enum):
    MAIN = "main"
    ACE = "ace"


class MaterialityOutcome(str, Enum):
    NOT_MATERIAL = "not_material"
    ANNOUNCE_NOW = "announce_now"
    WITHHOLD_AND_MONITOR = "withhold_and_monitor"


class ClockStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    NOT_APPLICABLE = "not_applicable"


class HaltDecision(str, Enum):
    NONE = "none"
    REQUESTED = "requested"
    APPROVED = "approved"
    DECLINED = "declined"
    LIFTED = "lifted"


class MaterialityAssessment(BaseModel):
    assessed_at: datetime
    assessed_by: str
    could_affect_price: Literal["yes", "no", "unsure"]
    exceptional_and_confidential: bool | None = None
    leak_signals: list[str] = Field(default_factory=list)
    outcome: MaterialityOutcome
    next_steps: list[str] = Field(default_factory=list)
    counsel_confirmed: bool = False
    rationale: str = ""
    basis: str = ""


class InsiderEntry(BaseModel):
    id: str = Field(default_factory=lambda: _id("ins"))
    name: str
    role: str = ""
    told_at: datetime
    told_by: str
    notice_sent_at: datetime | None = None
    acknowledged_at: datetime | None = None


class InsiderLock(BaseModel):
    active: bool = False
    started_at: datetime | None = None
    released_at: datetime | None = None
    released_by: str | None = None
    release_note: str = ""
    insiders: list[InsiderEntry] = Field(default_factory=list)


class RegulatoryClock(BaseModel):
    key: str
    label: str
    regulator: str
    window: str
    duration_hours: float | None = None
    depends_on: str | None = None
    applies_when: str = ""
    # "C" corroborated by a secondary source, "V" verify before relying on it.
    tag: Literal["C", "V"] = "V"
    status: ClockStatus = ClockStatus.PENDING
    owner: str = ""
    started_at: datetime | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    note: str = ""


class TradingHalt(BaseModel):
    decision: HaltDecision = HaltDecision.NONE
    requested_at: datetime | None = None
    requested_by: str | None = None
    resolved_at: datetime | None = None
    note: str = ""


class ListedIssuerState(BaseModel):
    market: Market = Market.MAIN
    enabled_at: datetime
    enabled_by: str
    materiality: MaterialityAssessment | None = None
    insider_lock: InsiderLock = Field(default_factory=InsiderLock)
    clocks: list[RegulatoryClock] = Field(default_factory=list)
    halt: TradingHalt = Field(default_factory=TradingHalt)
    # Product invariant, mirrored from HoldingBrief.auto_publish: the app never
    # submits anything to a regulator or exchange on anyone's behalf.
    auto_file: bool = False
    verification_note: str = (
        "Deadlines and paragraph references are aids, not legal advice. They come from "
        "secondary sources and have not been checked against Bursa's or any regulator's "
        "own text. The Company Secretary and counsel decide."
    )

    @field_validator("auto_file")
    @classmethod
    def force_no_auto_file(cls, v: bool) -> bool:
        return False
