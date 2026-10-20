"""Evidence-linked HoloAssist candidates, deliberately not automatic P1 gold."""

import hashlib
import math
import re
from collections import Counter


def _time(event, key):
    value = event.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("annotation event requires finite start/end seconds")
    return float(value)


def _input_event(event):
    attrs = event.get("attributes", {})
    common = {"event_id": str(event["id"]), "start": _time(event, "start"),
              "end": _time(event, "end"), "person_access": "UNCERTAIN"}
    if event["label"] == "Fine grained action":
        common.update(kind="action", actor="performer", person_access="ACCESSED",
                      content={key: attrs.get(key) for key in ("Verb", "Noun", "Adjective", "adverbial")})
    elif event["label"] == "Conversation":
        common.update(kind="utterance", actor="unspecified",
                      content={"text": attrs.get("Transcription"),
                               "purpose": attrs.get("Conversation Purpose"),
                               "confidence": attrs.get("Transcription Confidence")})
    else:
        return None
    # Full-session narration and post-hoc correctness/corrector attributes are
    # intentionally absent, even if their action starts before the cutoff.
    return common


def extract_candidates(sessions, max_candidates=30, horizon_seconds=30.0):
    if max_candidates <= 0 or not math.isfinite(horizon_seconds) or horizon_seconds <= 0:
        raise ValueError("positive candidate limit and finite horizon required")
    candidates, exclusions = [], Counter()
    total_wrong = total_linked = 0
    for session in sessions:
        events = session.get("events", [])
        by_id = {str(event["id"]): event for event in events}
        if len(by_id) != len(events):
            raise ValueError("duplicate source event ID within session")
        duration = float(session["videoMetadata"]["duration"]["seconds"])
        session_hash = hashlib.sha256(str(session["video_name"]).encode()).hexdigest()[:16]
        session_count = 0
        for mistake in sorted(events, key=lambda event: (_time(event, "start"), str(event["id"]))):
            attrs = mistake.get("attributes", {})
            correctness = str(attrs.get("Action Correctness", ""))
            if mistake["label"] != "Fine grained action" or not correctness.startswith("Wrong Action"):
                continue
            total_wrong += 1
            refs = re.findall(r"\d+", str(attrs.get("Incorrect Action Corrected by", "")))
            linked = [by_id[ref] for ref in refs if ref in by_id]
            if not linked:
                exclusions["missing_corrector_event_reference"] += 1
                continue
            anchor = max(linked, key=lambda event: _time(event, "end"))
            cutoff = _time(anchor, "end")
            if cutoff < _time(mistake, "start") or cutoff > duration:
                exclusions["corrector_time_not_usable"] += 1
                continue
            total_linked += 1
            if session_count >= 2 or len(candidates) >= max_candidates:
                exclusions["pilot_sampling_limit"] += 1
                continue
            input_events = []
            for event in sorted(events, key=lambda event: (_time(event, "start"), str(event["id"]))):
                if _time(event, "end") <= cutoff:
                    mapped = _input_event(event)
                    if mapped:
                        input_events.append(mapped)
            future = [event for event in events if event["label"] == "Fine grained action"
                      and cutoff < _time(event, "start") <= cutoff + horizon_seconds]
            future.sort(key=lambda event: _time(event, "start"))
            candidates.append({
                "candidate_id": f"holo_{session_hash}_{mistake['id']}",
                "stage": "unreviewed_source_candidate", "source_session_sha256_prefix": session_hash,
                "task_type": session.get("taskType"), "cutoff_seconds": cutoff,
                "horizon_seconds": horizon_seconds, "input_events": input_events,
                "outcome_audit": {"mistake_event_id": str(mistake["id"]),
                                  "corrector_event_ids": refs, "correctness_annotation": correctness,
                                  "window_complete": duration >= cutoff + horizon_seconds,
                                  "future_action_event_ids": [str(event["id"]) for event in future],
                                  "candidate_first_future_action": _input_event(future[0]) if future else None},
                "review_required": ["was the original goal actually suspended?",
                                    "which task steps and dependency graph are evidenced?",
                                    "does a future action advance an unfinished original-goal step?",
                                    "what evidence establishes perception, understanding or commitment?"],
                "gold": {"resume_label": "unknown", "resume_step": None,
                         "B": "UNKNOWN", "C": "UNKNOWN", "Q": "UNKNOWN"}})
            session_count += 1
    summary = {"source_sessions_inspected": len(sessions), "wrong_action_annotations": total_wrong,
               "wrong_actions_with_usable_corrector_link": total_linked,
               "selected_candidates": len(candidates), "exclusions": dict(exclusions),
               "selected_task_types": dict(Counter(c["task_type"] for c in candidates)),
               "complete_candidate_windows": sum(c["outcome_audit"]["window_complete"] for c in candidates),
               "source_session_count_selected": len({c["source_session_sha256_prefix"] for c in candidates}),
               "scope": "annotation-based correction candidates; no validated task-resumption labels",
               "sampling": "source prefix, at most two candidates per session, fixed 30-second window"}
    return candidates, summary
