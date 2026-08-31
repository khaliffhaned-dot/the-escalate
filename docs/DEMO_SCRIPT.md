# Demo video script — ~4:00

Shot list and narration for the required demo video. Timings sum to **3:55**,
leaving headroom. Every screen referenced here has been verified working
locally at `http://127.0.0.1:8080`.

**Before you record**

```bash
uvicorn nadi.api.app:app --port 8080
```

Open `http://127.0.0.1:8080`, set the sidebar role to **WS Admin**, and have a
second terminal ready. Record at 1920×1080. Keep the browser zoom at 100% so
the bilingual panes sit side by side.

---

## 0:00–0:30 · The problem

> **Shot:** Dashboard, full screen. Let the eye land on `AT RISK` and `5/5`.

"Malaysian PR desks work inside a boundary called **3R** — Royalty, Religion,
Race. Cross it, and you're not managing a news cycle, you're managing a legal
event. The response window is a few hours, and it usually opens at 2am.

So the obvious move is an agent that monitors and responds. That move is
wrong. An agent that can publish into a 3R moment on behalf of a brand is an
unbounded liability. But an agent that waits for someone to wake up wastes the
only hours that matter."

---

## 0:30–0:55 · The value proposition

> **Shot:** Stay on Dashboard. Point at the `Barcelona 4.0 · AVE Disabled`
> badge in the header, then the PESO Ladder.

"The Escalate takes the third option. The agent does **all** the work up to the
send — and the send is structurally unreachable to it.

It also refuses to lie about results. This desk measures contribution on the
AMEC framework. It does not report AVE — Advertising Value Equivalency — a
metric the Barcelona Principles rejected in 2010. Not as a setting someone can
flip. As a value the code will not hold."

---

## 0:55–1:35 · Escalation, live

> **Shot:** Click **Mentions**. Scroll to the Telegram mention flagged
> `royalty`. Then click **War Rooms**.

"A residue post surfaces — old point-of-sale creative, still on a wall in Jalan
Imbi, carrying a line that reads on royalty. The classifier flags it 3R,
severity high.

That flag opens a war room automatically — its own queues, its own posture, its
own legal-hold state. No human triaged this. It's 2am."

---

## 1:35–2:35 · The agent drafts

> **Shot:** Click **Holdings**. Let the brief render. Move slowly here — this
> is the centrepiece. Pause on each highlighted region.

"Here's what the ADK agent produced.

Bilingual — English and Bahasa Malaysia, side by side. Not a translation
afterthought; both are first-class output.

But look at what ships *with* the statement. **Information gaps** — what the
draft deliberately refuses to claim it knows. **Do not say** — the lines that
would make this worse, including any reference to AVE, and any suggestion the
creative was directed by an authority. And **operational next steps**, each
with an owner role and an SLA in hours.

And then this line —"

> **Shot:** Zoom on the green footer:
> `Human must send · AVE disabled (Barcelona 4.0) · Auto-publish off`

"— `human must send`. That is not a label. Reaching `sent external` requires an
explicit transition from a human holding the permission. There is no code path
that advances it on its own."

---

## 2:35–3:05 · Prove the governance

> **Shot:** Sidebar role dropdown → switch **WS Admin** to **Viewer**. Try an
> action. Then switch back. Cut to terminal.

"Roles aren't cosmetic — six of them, checked by a dependency on every route,
with `org_id` on every row and Postgres row-level security underneath.

And the AVE ban holds against a direct request:"

```bash
curl -s -X POST http://127.0.0.1:8080/v1/workspaces/ws_aurora/evaluation/lock \
  -H 'X-Nadi-Role: ws_admin' -H 'Content-Type: application/json' \
  -d '{"include_ave": true}'
```

> **Shot:** Show the response.
> `{"detail":"AVE not allowed under Barcelona Principles 4.0"}` — HTTP 422.

---

## 3:05–3:35 · Architecture

> **Shot:** `docs/architecture.md` diagram, or the agent diagram alone.

"Two things make this a real agent rather than a prompt.

Its tools are **scoped by construction**. `get_mention_detail` is a closure
built per request, bound to exactly the mentions in this war room. It cannot
reach another tenant's data — not because a check would stop it, but because
those objects aren't in the closure.

And every provider path — ADK, Vertex, direct key, deterministic fallback —
converges on **one** guard implementation.

That last part is a fix, not a boast. The ADK branch used to return early and
skip those guards. Which meant the highest-priority path — the one that runs
in real deployment — was the only one with no AVE scan and no tabletop marker.
A drill could return a draft indistinguishable from a sendable statement. A
guard that lives on one branch is not a guard."

---

## 3:35–3:55 · Production readiness

> **Shot:** Terminal, `pytest -q`. Then your hosted app URL.

```bash
pytest -q
```

"Seventy-six tests, running fully offline — no credentials, so the demo path is
deterministic and can't fail live.

Gemini 3.5 Flash through Google ADK. Postgres row-level security and a
Firestore store that scopes every read by tenant at the query — you can't
reintroduce AVE by editing a row by hand, because the model re-validates on
the way out.

It drafts in the hours that matter. It just can't press send."

> **Shot:** `pytest -q` finishing green, then the Holdings view one last time.

> **Do not claim a Google Cloud deployment.** The account carries a billing
> suspension from unrelated earlier work, so there is no Cloud Run service and
> no live Firestore project. Both
> integrations are written and tested in the repo, and the Devpost story states
> the gap outright — keep the video consistent with that. Showing the code and
> the passing tests is honest; showing a console you don't have is not.

---

## Recording notes

- **Do not claim a live Gemini run you haven't recorded.** Without credentials
  the draft is stamped `nadi-brief-2026-08-local`; with them,
  `adk:gemini-3.5-flash`. If you record against the offline path, say "the
  deterministic path" rather than implying a live model call — a judge who
  reads the repo will check, and the honesty is worth more than the claim.
- The strongest 20 seconds of the video are the Holdings footer. Give it room.
- Keep the bug story in. Most submissions claim everything worked; a concrete
  architectural defect, found by execution and fixed with tests, is evidence of
  engineering judgement and reads as confidence rather than weakness.
- If you run long, cut the role-switching demo (2:35–2:50) before cutting
  anything in the Holdings section.
