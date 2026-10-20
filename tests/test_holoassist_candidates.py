import copy
import unittest

from mwm_eval.holoassist_candidates import extract_candidates


class HoloCandidateTests(unittest.TestCase):
    def setUp(self):
        self.session = {"video_name": "anonymous-session", "taskType": "setup device",
            "videoMetadata": {"duration": {"seconds": 50}}, "events": [
                {"id": 1, "label": "Narration", "start": 0, "end": 50,
                 "attributes": {"Long form description": "FUTURE_SECRET"}},
                {"id": 2, "label": "Fine grained action", "start": 1, "end": 2,
                 "attributes": {"Action Correctness": "Wrong Action, corrected by instructor verbally",
                                "Incorrect Action Corrected by": "3", "Verb": "press", "Noun": "button"}},
                {"id": 3, "label": "Conversation", "start": 3, "end": 4,
                 "attributes": {"Transcription": "use the other button"}},
                {"id": 4, "label": "Fine grained action", "start": 5, "end": 6,
                 "attributes": {"Action Correctness": "Correct Action", "Verb": "press", "Noun": "other_button"}}
            ]}

    def test_correction_link_sets_cutoff_but_does_not_supply_gold(self):
        candidates, counts = extract_candidates([self.session])
        candidate = candidates[0]
        self.assertEqual(candidate["cutoff_seconds"], 4)
        self.assertEqual(candidate["outcome_audit"]["candidate_first_future_action"]["event_id"], "4")
        self.assertEqual(candidate["gold"]["resume_label"], "unknown")
        self.assertTrue(all(e["end"] <= 4 for e in candidate["input_events"]))
        self.assertEqual(counts["selected_candidates"], 1)
        self.assertNotIn("Action Correctness", str(candidate["input_events"]))
        self.assertNotIn("FUTURE_SECRET", str(candidate["input_events"]))

    def test_missing_future_and_incomplete_window_do_not_create_negative(self):
        self.session["events"].pop()
        self.session["videoMetadata"]["duration"]["seconds"] = 8
        candidate = extract_candidates([self.session])[0][0]
        self.assertFalse(candidate["outcome_audit"]["window_complete"])
        self.assertEqual(candidate["gold"]["resume_label"], "unknown")
        self.assertIsNone(candidate["outcome_audit"]["candidate_first_future_action"])

    def test_unknown_corrector_is_reported_not_replaced_by_nearest_utterance(self):
        self.session["events"][1]["attributes"]["Incorrect Action Corrected by"] = "999"
        candidates, summary = extract_candidates([self.session])
        self.assertEqual(candidates, [])
        self.assertEqual(summary["exclusions"]["missing_corrector_event_reference"], 1)

    def test_future_content_cannot_change_cutoff_input(self):
        original = extract_candidates([self.session])[0][0]
        changed = copy.deepcopy(self.session)
        changed["events"][-1]["attributes"]["Noun"] = "FUTURE_SECRET"
        altered = extract_candidates([changed])[0][0]
        self.assertEqual(original["input_events"], altered["input_events"])
        self.assertNotEqual(original["outcome_audit"], altered["outcome_audit"])


if __name__ == "__main__":
    unittest.main()
