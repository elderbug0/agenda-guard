"""Run the analyzer over eval/cases.jsonl and measure accuracy.

Usage (from the project root):  python -m eval.run_eval

Needs OPENAI_API_KEY in .env. Each case is a transcript snippet with the expected status.
Cases use DEFAULT_AGENDA unless they carry their own "agenda" list.
The number to watch is FALSE ALARMS (on_track / moved_on predicted as off_track): that is
the mistake that makes people hate the bot.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analyzer import analyze, close_client  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import AgendaItem, Session  # noqa: E402

DEFAULT_AGENDA = [
    {"id": "item-1", "title": "Q3 roadmap", "description": "Which features ship in Q3 and in what order", "minutes": 20},
    {"id": "item-2", "title": "Hiring plan", "description": "Open engineering roles, interview process, headcount", "minutes": 15},
    {"id": "item-3", "title": "Budget review", "description": "Marketing and infrastructure spend for next quarter", "minutes": 10},
]


def load_cases(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


async def run() -> int:
    if not settings.OPENAI_API_KEY:
        print("Set OPENAI_API_KEY in .env first.")
        return 2
    cases = load_cases(Path(__file__).with_name("cases.jsonl"))
    if not cases:
        print("eval/cases.jsonl is empty.")
        return 2

    correct = false_alarms = missed = 0
    print(f"Model: {settings.ANALYZER_MODEL}  |  {len(cases)} cases\n")
    for case in cases:
        agenda = [AgendaItem(**item) for item in case.get("agenda", DEFAULT_AGENDA)]
        session = Session(
            id=case["id"],
            meeting_url="eval",
            agenda=agenda,
            current_item_id=case.get("current_item_id", agenda[0].id),
        )
        result = await analyze(session, case["transcript"])
        expected = case["expected_status"]
        ok = result["status"] == expected
        if ok and expected == "moved_on":
            ok = result["matched_item_id"] == case.get("expected_item_id")
        correct += ok
        if not ok and result["status"] == "off_track":
            false_alarms += 1
        if not ok and expected == "off_track":
            missed += 1
        mark = "PASS" if ok else "FAIL"
        print(f"{mark}  {case['id']:<26} expected={expected:<9} got={result['status']:<9} "
              f"conf={result['confidence']:.2f}  {result['reason']}")

    print(f"\nAccuracy: {correct}/{len(cases)} ({correct / len(cases):.0%})")
    print(f"False alarms (flagged off-track wrongly): {false_alarms}")
    print(f"Missed drift (off-track not flagged):      {missed}")
    await close_client()
    return 0 if correct == len(cases) else 1


if __name__ == "__main__":
    started = time.time()
    code = asyncio.run(run())
    print(f"Done in {time.time() - started:.1f}s")
    sys.exit(code)
