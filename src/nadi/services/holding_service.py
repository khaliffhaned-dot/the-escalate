"""Holding statements — template path (no auto-publish, no AVE)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from nadi.config import settings
from nadi.domain.enums import HoldingStatus
from nadi.domain.models import HoldingBrief, Mention

# Word boundaries matter: a bare `ave` also matches "have", "save" and "available", so
# an ordinary sentence ("We have confirmed...") tripped the guard and raised.
_AVE_RE = re.compile(r"\b(?:ave|emv)\b|advertising\s*value|media\s*value|pr\s*value", re.I)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "holding_system.txt"


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def reject_if_ave_requested(payload: dict) -> None:
    if payload.get("include_ave") or payload.get("publish") is True or payload.get("media_value"):
        raise ValueError("AVE / auto-publish not allowed under Barcelona Principles 4.0")


def _hash_prompt(system: str, facts: str) -> str:
    return "sha256:" + hashlib.sha256((system + facts).encode()).hexdigest()[:16]


def draft_holding_from_mentions(
    *,
    mentions: list[Mention],
    war_room_id: str | None,
    locale: str = "bilingual",
    audience: str = "press",
    tabletop: bool = False,
) -> HoldingBrief:
    """Deterministic starter draft for residue / 3R cases."""
    reject_if_ave_requested({})
    system = load_system_prompt()
    facts_ids = [m.id for m in mentions]
    texts = " | ".join((m.excerpt or m.text)[:180] for m in mentions)
    flags = sorted({f.value for m in mentions for f in m.three_r.flags})

    # Six parts, same order in EN and BM: happened, care, confirmed, not yet
    # confirmed, being done, what to do + next update (see prompts/holding_system.txt).
    en = (
        "We are aware of circulating materials related to a prior creative line. "
        "We take community sensitivities seriously and will not add to the concern with a second apology. "
        "Owned channels no longer use that line, and current campaign creative does not use it. "
        "We are still establishing how much of it remains in retail points. "
        "We are completing a retail and residual-asset sweep and will apply a one-line superseded notice where needed. "
        "If you see the material in a shop or online, please tell us at [contact]. "
        "We will share the next update by [next update: time to be set by the desk]."
    )
    bm = (
        "Kami sedar tentang bahan yang masih beredar berkaitan baris kreatif lama. "
        "Kami mengambil serius kepekaan masyarakat dan tidak akan menambah kebimbangan dengan permohonan maaf kali kedua. "
        "Saluran rasmi tidak lagi menggunakan baris itu, dan kreatif kempen semasa tidak menggunakannya. "
        "Kami masih mengesahkan berapa banyak yang masih ada di premis runcit. "
        "Sapuan runcit dan aset sisa sedang diselesaikan, dengan notis satu baris 'telah diganti' jika perlu. "
        "Jika anda terserempak dengan bahan itu di kedai atau dalam talian, sila maklumkan kepada kami di [hubungan]. "
        "Kemas kini seterusnya akan dikongsi menjelang [kemas kini seterusnya: masa ditetapkan oleh pasukan]."
    )
    if tabletop:
        en = f"[TABLETOP — DO NOT SEND] {en}"
        bm = f"[TABLETOP — JANGAN HANTAR] {bm}"

    if _AVE_RE.search(en) or _AVE_RE.search(bm):
        raise RuntimeError("holding body failed AVE guard")

    posture = "self_regulated_not_directed"
    ops = [
        {
            "action": "Complete residual asset / POS sweep within 48h",
            "owner_role": "editor",
            "sla_hours": 48,
            "objective_ids": ["O4"],
        },
        {
            "action": "Use one-line superseded notice only — no second apology",
            "owner_role": "editor",
            "sla_hours": 24,
            "objective_ids": ["O4"],
        },
    ]
    if "royalty" in flags:
        ops.append(
            {
                "action": "Legal/comms review of 3R posture before any external line",
                "owner_role": "ws_admin",
                "sla_hours": 12,
                "objective_ids": ["O4"],
            }
        )

    return HoldingBrief(
        war_room_id=war_room_id,
        status=HoldingStatus.DRAFT,
        locale=locale,
        audience=audience,
        facts_used=facts_ids,
        gaps=[
            "Confirm original print-run authorisation trail if asked",
            "Set the next-update time and the contact line in part 6 before sending",
        ],
        lines={"en": en, "bm": bm},
        do_not_say=[
            "That the line was directed by any authority",
            "Any AVE or circulation value",
            "A second public apology unless new facts require it",
        ],
        ops=ops,
        posture=posture,
        model_version=settings.brief_model_version,
        prompt_hash=_hash_prompt(system, texts),
    )


def transition(holding: HoldingBrief, new_status: HoldingStatus) -> HoldingBrief:
    allowed = {
        HoldingStatus.DRAFT: {HoldingStatus.LEGAL_REVIEW, HoldingStatus.APPROVED, HoldingStatus.SUPERSEDED},
        HoldingStatus.LEGAL_REVIEW: {HoldingStatus.APPROVED, HoldingStatus.DRAFT, HoldingStatus.SUPERSEDED},
        HoldingStatus.APPROVED: {HoldingStatus.SENT_EXTERNAL, HoldingStatus.SUPERSEDED},
        HoldingStatus.SENT_EXTERNAL: {HoldingStatus.SUPERSEDED},
        HoldingStatus.SUPERSEDED: set(),
    }
    if new_status not in allowed.get(holding.status, set()):
        raise ValueError(f"cannot transition {holding.status} -> {new_status}")
    holding.status = new_status
    return holding
