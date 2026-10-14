"""Listed-issuer logic for war rooms: materiality, insider lock, clocks, halt prompt.

Pure functions over `ListedIssuerState`, so every rule here is testable without a
store, a clock or a network. The routes in `api/routes/listed.py` are thin wrappers.

What this module does NOT do, on purpose: file with Bursa, notify any regulator,
request a halt, or send a notice. It records what a human decided and prompts what
a human should consider. Every rule below is a simplification of the Bursa
disclosure path and the playbook's clock board; the Company Secretary decides.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nadi.domain.listed import (
    ClockStatus,
    HaltDecision,
    InsiderEntry,
    ListedIssuerState,
    Market,
    MaterialityAssessment,
    MaterialityOutcome,
    RegulatoryClock,
)

# Malaysia does not observe daylight saving, so a fixed offset is exact and avoids
# depending on a system tz database being installed.
KL = timezone(timedelta(hours=8))

BASIS = (
    "Simplified from Bursa Main Market Listing Requirements Chapter 9 (immediate "
    "disclosure; narrow exception for exceptional circumstances with complete "
    "confidentiality). Paragraph numbers and exact conditions have not been checked "
    "against Bursa's own text. Confirm with the Company Secretary."
)

HALT_BASIS = (
    "Halts are requested from Bursa under Practice Note 2 (requests for suspension) "
    "and Bursa decides. Sub-paragraph references vary between examples; confirm the "
    "current wording with the Company Secretary."
)

MARKET_CAVEAT = (
    "Public holidays and half-day sessions are not modelled. Check Bursa's calendar."
)


class ListedIssuerError(ValueError):
    """A rule was broken (wrong order, missing reason). Routes map this to 422."""


class ListedIssuerNotFound(ListedIssuerError):
    """An unknown clock key or insider id. Routes map this to 404."""


def aware(dt: datetime | None, default: datetime | None = None) -> datetime:
    """Return a timezone-aware datetime. Naive input is read as Kuala Lumpur time,
    the workspace default, never as the server's local time."""
    if dt is None:
        if default is None:
            raise ListedIssuerError("a datetime is required")
        return default
    return dt.replace(tzinfo=KL) if dt.tzinfo is None else dt


# --------------------------------------------------------------------- clocks
# (key, label, regulator, window text, hours, depends_on, applies_when, tag)
# Windows follow the playbook's clock board (Section 2.3 / 5.4). "C" = corroborated by
# a secondary source while drafting; "V" = verify against the current document.
_CATALOGUE: tuple[tuple, ...] = (
    ("bursa_material", "Announce material information", "Bursa Malaysia",
     "Immediately", 0, None, "Material information exists and no exception applies", "C"),
    ("bursa_uma", "Reply to UMA / Exchange query", "Bursa Malaysia",
     "As stated in Bursa's query; board-endorsed reply", None, None,
     "Bursa has queried unusual trading or an unannounced development", "C"),
    ("pdpc_breach", "Personal data breach: notify the Commissioner", "PDPC",
     "Within 72 hours of the breach or of being informed", 72, None,
     "Notifiable personal data breach (PDPA as amended)", "C"),
    ("pdpc_individuals", "Notify affected individuals", "PDPC / PDPA",
     "Without unnecessary delay, no later than 7 days after notifying the PDPC", 168,
     "pdpc_breach", "After the PDPC has been notified", "C"),
    ("nacsa_notice", "Cyber incident: immediate notice", "NACSA and sector lead",
     "Immediate electronic notice", 0, None,
     "Designated NCII entities only (Cyber Security Act 2024)", "C"),
    ("nacsa_report", "Cyber incident: fuller report", "NACSA",
     "Within 6 hours; confirm when this clock starts", 6, None,
     "Designated NCII entities only", "C"),
    ("nacsa_supplement", "Cyber incident: supplementary report", "NACSA",
     "Within 14 days; confirm when this clock starts", 336, None,
     "Designated NCII entities only", "C"),
    ("bnm_rmit", "Technology incident (financial institutions)", "Bank Negara Malaysia",
     "Short window; confirm in the current RMiT policy document", None, None,
     "Incident under RMiT", "V"),
    ("dosh_notice", "Workplace death or serious injury: notify", "DOSH (JKKP)",
     "Immediately, by the quickest means", 0, None,
     "Qualifying workplace accident (secondary source)", "C"),
    ("dosh_report", "Workplace accident: written report", "DOSH (JKKP)",
     "Written report within 7 days", 168, None,
     "Qualifying workplace accident (secondary source)", "C"),
    ("lenders_trustees", "Lenders and trustees", "Per facility or trust deed",
     "Check the document", None, None, "Covenant or event-of-default trigger", "V"),
    ("insurers", "Insurers", "Per policy",
     "Often 'as soon as practicable'; check the policy", None, None,
     "Potential claim", "V"),
)

