"""Verify a Meeting Board transcript and print the evidence log.

Checks
  1. At least two AI seats posted, from at least two different vendors.
  2. Each AI seat reported a distinct, non-empty session id (separate sessions).
  3. No AI seat is a dummy (dummy runs are reported as relay tests, not as success).
  4. Every AI message has reply_to pointing at a message from someone else.
  5. Every AI seat answered another vendor's AI output >= min_round_trips times
     (1:1 -> round trips A->B->A; multi -> full rotations A->B->C->A).
  6. Vendor response ids (when present) are unique, and provenance session ids match the seat.
"""

from __future__ import annotations

from collections import Counter


def verify(t: dict, min_round_trips: int = 10) -> dict:
    parts = {p["participant_id"]: p for p in t["participants"]}
    msgs = t["messages"]
    by_id = {m["message_id"]: m for m in msgs}
    ai_msgs = [m for m in msgs if m["sender_kind"] == "ai"]
    posting_ai = {m["sender_id"] for m in ai_msgs}
    checks: list[tuple[str, bool, str]] = []

    vendors = {parts[pid]["vendor"] for pid in posting_ai}
    checks.append(("two_or_more_ai_vendors", len(vendors) >= 2, f"vendors={sorted(vendors)}"))

    sids = [parts[pid]["session_id"] for pid in posting_ai]
    checks.append(("distinct_session_ids", all(sids) and len(set(sids)) == len(sids),
                   f"session_ids={sids}"))

    dummies = [pid for pid in posting_ai if (parts[pid].get("transport") or "") == "dummy"]
    checks.append(("no_dummy_seats", not dummies,
                   "dummy seats: " + ", ".join(parts[p]["display_name"] for p in dummies) if dummies else "none"))

    bad_reply = [m["message_id"] for m in ai_msgs
                 if not m["reply_to"] or m["reply_to"] not in by_id
                 or by_id[m["reply_to"]]["sender_id"] == m["sender_id"]]
    checks.append(("every_ai_reply_targets_other_participant", not bad_reply,
                   f"bad={bad_reply}" if bad_reply else f"{len(ai_msgs)} AI messages ok"))

    # Cross-vendor input per seat: messages a seat posted in reply to another vendor's AI message.
    # 1:1  -> equals min(A->B, B->A), i.e. completed round trips.
    # multi-> number of full rotations in which every seat answered another vendor's output.
    edges = Counter()
    per_seat = Counter()
    for m in ai_msgs:
        src = by_id.get(m["reply_to"] or "")
        if src and src["sender_kind"] == "ai" and src["sender_vendor"] != m["sender_vendor"]:
            edges[(src["sender_vendor"], m["sender_vendor"])] += 1
            per_seat[m["sender_id"]] += 1
    directions = {f"{a}->{b}": n for (a, b), n in edges.items()}
    round_trips = min((per_seat.get(pid, 0) for pid in posting_ai), default=0) if len(posting_ai) >= 2 else 0
    mode = "1:1" if len(posting_ai) <= 2 else f"multi({len(posting_ai)} seats)"
    checks.append((f"cross_vendor_round_trips>={min_round_trips}", round_trips >= min_round_trips,
                   f"mode={mode} round_trips={round_trips} edges={directions}"))

    rids = [(m.get("provenance") or {}).get("vendor_response_id") for m in ai_msgs]
    rids = [r for r in rids if r]
    checks.append(("vendor_response_ids_unique", len(rids) == len(set(rids)),
                   f"{len(rids)} vendor response ids"))

    mismatched = []
    for m in ai_msgs:
        prov = m.get("provenance") or {}
        seat_sid = parts[m["sender_id"]]["session_id"]
        claimed = prov.get("reported_session_id") or prov.get("requested_session_id") or \
            prov.get("conversation") or prov.get("session_id") or prov.get("conversation_id")
        if claimed and seat_sid and claimed != seat_sid:
            mismatched.append(m["message_id"])
    checks.append(("provenance_session_matches_seat", not mismatched,
                   f"mismatched={mismatched}" if mismatched else "ok"))

    return {
        "passed": all(ok for _, ok, _ in checks),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "round_trips": round_trips,
        "mode": mode,
        "edges": directions,
    }


def render_report(t: dict, rep: dict) -> str:
    parts = {p["participant_id"]: p for p in t["participants"]}
    by_id = {m["message_id"]: m for m in t["messages"]}
    out = [f"Room {t['room']['room_id']}  \"{t['room']['title']}\"  status={t['room']['status']}", "",
           "Participants:"]
    for p in t["participants"]:
        out.append(f"  {p['participant_id']:<16} {p['kind']:<5} {p['display_name']:<14} vendor={p['vendor']:<10} "
                   f"model={p['model']}  transport={p['transport']}  session_id={p['session_id']}")
    out += ["", "Message log (seq | message_id | sender -> reply_to sender):"]
    for m in t["messages"]:
        p = parts.get(m["sender_id"], {})
        rt = by_id.get(m["reply_to"] or "")
        rt_s = f"{m['reply_to']} ({parts.get(rt['sender_id'], {}).get('display_name', '?')}/{rt['sender_vendor']})" \
            if rt else "-"
        prov = m.get("provenance") or {}
        extra = prov.get("vendor_response_id") or prov.get("reported_session_id") or ""
        out.append(f"  {m['sequence']:>3} | {m['message_id']} | {p.get('display_name', '?')}/{m['sender_vendor']:<9}"
                   f" -> {rt_s}  {extra}")
    out += ["", "Checks:"]
    for c in rep["checks"]:
        out.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    out.append("")
    out.append("RESULT: " + ("PASSED" if rep["passed"] else "NOT PASSED"))
    return "\n".join(out)
