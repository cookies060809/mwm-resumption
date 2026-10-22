"""Project task adapter around the *official* MentisEngine.run_sample.

No Mentis algorithm is reimplemented here. This changes the upstream task from
situated MCQ to cutoff-observation/resumption MCQ and discloses that change.
Runtime needs an independently supplied, clean, pinned official checkout plus
its dependencies and API configuration. --check never calls an LLM.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from mwm_eval.external import (  # noqa: E402
    AUDITED_COMMIT, OFFICIAL_REPOSITORY, ExternalPredictionError, UnavailableError,
    _json_loads, _observation_copy, _redact, _secret_values,
)


def checkout_status(environ=None):
    """Read-only provenance/dependency checks; no install, API request or .env read."""
    environ = os.environ if environ is None else environ
    root_text = environ.get("MWM_MENTIS_ROOT", "")
    if not root_text:
        return {"available": False, "reason": "MWM_MENTIS_ROOT is not configured"}
    root = Path(root_text).expanduser().resolve()
    required = ("mentis/engine.py", "mentis/config.py", "mentis/schema.py")
    if not root.is_dir() or any(not (root / name).is_file() for name in required):
        return {"available": False, "reason": "official Mentis checkout files are missing"}
    expected = environ.get("MWM_MENTIS_COMMIT", AUDITED_COMMIT)
    try:
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=10, check=False)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "cannot verify local official checkout revision"}
    actual = revision.stdout.strip()
    if revision.returncode or actual != expected:
        return {"available": False, "reason": "local checkout does not match required pinned commit",
                "expected_commit": expected, "actual_commit": actual if len(actual) == 40 else None}
    if dirty.returncode or dirty.stdout.strip():
        return {"available": False, "reason": "official checkout has tracked edits or could not be audited"}
    if not (environ.get("OPENAI_API_KEY") or environ.get("MWM_LLM_API_KEY")):
        return {"available": False, "reason": "OPENAI_API_KEY or MWM_LLM_API_KEY is missing",
                "commit": actual}
    if not environ.get("MWM_LLM_MODEL"):
        return {"available": False, "reason": "MWM_LLM_MODEL is required for explicit model matching",
                "commit": actual}
    return {"available": True, "reason": "checkout and environment present; engine imports still required",
            "root": str(root), "repository": OFFICIAL_REPOSITORY, "commit": actual}


def _control_text(observation, mode, max_chars):
    if mode == "original":
        return ""
    if mode == "memory":
        # Mechanical duplication only: no learned updates, gold labels or inferred mental state.
        log = []
        for item in observation["events"]:
            if item.get("goal_id") != observation["goal_id"]:
                continue
            candidate = log + [item]
            if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True)) > max_chars:
                break
            log = candidate
        return "\nMechanical persistent original-goal event log (duplicated evidence, not EC-JMF):\n" + json.dumps(log, ensure_ascii=False, sort_keys=True)
    if mode == "structured":
        return (
            "\nStructured reading headings: original goal; objective validity/feasibility; "
            "the target's accessible and understood evidence; commitment; task progress and "
            "resumption point. Do not automatically copy objective facts into target beliefs. "
            "Use the same cutoff observation above. No additional state updater is installed."
        )[:max_chars]
    raise ValueError("unsupported official-engine mode")


def observation_to_sample(observation, mode="original", control_max_chars=4000):
    obs = _observation_copy(observation)
    canonical = json.dumps(obs, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    options, mapping = [], {}
    for index, step in enumerate(obs["task_steps"], start=1):
        option_id = f"R{index:03d}"
        options.append({"option_id": option_id, "action_description": (
            f"Within the specified future horizon, the target resumes original goal {obs['goal_id']!r}; "
            f"their first action advancing a previously unfinished original-goal step is at step {step!r}."
        )})
        mapping[option_id] = ("resume", step)
    options.append({"option_id": "N", "action_description": (
        "Within the specified future horizon, the target takes no action advancing a previously "
        "unfinished original-goal step. Talking about it or returning to a location alone is not resumption."
    )})
    mapping["N"] = ("not_resume", None)
    control = _control_text(obs, mode, control_max_chars)
    story = (
        "External-observer record, truncated at the prediction cutoff. Objective events may be "
        "unknown to the target; person_access_evidence is separate. No future events are provided.\n"
        + canonical + control
    )
    # Upstream tie-breaking requires a sample_id. Use only a hash of model input,
    # never dataset IDs, family IDs, split names, annotations or future outcomes.
    sample = {
        "sample_id": "obs_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
        "modality": "text", "target_agent": obs["target_person"],
        "question": "Which candidate best describes the target's actual original-task resumption within the specified horizon?",
        "options": options,
        "story": {"text": story, "images": [], "video": None, "scene_context": ""},
    }
    return sample, mapping, {"story_chars": len(story), "control_chars": len(control),
                             "control_budget_type": "characters; token equality is NOT established"}


async def predict_with_engine(observation, engine, mode, provenance, settings_spec=None):
    """Injecting a stub engine in tests verifies this boundary, not upstream quality."""
    sample, mapping, context = observation_to_sample(
        observation, mode, int(os.environ.get("MWM_MENTIS_CONTROL_MAX_CHARS", "4000")))
    output = await engine.run_sample(sample, provenance.get("root", ""))
    result = output.get("result", {})
    stats = result.get("stats", {})
    stats = stats if isinstance(stats, dict) else {}
    if result.get("status") != "success" or result.get("prediction") not in mapping:
        # A failed final decision can still have paid-for successful earlier calls.
        # Preserve upstream accounting, while making no prediction for this sample.
        raise ExternalPredictionError("official Mentis did not return a successful mapped candidate", {
            "adapter": "project_resumption_mcq_v1", "mode": mode,
            "provenance": provenance, "settings": settings_spec or {},
            "model": (settings_spec or {}).get("model"),
            "usage": stats.get("tokens"), "llm_calls": stats.get("llm_calls"),
            "upstream_latency_ms": stats.get("latency_ms"),
            "official_stats": stats, "official_result": result,
            "usage_scope": "upstream-reported stats, including successful stages before final decision failure",
        })
    label, step = mapping[result["prediction"]]
    return {
        "resume_label": label, "resume_step": step,
        # Upstream criterion scores are branch values, not P(resume) or state posteriors.
        "p_resume": None, "conditional_step_probs": None, "state_probs": {},
        "evidence_event_ids": [],
        "reason": f"Official MentisEngine.run_sample selected candidate {result['prediction']} in project mode {mode}.",
        "metadata": {
            "adapter": "project_resumption_mcq_v1", "mode": mode,
            "task_matches_original_paper": False,
            "provenance": provenance, "settings": settings_spec or {},
            "model": (settings_spec or {}).get("model"),
            "usage": stats.get("tokens"), "llm_calls": stats.get("llm_calls"),
            "upstream_latency_ms": stats.get("latency_ms"), "context": context,
            "official_result": result,
            "probability_policy": "No conversion of branch values into invented probabilities",
        },
    }


def _load_official(status):
    root = Path(status["root"])
    sys.path.insert(0, str(root))
    try:
        configuration = importlib.import_module("mentis.config")
        module = importlib.import_module("mentis.engine")
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise UnavailableError("resolved mentis package is outside the configured official checkout")
        settings = configuration.load_settings(os.environ.get("MWM_MENTIS_CONFIG") or None)
        settings.model = os.environ["MWM_LLM_MODEL"]
        settings.max_output_tokens = int(os.environ.get("MWM_LLM_MAX_OUTPUT_TOKENS", "1024"))
        temperature = os.environ.get("MWM_LLM_TEMPERATURE", "0")
        settings.temperature = None if temperature.lower() == "null" else float(temperature)
        settings.max_retries = int(os.environ.get("MWM_LLM_MAX_RETRIES", "2"))
        settings.schema_retries = int(os.environ.get("MWM_MENTIS_SCHEMA_RETRIES", "0"))
        if settings.max_output_tokens <= 0:
            raise ValueError("output token budget must be positive")
        if os.environ.get("MWM_LLM_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.environ["MWM_LLM_API_KEY"]
        if os.environ.get("MWM_LLM_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = os.environ["MWM_LLM_BASE_URL"]
        # Constructor does not issue requests; official client is created lazily.
        engine = module.MentisEngine(settings)
        importlib.import_module("openai")
        thinking = os.environ.get("MWM_LLM_THINKING_MODE")
        if thinking:
            if thinking not in {"enabled", "disabled"}:
                raise ValueError("invalid thinking mode")
            # Provider transport settings only; retain the upstream pipeline/prompts.
            client_class = importlib.import_module("openai").AsyncOpenAI
            from types import SimpleNamespace
            provider_client = client_class(timeout=settings.request_timeout_seconds, max_retries=0)
            async def provider_create(**kwargs):
                kwargs['max_tokens'] = kwargs.pop('max_completion_tokens')
                kwargs['extra_body'] = {'thinking':{'type':thinking}}
                return await provider_client.chat.completions.create(**kwargs)
            engine.llm._client = SimpleNamespace(chat=SimpleNamespace(
                completions=SimpleNamespace(create=provider_create)))
    except (ImportError, KeyError, ValueError) as exc:
        raise UnavailableError("official dependency/configuration unavailable: " + type(exc).__name__) from None
    settings_spec = {
        "model": settings.model, "temperature": settings.temperature,
        "max_output_tokens": settings.max_output_tokens, "max_retries": settings.max_retries,
        "schema_retries": settings.schema_retries, "branch_concurrency": settings.branch_concurrency,
        "thinking_mode": os.environ.get("MWM_LLM_THINKING_MODE"),
    }
    return engine, settings_spec


def main():
    check_only = sys.argv[1:] == ["--check"]
    try:
        status = checkout_status()
        if not status["available"]:
            if check_only:
                print(json.dumps(status, ensure_ascii=False))
                return 0
            raise UnavailableError(status["reason"])
        with contextlib.redirect_stdout(sys.stderr):
            engine, settings_spec = _load_official(status)
        if check_only:
            print(json.dumps({**status, "reason": "local checkout/dependencies/configuration verified; no API call made"}))
            return 0
        observation = _json_loads(sys.stdin.read())
        mode = os.environ.get("MWM_ADAPTER_MODE", "original")
        with contextlib.redirect_stdout(sys.stderr):
            prediction = asyncio.run(predict_with_engine(observation, engine, mode, status, settings_spec))
        prediction = _redact(prediction, _secret_values({}))
        print(json.dumps(prediction, ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        # Do not expose third-party exception strings (they may contain headers/keys).
        failure = {"status": "unavailable" if isinstance(exc, UnavailableError) else "error",
                   "available": False, "reason": str(exc) if isinstance(exc, UnavailableError) else "official adapter execution failed",
                   "error_type": type(exc).__name__, "final_prediction_successful": False}
        if isinstance(exc, ExternalPredictionError):
            failure["metadata"] = exc.metadata
            failure["usage"] = exc.metadata.get("usage")
        failure = _redact(failure, _secret_values({}))
        if check_only:
            print(json.dumps(failure, ensure_ascii=False))
            return 0
        # Nonzero exit plus a structured failure envelope allows the command
        # parent to retain known usage. This object is never a prediction.
        print(json.dumps(failure, ensure_ascii=False, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
