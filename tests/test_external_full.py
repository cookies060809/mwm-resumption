"""Real local protocol round trips, not real LLM/Mentis performance experiments."""

import asyncio
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from mwm_eval.external import (
    AUDITED_COMMIT, ChatCompletionBaseline, CommandBaseline,
    ExternalPredictionError, UnavailableError, make_external_baselines,
)


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "integration" / "mentis_adapter.py"
module_spec = importlib.util.spec_from_file_location("project_mentis_adapter", ADAPTER_PATH)
adapter = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(adapter)


def observation():
    return {"target_person": "worker", "goal_id": "order", "task_steps": ["pack", "ship"],
            "task_graph": {"nodes": ["pack", "ship"], "edges": [["pack", "ship"]]},
            "cutoff": 2, "horizon": {"type": "decision_opportunities", "value": 3},
            "events": [{"event_id": "e1", "time": 1, "actor": "worker", "event_type": "task_action",
                        "goal_id": "order", "step_id": "pack", "action_status": "completed",
                        "world_effect": None, "observer_evidence": "packing completed",
                        "person_access_evidence": {"status": "ACCESSED", "understood": True},
                        "source": "protocol fixture", "certainty": 1}]}


def prediction():
    return {"resume_label": "resume", "resume_step": "ship", "p_resume": 0.7,
            "conditional_step_probs": {"pack": 0.1, "ship": 0.9}, "state_probs": {},
            "evidence_event_ids": ["e1"], "reason": "protocol fixture", "metadata": {}}


class LocalEndpoint:
    def __init__(self, responses):
        self.responses = list(responses)
        self.received = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                owner.received.append({"path": self.path, "payload": json.loads(payload),
                                       "authorization_present": bool(self.headers.get("Authorization"))})
                code, response_body = owner.responses.pop(0)
                raw = response_body if isinstance(response_body, str) else json.dumps(response_body)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw.encode("utf-8"))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def config(self):
        return {"enabled": True, "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
                "model": "local-protocol-fixture", "require_api_key": False,
                "max_retries": 1, "retry_delay_seconds": 0, "max_output_tokens": 200,
                "temperature": 0}