CLOCK_KEYS = tuple(c[0] for c in _CATALOGUE)


def clock_catalogue() -> list[RegulatoryClock]:
    return [
        RegulatoryClock(
            key=k, label=label, regulator=reg, window=window, duration_hours=hours,
            depends_on=dep, applies_when=when, tag=tag,
        )
        for (k, label, reg, window, hours, dep, when, tag) in _CATALOGUE
    ]


def new_state(*, market: Market, actor: str, now: datetime) -> ListedIssuerState:
    return ListedIssuerState(
        market=market, enabled_at=now, enabled_by=actor, clocks=clock_catalogue()
    )


def _clock(state: ListedIssuerState, key: str) -> RegulatoryClock:
    for c in state.clocks:
        if c.key == key:
            return c
    raise ListedIssuerNotFound(f"unknown clock: {key}")


def start_clock(
    state: ListedIssuerState,
    key: str,
    *,
    now: datetime,
    owner: str = "",
    started_at: datetime | None = None,
    due_at: datetime | None = None,
) -> RegulatoryClock:
    c = _clock(state, key)
    if c.status == ClockStatus.DONE:
        raise ListedIssuerError(f"clock {key} is already done")
    if c.depends_on:
        parent = _clock(state, c.depends_on)
        if parent.status != ClockStatus.DONE or parent.completed_at is None:
            raise ListedIssuerError(
                f"{key} starts when {c.depends_on} is done (it runs from that notification)"
            )
        start = aware(started_at, parent.completed_at)
    else:
        start = aware(started_at, now)
    c.status = ClockStatus.RUNNING
    c.started_at = start
    c.owner = owner or c.owner
    if due_at is not None:
        c.due_at = aware(due_at)
    elif c.duration_hours is not None:
        c.due_at = start + timedelta(hours=c.duration_hours)
    else:
        c.due_at = None  # the deadline lives in a source document; the board says so
    return c


def complete_clock(
    state: ListedIssuerState,
    key: str,
    *,
    now: datetime,
    completed_at: datetime | None = None,
    note: str = "",
) -> RegulatoryClock:
    c = _clock(state, key)
    if c.status != ClockStatus.RUNNING:
        raise ListedIssuerError(f"clock {key} is not running; start it first")
    c.status = ClockStatus.DONE
    c.completed_at = aware(completed_at, now)
    if note:
        c.note = note
    return c


def mark_not_applicable(state: ListedIssuerState, key: str, *, note: str) -> RegulatoryClock:
    if not note.strip():
        raise ListedIssuerError("say why the clock does not apply")
    c = _clock(state, key)
    if c.status == ClockStatus.DONE:
        raise ListedIssuerError(f"clock {key} is already done")
    c.status = ClockStatus.NOT_APPLICABLE
    c.note = note.strip()
    return c


