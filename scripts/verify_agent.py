"""Did the real ADK agent run, or did it quietly fall back?

The fallback chain is deliberately silent: if the agent fails, you still get a
good deterministic draft. That is right for production and dangerous for a
demo, because the service looks healthy either way. `model_version` is the
only thing that tells them apart.

    python scripts/verify_agent.py

Reads GOOGLE_API_KEY / GEMINI_API_KEY from the environment. Prints nothing
that could expose the key.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nadi.data.seed_aurora import seed_mentions  # noqa: E402
from nadi.services.llm_holding import generate_holding_with_llm  # noqa: E402


def _mask(v: str | None) -> str:
    if not v:
        return "not set"
    return f"set ({len(v)} chars, starts {v[:3]}…)"


async def main() -> int:
    print("Credentials visible to the agent")
    print(f"  GOOGLE_API_KEY  : {_mask(os.getenv('GOOGLE_API_KEY'))}")
    print(f"  GEMINI_API_KEY  : {_mask(os.getenv('GEMINI_API_KEY'))}")
    print(f"  VERTEX mode     : {os.getenv('GOOGLE_GENAI_USE_VERTEXAI') or 'off'}")

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("\nNo key set. On Windows:")
        print("  set GOOGLE_API_KEY=your-key")
        print("Then re-run. Without one the agent cannot run and this will")
        print("report the deterministic fallback, which is expected.")

    mentions = [m for m in seed_mentions() if m.id == "mnt_tg_imbi_01"]
    print(f"\nDrafting from {mentions[0].id} "
          f"(3R: {[f.value for f in mentions[0].three_r.flags]})…\n")

    h = await generate_holding_with_llm(mentions=mentions, war_room_id=None)

    live = h.model_version.startswith("adk:")
    print(f"  model_version   : {h.model_version}")
    print(f"  human_must_send : {h.human_must_send}")
    print(f"  ave             : {h.ave}")
    print(f"  auto_publish    : {h.auto_publish}")
    print(f"  do_not_say      : {len(h.do_not_say)} item(s)")
    print(f"  ops             : {len(h.ops)} step(s)")
    print(f"\n  EN: {h.lines.get('en', '')[:150]}")
    print(f"  BM: {h.lines.get('bm', '')[:150]}")

    print()
    if live:
        print("PASS — the real ADK agent ran on Gemini. Record the demo now.")
    else:
        print("FALLBACK — this is the deterministic draft, not the agent.")
        print("The demo still works, but do not describe it as a live model")
        print("call. Re-run with a valid key set to get the agent path.")

    # The invariants must hold on either path. If these ever fail, that is
    # a real defect, not a configuration problem.
    assert h.human_must_send is True, "INVARIANT BROKEN: human_must_send"
    assert h.ave is False, "INVARIANT BROKEN: ave"
    assert h.auto_publish is False, "INVARIANT BROKEN: auto_publish"
    print("Invariants hold: human must send, no AVE, no auto-publish.")

    return 0 if live else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