def completion(content=None):
    return {"id": "local-fixture-id", "model": "local-protocol-fixture",
            "choices": [{"message": {"content": content if content is not None else json.dumps(prediction())}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50}}


class ExternalIntegrationTests(unittest.TestCase):
    def test_unconfigured_registry_is_explicitly_unavailable(self):
        methods = make_external_baselines({})
        self.assertEqual(set(methods), {"B2", "B3", "B8", "B9", "B10", "MENTIS_STRUCTURED"})
        for method in methods.values():
            self.assertFalse(method.availability()["available"])
            with self.assertRaises(UnavailableError):
                method.predict(observation())

    def test_real_local_http_roundtrip_usage_and_input_only(self):
        with LocalEndpoint([(200, completion())]) as endpoint:
            model = ChatCompletionBaseline("B2", endpoint.config())
            model.fit([(observation(), {"gold": "TRAIN_LABEL_MUST_NOT_LEAK"})])
            result = model.predict(observation())
            self.assertEqual(result["resume_step"], "ship")
            metadata = result["metadata"]["external"]
            self.assertEqual(metadata["usage"]["total_tokens"], 50)
            self.assertGreaterEqual(metadata["latency_ms"], 0)
            self.assertEqual(metadata["retries"], 0)
            request_data = endpoint.received[0]
            self.assertEqual(request_data["path"], "/v1/chat/completions")
            self.assertNotIn("TRAIN_LABEL_MUST_NOT_LEAK", json.dumps(request_data))
            self.assertEqual(json.loads(request_data["payload"]["messages"][1]["content"]), observation())

    def test_b2_b3_identical_model_budget_and_observation(self):
        with LocalEndpoint([(200, completion()), (200, completion())]) as endpoint:
            methods = make_external_baselines({"llm": endpoint.config()})
            for method_id in ("B2", "B3"):
                methods[method_id].predict(observation())
            left, right = [item["payload"] for item in endpoint.received]
            for name in ("model", "temperature", "max_completion_tokens", "response_format"):
                self.assertEqual(left[name], right[name])
            self.assertEqual(left["messages"][1], right["messages"][1])
            self.assertNotEqual(left["messages"][0], right["messages"][0])

    def test_unsupported_http_seed_is_a_repeat_label_not_a_controlled_seed(self):
        with LocalEndpoint([(200, completion())]) as endpoint:
            cfg = endpoint.config()
            cfg["seed"] = 999
            model = make_external_baselines({"run_seed": 12, "llm": cfg})["B2"]
            result = model.predict(observation())
            self.assertNotIn("seed", endpoint.received[0]["payload"])
            self.assertEqual(model.spec()["requested_seed"], 12)
            self.assertEqual(model.spec()["seed_control"], "unsupported_repeat_only")
            self.assertEqual(result["metadata"]["external"]["seed_control"], "unsupported_repeat_only")

    def test_supported_http_seed_is_forwarded_without_determinism_claim(self):
        with LocalEndpoint([(200, completion())]) as endpoint:
            cfg = {**endpoint.config(), "supports_seed": True, "seed": 999}
            model = make_external_baselines({"run_seed": 0, "llm": cfg})["B3"]
            result = model.predict(observation())
            self.assertEqual(endpoint.received[0]["payload"]["seed"], 0)
            self.assertEqual(model.spec()["requested_seed"], 0)
            self.assertEqual(model.spec()["seed_control"], "requested_not_verified")
            self.assertFalse(result["metadata"]["external"]["determinism_guaranteed"])

    def test_http_prediction_contract_failure_retains_known_paid_usage(self):
        invalid = prediction()
        invalid["p_resume"] = 1.4
        with LocalEndpoint([(200, completion(json.dumps(invalid)))]) as endpoint:
            with self.assertRaises(ExternalPredictionError) as raised:
                ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
            self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 50)
            self.assertEqual(raised.exception.metadata["n_usage_known_attempts"], 1)

    def test_http_json_decoding_failure_retains_known_paid_usage(self):
        with LocalEndpoint([(200, completion("not JSON"))]) as endpoint:
            with self.assertRaises(ExternalPredictionError) as raised:
                ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
            self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 50)

    def test_reported_http_failure_usage_is_counted_with_retry_response(self):
        failed = {"error": "protocol failure", "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}
        with LocalEndpoint([(500, failed), (200, completion())]) as endpoint:
            result = ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
            external = result["metadata"]["external"]
            self.assertEqual(external["usage"]["total_tokens"], 55)
            self.assertEqual(external["response_usage"]["total_tokens"], 50)
            self.assertEqual(external["n_usage_known_attempts"], 2)
            self.assertEqual(external["n_usage_unknown_attempts"], 0)

    def test_retry_http_429_and_record_real_attempts(self):
        with LocalEndpoint([(429, {"error": "busy"}), (200, completion())]) as endpoint:
            result = ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
            self.assertEqual(result["metadata"]["external"]["retries"], 1)
            self.assertEqual(len(endpoint.received), 2)

    def test_http_error_body_and_secret_do_not_leak(self):
        secret = "protocol-fixture-secret-never-log"
        with patch.dict(os.environ, {"MWM_LLM_API_KEY": secret}):
            with LocalEndpoint([(401, {"error": secret})]) as endpoint:
                model = ChatCompletionBaseline("B2", endpoint.config())
                with self.assertRaises(ExternalPredictionError) as raised:
                    model.predict(observation())
                self.assertNotIn(secret, str(raised.exception))
                self.assertNotIn(secret, json.dumps(raised.exception.metadata))
                self.assertTrue(endpoint.received[0]["authorization_present"])
                self.assertEqual(len(endpoint.received), 1)
                self.assertNotIn(secret, json.dumps(model.spec()))

    def test_response_raw_output_redacts_accidentally_echoed_key(self):
        secret = "protocol-fixture-key-echo"
        pred = prediction()
        pred["reason"] = secret
        with patch.dict(os.environ, {"MWM_LLM_API_KEY": secret}):
            with LocalEndpoint([(200, completion(json.dumps(pred)))]) as endpoint:
                result = ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
                self.assertNotIn(secret, json.dumps(result))
                self.assertIn("REDACTED", json.dumps(result))

    def test_json_fences_duplicates_and_nan_are_rejected(self):
        bad_outputs = ['```json\n{}\n```', '{"p_resume":0.2,"p_resume":0.9}', '{"p_resume":NaN}', '{"p_resume":1e999}']
        for text in bad_outputs:
            with self.subTest(text=text), LocalEndpoint([(200, completion(text))]) as endpoint:
                with self.assertRaises(ExternalPredictionError):
                    ChatCompletionBaseline("B2", endpoint.config()).predict(observation())
                self.assertEqual(len(endpoint.received), 1)

    def test_observation_with_gold_or_sample_id_rejected_before_request(self):
        with LocalEndpoint([]) as endpoint:
            model = ChatCompletionBaseline("B2", endpoint.config())
            for field in ("sample_id", "gold", "resume_label"):
                obs = observation()
                obs[field] = "forbidden"
                with self.assertRaises(ValueError):
                    model.predict(obs)
            self.assertEqual(endpoint.received, [])

    def test_future_or_nested_annotation_rejected_before_request(self):
        with LocalEndpoint([]) as endpoint:
            model = ChatCompletionBaseline("B2", endpoint.config())
            future = observation()
            future["events"][0]["time"] = 99
            with self.assertRaises(ValueError):
                model.predict(future)
            nested = observation()
            nested["events"][0]["gold"] = "future_answer"
            with self.assertRaises(ValueError):
                model.predict(nested)
            self.assertEqual(endpoint.received, [])

    def test_mentis_cannot_be_instantiated_as_a_direct_chat_baseline(self):
        with self.assertRaises(ValueError):
            ChatCompletionBaseline("B9", {})

    def test_real_command_roundtrip_and_mode_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stub.py"
            path.write_text(
                "import json,os,sys\nobs=json.load(sys.stdin)\np=" + repr(prediction()) + "\n"
                "p['metadata']={'observed_fields':sorted(obs),'mode':os.environ['MWM_ADAPTER_MODE']}\n"
                "print(json.dumps(p))\n", encoding="utf-8")
            cfg = {"enabled": True, "argv": [sys.executable, str(path)],
                   "provenance": {"repository": "protocol-fixture-not-official", "commit": "fixture"}}
            model = CommandBaseline("B9", cfg)
            result = model.predict(observation())
            self.assertEqual(result["metadata"]["mode"], "memory")
            self.assertEqual(result["metadata"]["observed_fields"], sorted(observation()))
            self.assertTrue(result["metadata"]["external"]["real_child_process_execution"])

    def test_command_seed_only_forwarded_when_adapter_declares_support(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "seed_stub.py"
            path.write_text(
                "import json,os,sys\njson.load(sys.stdin)\np=" + repr(prediction()) + "\n"
                "p['metadata']={'received_seed':os.environ.get('MWM_SEED')}\nprint(json.dumps(p))\n",
                encoding="utf-8")
            for supports_seed in (False, True):
                cfg = {"enabled": True, "argv": [sys.executable, str(path)], "supports_seed": supports_seed}
                with patch.dict(os.environ, {"MWM_SEED": "unrelated-parent-seed"}):
                    model = make_external_baselines({"run_seed": 23, "commands": {"B10": cfg}})["B10"]
                    result = model.predict(observation())
                self.assertEqual(result["metadata"]["received_seed"], "23" if supports_seed else None)
                self.assertEqual(model.spec()["requested_seed"], 23)
                self.assertEqual(model.spec()["seed_control"], "requested_not_verified" if supports_seed else "unsupported_repeat_only")

    def test_command_nonzero_exit_retains_reported_usage(self):
        failed = {"error": "upstream failure", "metadata": {"usage": {"total_tokens": 91}}}
        cfg = {"enabled": True, "argv": [sys.executable, "-c",
               "import json,sys; print(json.dumps(" + repr(failed) + ")); sys.exit(8)"]}
        with self.assertRaises(ExternalPredictionError) as raised:
            CommandBaseline("B10", cfg).predict(observation())
        self.assertEqual(raised.exception.metadata["returncode"], 8)
        self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 91)

    def test_command_invalid_prediction_retains_reported_usage(self):
        invalid = prediction()
        invalid["metadata"]["usage"] = {"total_tokens": 92}
        invalid["resume_step"] = "nonexistent_step"
        cfg = {"enabled": True, "argv": [sys.executable, "-c",
               "import json; print(json.dumps(" + repr(invalid) + "))"]}
        with self.assertRaises(ExternalPredictionError) as raised:
            CommandBaseline("B10", cfg).predict(observation())
        self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 92)

    def test_command_timeout_retains_complete_already_reported_usage(self):
        reported = {"metadata": {"usage": {"total_tokens": 93}}}
        cfg = {"enabled": True, "timeout_seconds": 0.5,
               "argv": [sys.executable, "-c", "import json,time; print(json.dumps(" + repr(reported) + "),flush=True); time.sleep(10)"]}
        with self.assertRaises(ExternalPredictionError) as raised:
            CommandBaseline("B10", cfg).predict(observation())
        self.assertEqual(raised.exception.metadata["error_type"], "TimeoutExpired")
        self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 93)

    def test_command_stderr_redaction_and_failure_capture(self):
        secret = "protocol-secret-child-stderr"
        cfg = {"enabled": True, "argv": [sys.executable, "-c",
               "import os,sys; print(os.environ['MWM_LLM_API_KEY'],file=sys.stderr); sys.exit(7)"]}
        with patch.dict(os.environ, {"MWM_LLM_API_KEY": secret}):
            with self.assertRaises(ExternalPredictionError) as raised:
                CommandBaseline("B10", cfg).predict(observation())
            self.assertEqual(raised.exception.metadata["returncode"], 7)
            self.assertNotIn(secret, json.dumps(raised.exception.metadata))

    def test_command_timeout_is_a_failure_without_prediction(self):
        cfg = {"enabled": True, "argv": [sys.executable, "-c", "import time; time.sleep(10)"],
               "timeout_seconds": 0.1}
        with self.assertRaises(ExternalPredictionError) as raised:
            CommandBaseline("B10", cfg).predict(observation())
        self.assertEqual(raised.exception.metadata["error_type"], "TimeoutExpired")

    def test_command_non_json_stdout_is_not_silently_repaired(self):
        cfg = {"enabled": True, "argv": [sys.executable, "-c", "print('log line before {}')"]}
        with self.assertRaises(ExternalPredictionError):
            CommandBaseline("B10", cfg).predict(observation())

    def test_b9_and_structured_inherit_same_official_command(self):
        base = {"enabled": False, "argv": ["official-wrapper"], "cwd": "official-root",
                "provenance": {"repository": "official", "commit": AUDITED_COMMIT}}
        methods = make_external_baselines({"commands": {"B8": base,
                    "B9": {"argv": ["fake-direct-llm"]}, "MENTIS_STRUCTURED": {}}})
        for method_id, mode in (("B9", "memory"), ("MENTIS_STRUCTURED", "structured")):
            self.assertEqual(methods[method_id].config["argv"], base["argv"])
            self.assertEqual(methods[method_id].config["mode"], mode)
            self.assertEqual(methods[method_id].config["provenance"], base["provenance"])

    def test_ablations_are_references_not_fake_models(self):
        model = make_external_baselines({"ablations": {"A0": "member_A/full.json"}})["B10"]
        entries = model.spec()["ablations"]
        self.assertEqual(set(entries), {f"A{x}" for x in range(8)})
        self.assertEqual(entries["A0"]["config_path"], "member_A/full.json")
        self.assertEqual(entries["A1"]["status"], "awaiting_A_implementation")
        self.assertFalse(model.availability()["available"])

    def test_mentis_task_conversion_fixed_candidates_and_input_hash_id(self):
        sample, mapping, metadata = adapter.observation_to_sample(observation())
        self.assertEqual(mapping, {"R001": ("resume", "pack"), "R002": ("resume", "ship"), "N": ("not_resume", None)})
        self.assertNotIn("answer", sample)
        self.assertTrue(sample["sample_id"].startswith("obs_"))
        self.assertIn('"person_access_evidence"', sample["story"]["text"])
        self.assertEqual(metadata["control_chars"], 0)
        repeated = adapter.observation_to_sample(deepcopy(observation()))[0]
        self.assertEqual(sample["sample_id"], repeated["sample_id"])

    def test_mentis_engine_boundary_calls_run_sample_and_does_not_invent_probabilities(self):
        class StubEngine:
            async def run_sample(self, record, base_dir):
                self.record = record
                return {"result": {"status": "success", "prediction": "R002",
                                   "stats": {"tokens": {"total_tokens": 70}, "llm_calls": 8}}}

        engine = StubEngine()
        result = asyncio.run(adapter.predict_with_engine(observation(), engine, "memory", {"commit": "fixture"}))
        self.assertEqual(result["resume_step"], "ship")
        self.assertIsNone(result["p_resume"])
        self.assertIsNone(result["conditional_step_probs"])
        self.assertEqual(result["state_probs"], {})
        self.assertEqual(result["metadata"]["usage"]["total_tokens"], 70)
        self.assertNotIn("answer", engine.record)
        self.assertIn("Mechanical persistent", engine.record["story"]["text"])

    def test_mentis_failed_final_decision_preserves_prior_successful_stage_usage(self):
        class FailedStubEngine:
            async def run_sample(self, record, base_dir):
                return {"result": {"status": "failed", "prediction": "",
                                   "error_type": "BranchExecutionError",
                                   "stats": {"tokens": {"total_tokens": 131}, "llm_calls": 3, "latency_ms": 123.0}}}

        with self.assertRaises(ExternalPredictionError) as raised:
            asyncio.run(adapter.predict_with_engine(observation(), FailedStubEngine(), "original", {"commit": "fixture"}))
        self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 131)
        self.assertEqual(raised.exception.metadata["llm_calls"], 3)
        self.assertEqual(raised.exception.metadata["official_stats"]["latency_ms"], 123.0)

    def test_real_adapter_failure_envelope_roundtrip_retains_usage_and_redacts_secret(self):
        # Only the engine/checkout boundary is stubbed. Execute the real adapter
        # main in a child and read its nonzero-exit envelope via CommandBaseline.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "failed_official_boundary_stub.py"
            path.write_text(
                "import os,sys\nsys.path.insert(0," + repr(str(ROOT)) + ")\n"
                "from integration import mentis_adapter as adapter\n"
                "class FailedEngine:\n"
                "    async def run_sample(self, record, base_dir):\n"
                "        return {'result':{'status':'failed','prediction':'',"
                "'error_message':os.environ['MWM_LLM_API_KEY'],"
                "'stats':{'tokens':{'total_tokens':132},'llm_calls':4}}}\n"
                "adapter.checkout_status=lambda:{'available':True,'root':'fixture','commit':'fixture'}\n"
                "adapter._load_official=lambda status:(FailedEngine(),{'model':'protocol-fixture'})\n"
                "sys.exit(adapter.main())\n", encoding="utf-8")
            cfg = {"enabled": True, "argv": [sys.executable, str(path)], "mode": "original"}
            secret = "protocol-fixture-official-failure-secret"
            with patch.dict(os.environ, {"MWM_LLM_API_KEY": secret}):
                with self.assertRaises(ExternalPredictionError) as raised:
                    CommandBaseline("B10", cfg).predict(observation())
            self.assertEqual(raised.exception.metadata["returncode"], 2)
            self.assertIsNotNone(raised.exception.metadata["usage"], raised.exception.metadata)
            self.assertEqual(raised.exception.metadata["usage"]["total_tokens"], 132)
            envelope = json.loads(raised.exception.metadata["raw_output"])
            self.assertEqual(envelope["status"], "error")
            self.assertEqual(envelope["metadata"]["llm_calls"], 4)
            self.assertNotIn(secret, json.dumps(raised.exception.metadata))
            self.assertNotIn("resume_label", envelope)

    def test_missing_official_checkout_check_is_read_only_and_unavailable(self):
        with patch.dict(os.environ, {"MWM_MENTIS_ROOT": ""}):
            result = subprocess.run([sys.executable, str(ADAPTER_PATH), "--check"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["available"])


if __name__ == "__main__":
    unittest.main()