def clock_board(state: ListedIssuerState, now: datetime) -> list[dict]:
    """Every clock with its computed state. `overdue` only for timed clocks: an
    "immediate" duty is shown as running with the minutes elapsed instead, because
    it is due the moment it starts, not late after a grace period."""
    by_key = {c.key: c for c in state.clocks}
    rows: list[dict] = []
    for c in state.clocks:
        immediate = c.duration_hours == 0
        elapsed = remaining = None
        computed = c.status.value
        if c.status == ClockStatus.RUNNING and c.started_at:
            elapsed = int((now - c.started_at).total_seconds() // 60)
            if c.due_at and not immediate:
                remaining = int((c.due_at - now).total_seconds() // 60)
                if remaining < 0:
                    computed = "overdue"
        blocked = bool(
            c.depends_on and by_key[c.depends_on].status != ClockStatus.DONE
            and c.status == ClockStatus.PENDING
        )
        rows.append(
            {
                **c.model_dump(mode="json"),
                "state": computed,
                "immediate": immediate,
                "minutes_remaining": remaining,
                "elapsed_minutes": elapsed,
                "blocked": blocked,
                "deadline_in_source": c.status == ClockStatus.RUNNING and c.due_at is None,
            }
        )
    return rows


# ---------------------------------------------------------------- materiality
def assess_materiality(
    *,
    could_affect_price: str,
    exceptional_and_confidential: bool | None,
    leak_signals: list[str] | None,
    assessed_by: str,
    now: datetime,
    counsel_confirmed: bool = False,
) -> MaterialityAssessment:
    """The four-question disclosure path, applied mechanically.

    1. Could it reasonably affect the price, value or market activity of the
       securities, or an investor's decision?  no -> normal route.
       "unsure" is treated as yes: if it might be price-sensitive, treat it as
       price-sensitive until counsel says otherwise.
    2. Are there exceptional circumstances AND is the information fully
       confidential?  no (or not established) -> announce now.
    3. Withhold: keep the insider list, keep the announcement drafted, watch the
       market. Withholding is an exception.
    4. Any leak, rumour or unusual trading?  yes -> announce now.
    """
    if could_affect_price not in ("yes", "no", "unsure"):
        raise ListedIssuerError("could_affect_price must be yes, no or unsure")
    signals = [s.strip() for s in (leak_signals or []) if s and s.strip()]

    if could_affect_price == "no":
        outcome = MaterialityOutcome.NOT_MATERIAL
        why = "Judged unlikely to affect price, value, market activity or an investor's decision."
        steps = [
            "Use the normal communications route; no Bursa announcement is needed on this reading.",
            "Re-run this check if the facts change, if the press or an analyst asks, or if Bursa queries trading.",
        ]
    elif exceptional_and_confidential is not True:
        outcome = MaterialityOutcome.ANNOUNCE_NOW
        why = (
            "Could affect price or an investor's decision"
            + (" (unsure counts as yes)" if could_affect_price == "unsure" else "")
            + ", and exceptional circumstances with complete confidentiality are not established."
        )
        steps = _announce_steps()
    elif signals:
        outcome = MaterialityOutcome.ANNOUNCE_NOW
        why = "A leak, rumour or unusual trading ends the exception: " + "; ".join(signals) + "."
        steps = _announce_steps()
    else:
        outcome = MaterialityOutcome.WITHHOLD_AND_MONITOR
        why = (
            "Exceptional circumstances and complete confidentiality are asserted, and no leak "
            "signal is recorded. Withholding is an exception and the presumption is disclosure."
        )
        steps = [
            "Keep the insider list current and the do-not-trade notice in force.",
            "Keep the Bursa announcement drafted and ready to release.",
            "Watch trading, press and social closely; any leak, rumour or unusual trading means announce immediately.",
            "Have the Company Secretary confirm the exception is still available at each review.",
        ]
    return MaterialityAssessment(
        assessed_at=now,
        assessed_by=assessed_by,
        could_affect_price=could_affect_price,  # type: ignore[arg-type]
        exceptional_and_confidential=exceptional_and_confidential,
        leak_signals=signals,
        outcome=outcome,
        next_steps=steps,
        counsel_confirmed=counsel_confirmed,
        rationale=why,
        basis=BASIS,
    )


def _announce_steps() -> list[str]:
    return [
        "Company Secretary submits the announcement through Bursa LINK. Bursa first, then press release, website and social, then staff note, then analyst and investor calls.",
        "Start the Bursa clock and the insider lock now.",
        "Do not tell analysts, shareholders or journalists before the market has the news.",
        "If it cannot be released at once while the market is open, ask the Company Secretary whether to request a trading halt.",
    ]


# ------------------------------------------------------------ market and halt
def market_status(now: datetime) -> dict:
    """Bursa securities-market phases in Kuala Lumpur time, from broker pages:
    pre-open 08:30-09:00 and 14:00-14:30, continuous trading to 12:30 and from
    14:30, closing 17:00. Holidays are not modelled."""
    local = now.astimezone(KL)
    hhmm = local.hour * 60 + local.minute
    if local.weekday() >= 5:
        status = "closed"
    elif 8 * 60 + 30 <= hhmm < 9 * 60 or 14 * 60 <= hhmm < 14 * 60 + 30:
        status = "pre_open"
    elif 9 * 60 <= hhmm < 12 * 60 + 30 or 14 * 60 + 30 <= hhmm < 17 * 60:
        status = "open"
    elif 12 * 60 + 30 <= hhmm < 14 * 60:
        status = "midday_break"
    else:
        status = "closed"
    return {
        "status": status,
        "local_time": local.strftime("%a %H:%M"),
        "timezone": "Asia/Kuala_Lumpur",
        "caveat": MARKET_CAVEAT,
    }


def halt_prompt(state: ListedIssuerState, now: datetime) -> dict:
    """What to consider about a trading halt. A prompt only: nothing here requests
    a halt, and the desk records the human decision with `record_halt`."""
    market = market_status(now)
    base = {"market": market, "basis": HALT_BASIS, "decision": state.halt.decision.value}

    def out(level: str, headline: str, steps: list[str] | None = None) -> dict:
        return {**base, "level": level, "headline": headline, "steps": steps or []}

    if state.halt.decision in (HaltDecision.REQUESTED, HaltDecision.APPROVED):
        return out("recorded", f"Halt {state.halt.decision.value}. Keep the announcement ready to release.")
    m = state.materiality
    if m is None:
        return out("none", "Run the materiality check first.")
    if m.outcome == MaterialityOutcome.NOT_MATERIAL:
        return out("none", "No halt prompt: judged not material. Re-run the check if facts change.")
    bursa = next((c for c in state.clocks if c.key == "bursa_material"), None)
    if bursa is not None and bursa.status == ClockStatus.DONE:
        return out("none", "Bursa announcement recorded as released. No halt prompt.")

    ask = [
        "Company Secretary telephones Bursa before filing, where practicable.",
        "If a halt is wanted, the authorised signatory files the request under Practice Note 2.",
        "Bursa decides; record its decision here. A halt usually runs until the announcement is out.",
    ]
    if m.outcome == MaterialityOutcome.WITHHOLD_AND_MONITOR:
        return out(
            "watch",
            "Withholding. If a leak, rumour or unusual trading appears, announce at once; a halt may be needed to announce in an orderly way.",
        )
    if market["status"] == "closed":
        return out(
            "after_hours",
            "Market is closed, so nobody can trade, but immediate disclosure still applies. Have the announcement ready before the next open and ask the Company Secretary whether a halt request is needed for the open.",
            ask,
        )
    return out(
        "consider",
        f"Material information exists and the market is {market['status'].replace('_', ' ')}. "
        "Announce immediately. If it cannot be released at once, ask the Company Secretary whether to request a trading halt.",
        ask,
    )


def record_halt(
    state: ListedIssuerState, *, decision: HaltDecision, actor: str, note: str, now: datetime
) -> None:
    if decision == HaltDecision.NONE:
        raise ListedIssuerError("record requested, approved, declined or lifted")
    cur = state.halt.decision
    allowed = {
        HaltDecision.NONE: {HaltDecision.REQUESTED},
        HaltDecision.REQUESTED: {HaltDecision.APPROVED, HaltDecision.DECLINED},
        HaltDecision.APPROVED: {HaltDecision.LIFTED},
        HaltDecision.DECLINED: {HaltDecision.REQUESTED},
        HaltDecision.LIFTED: {HaltDecision.REQUESTED},
    }
    if decision not in allowed[cur]:
        raise ListedIssuerError(f"cannot record {decision.value} after {cur.value}")
    if decision == HaltDecision.REQUESTED:
        state.halt.requested_at, state.halt.requested_by = now, actor
        state.halt.resolved_at = None
    else:
        state.halt.resolved_at = now
    state.halt.decision = decision
    state.halt.note = note


# --------------------------------------------------------------- insider lock
def add_insider(
    state: ListedIssuerState,
    *,
    name: str,
    role: str,
    told_by: str,
    told_at: datetime,
    now: datetime,
) -> InsiderEntry:
    name = name.strip()
    if not name:
        raise ListedIssuerError("name is required")
    lock = state.insider_lock
    if any(i.name.lower() == name.lower() for i in lock.insiders):
        raise ListedIssuerError(f"{name} is already on the insider list")
    entry = InsiderEntry(name=name, role=role.strip(), told_at=told_at, told_by=told_by)
    lock.insiders.append(entry)
    if not lock.active:
        lock.active, lock.started_at = True, now
        lock.released_at = lock.released_by = None
        lock.release_note = ""
    return entry


def _insider(state: ListedIssuerState, insider_id: str) -> InsiderEntry:
    for i in state.insider_lock.insiders:
        if i.id == insider_id:
            return i
    raise ListedIssuerNotFound(f"unknown insider: {insider_id}")


def mark_notice_sent(state: ListedIssuerState, insider_id: str, *, now: datetime) -> InsiderEntry:
    entry = _insider(state, insider_id)
    entry.notice_sent_at = entry.notice_sent_at or now
    return entry


def acknowledge_notice(state: ListedIssuerState, insider_id: str, *, now: datetime) -> InsiderEntry:
    entry = _insider(state, insider_id)
    if entry.notice_sent_at is None:
        raise ListedIssuerError("the notice has not been sent to this person yet")
    entry.acknowledged_at = entry.acknowledged_at or now
    return entry


def release_lock(state: ListedIssuerState, *, actor: str, note: str, now: datetime) -> dict:
    """End the restriction. Needs a written reason; reports anyone not yet
    acknowledged so the Company Secretary sees the gap rather than losing it."""
    lock = state.insider_lock
    if not lock.active:
        raise ListedIssuerError("the insider lock is not active")
    if not note.strip():
        raise ListedIssuerError("a release note is required (who told the insiders in writing, and when)")
    lock.active, lock.released_at, lock.released_by, lock.release_note = False, now, actor, note.strip()
    unacked = [i.name for i in lock.insiders if i.acknowledged_at is None]
    return {"released": True, "unacknowledged": unacked}


def insider_notice(*, company: str, code_name: str, secretary: str, channel: str, now: datetime) -> dict:
    """Do-not-trade and confidentiality notice (playbook template T6). The desk
    sends it; this only drafts it. Counsel should approve the wording first."""
    company = company.strip() or "[Company]"
    code = code_name.strip() or "____"
    sec = secretary.strip() or "[Company Secretary]"
    chan = channel.strip() or "[designated channel]"
    when = now.astimezone(KL).strftime("%d %b %Y %H:%M")
    body = (
        f"You are receiving this notice because you have, or may have, knowledge of non-public "
        f"information concerning {company} [code name: {code}].\n\n"
        f"1. Do not buy, sell or otherwise deal, directly or indirectly, including through family "
        f"members, nominees or connected persons, in securities of {company} or any related "
        f"securities until you are told in writing that this restriction has ended.\n"
        f"2. Do not disclose this information to anyone, including colleagues without a need to know, "
        f"family and friends. Do not advise or encourage anyone else to deal.\n"
        f"3. Dealing in securities, or communicating inside information, while in possession of "
        f"material non-public information may be a criminal offence under the Capital Markets and "
        f"Services Act 2007 (see s.188) and may breach the Listing Requirements.\n"
        f"4. Do not discuss this matter by personal chat, email or social media. Use only {chan}.\n"
        f"5. Please reply to confirm receipt and that you have complied with this notice.\n\n"
        f"{sec}  |  {when} (Malaysia time)"
    )
    return {
        "subject": f"STRICTLY CONFIDENTIAL: Restriction on dealing in {company} securities",
        "body": body,
        "review_note": (
            "Have counsel approve this wording before it is sent. The offence and Listing "
            "Requirements references have not been checked against the primary text."
        ),
    }


# ------------------------------------------------------- holding integration
def listed_context_for_holding(state: ListedIssuerState | None) -> str | None:
    """A line of context for the drafting model. Facts about the process only: it
    never contains the information itself."""
    if state is None or state.materiality is None:
        return None
    m = state.materiality
    lock = "active" if state.insider_lock.active else "not started"
    base = (
        f"Listed issuer ({state.market.value.upper()} Market). Materiality outcome: {m.outcome.value}. "
        f"Insider lock: {lock}. "
    )
    if m.outcome == MaterialityOutcome.ANNOUNCE_NOW:
        return base + (
            "A Bursa announcement is required and must be released BEFORE this statement. "
            "Do not call the information material or immaterial in public text."
        )
    if m.outcome == MaterialityOutcome.WITHHOLD_AND_MONITOR:
        return base + (
            "Information is being withheld under the exception. The statement must not disclose, "
            "confirm or hint at it."
        )
    return base + "No Bursa announcement is required on the current assessment."


def apply_listed_guard(brief, state: ListedIssuerState | None) -> None:
    """Deterministic post-processing, applied whatever the model wrote, so the Bursa
    rules do not depend on the model remembering them. Idempotent."""
    if state is None or state.materiality is None:
        return
    m = state.materiality
    if m.outcome == MaterialityOutcome.NOT_MATERIAL:
        return

    def add_once(items: list, value) -> None:
        key = value["action"] if isinstance(value, dict) else value
        have = [i["action"] if isinstance(i, dict) else i for i in items]
        if key not in have:
            items.append(value)

    if m.outcome == MaterialityOutcome.ANNOUNCE_NOW:
        add_once(
            brief.do_not_say,
            "Do not release or send this statement before the Bursa announcement is out. Bursa first.",
        )
        first_op = {
            "action": "Company Secretary confirms the Bursa announcement is released before this statement is sent",
            "owner_role": "ws_admin",
            "sla_hours": 1,
            "objective_ids": [],
        }
        bursa = next((c for c in state.clocks if c.key == "bursa_material"), None)
        if bursa is None or bursa.status != ClockStatus.DONE:
            add_once(brief.gaps, "Bursa announcement is not yet recorded as released")
    else:
        add_once(
            brief.do_not_say,
            "Do not disclose, confirm or hint at the withheld information in any public text.",
        )
        first_op = {
            "action": "Company Secretary watches trading and keeps the announcement ready; announce immediately on any leak, rumour or unusual trading",
            "owner_role": "ws_admin",
            "sla_hours": 1,
            "objective_ids": [],
        }
    add_once(
        brief.do_not_say,
        "Do not describe the information as material or not material in public text; that is the Company Secretary's call.",
    )
    if not state.insider_lock.active:
        add_once(brief.gaps, "Insider lock not started: tell everyone who knows not to deal and start the insider list")
    if first_op["action"] not in [o.get("action") for o in brief.ops]:
        brief.ops = [first_op, *brief.ops][:5]
