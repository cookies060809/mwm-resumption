"""Explicit external integrations. An absent dependency never becomes a fake score.

Only B2/B3 use a direct chat call. B8/B9/MENTIS_STRUCTURED require an explicitly
installed task adapter around official Mentis; B10 requires member A's model.
The caller validates observations and canonical predictions against the contract.
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib import error, parse, request


OFFICIAL_REPOSITORY = "https://github.com/mental-world/Mentis"
AUDITED_COMMIT = "7c6ea55e007a64233c3a0f987b6d229476f3fdf6"
OBSERVATION_FIELDS = {
    "target_person", "goal_id", "task_steps", "cutoff", "horizon", "events",
    "task_graph",
}
REQUIRED_OBSERVATION_FIELDS = OBSERVATION_FIELDS
MODES = {"B8": "original", "B9": "memory", "MENTIS_STRUCTURED": "structured", "B10": "full"}
ABLATIONS = {
    "A0": "complete ECR-MWM",
    "A1": "remove information-access gating",
    "A2": "remove joint commitment/progress update",
    "A3": "remove persistent goal memory",
    "A4": "remove event consistency loss",
    "A5": "remove resumption-step auxiliary task",
    "A6": "replace learned gate with a rule gate",
    "A7": "matched history-summary/prompt-token control",
}


class UnavailableError(RuntimeError):
    """The real dependency/configuration has not been supplied."""


class ExternalPredictionError(RuntimeError):
    """Real transport, child process or response decoding failed."""

    def __init__(self, message, metadata=None):
        super().__init__(message)
        self.metadata = metadata or {}


def _json_loads(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out

    def constant(value):
        raise ValueError("non-finite JSON number")

    def number(value):
        out = float(value)
        if not math.isfinite(out):
            raise ValueError("non-finite JSON number")
        return out

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def _observation_copy(observation):
    if not isinstance(observation, dict):
        raise ValueError("predict accepts an observation object, never a dataset record")
    fields = set(observation)
    if not REQUIRED_OBSERVATION_FIELDS <= fields or fields - OBSERVATION_FIELDS:
        raise ValueError("observation fields do not match the contract; IDs/gold are not accepted")
    from .schema import validate_observation
    validate_observation(observation)
    # Serializing here also rejects NaN before anything leaves the process.
    return _json_loads(json.dumps(observation, ensure_ascii=False, allow_nan=False))


def _redact(value, secrets=()):
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if re.search(r"api[_-]?key|authorization|secret|password", str(key), re.I)
                  else _redact(item, secrets))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        result = value
        for secret in secrets:
            if secret:
                result = result.replace(secret, "[REDACTED]")
        result = re.sub(r"Bearer\s+[^\s\"']+", "Bearer [REDACTED]", result, flags=re.I)
        return result
    return value


def _secret_values(config):
    names = {config.get("api_key_env", "MWM_LLM_API_KEY"), "MWM_LLM_API_KEY", "OPENAI_API_KEY"}
    names.update(config.get("redact_env_names", []))
    return tuple(os.environ[name] for name in names if name and os.environ.get(name))


def _seed_details(config, transport):
    """A requested upstream seed is not proof of deterministic execution."""
    supported = config.get("supports_seed", False)
    if type(supported) is not bool:
        raise ValueError("supports_seed must be a boolean")
    requested = config.get("requested_seed", config.get("seed"))
    if requested is not None and type(requested) is not int:
        raise ValueError("requested seed must be an integer or null")
    effective = requested if supported else None
    return {
        "requested_seed": requested,
        "supports_seed": supported,
        "seed_control": ("requested_not_verified" if effective is not None else
                         "unsupported_repeat_only" if not supported else "not_requested"),
        "seed_parameter": ("seed" if transport == "http" else "MWM_SEED") if effective is not None else None,
        "effective_seed_requested": effective,
        "determinism_guaranteed": False,
    }


def _reported_usage(payload):
    """Read provider/adapter usage only; never estimate tokens from characters."""
    if not isinstance(payload, dict):
        return None
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    external = metadata.get("external")
    external = external if isinstance(external, dict) else {}
    official = metadata.get("official_result")
    official = official if isinstance(official, dict) else {}
    stats = official.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    for candidate in (payload.get("usage"), metadata.get("usage"), external.get("usage"), stats.get("tokens")):
        if isinstance(candidate, dict) and candidate:
            return copy.deepcopy(candidate)
    return None


def _usage_accounting(attempt_usages):
    """Sum known counters, retaining full per-attempt responses separately."""
    known = [usage for usage in attempt_usages if isinstance(usage, dict) and usage]
    aggregate = None
    if len(known) == 1:
        aggregate = copy.deepcopy(known[0])
    elif known:
        aggregate = {}
        for usage in known:
            for key, value in usage.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                    aggregate[key] = aggregate.get(key, 0) + value
    return {
        "usage": aggregate,
        "attempt_usage": copy.deepcopy(attempt_usages),
        "n_usage_known_attempts": len(known),
        "n_usage_unknown_attempts": len(attempt_usages) - len(known),
        "usage_scope": "sum of available provider-reported usage across attempts; unreported attempts remain unknown",
    }


def _attach_metadata(prediction, external_metadata, secrets):
    external_metadata = _redact(external_metadata, secrets)
    if not isinstance(prediction, dict):
        raise ExternalPredictionError("external prediction must be a JSON object", external_metadata)
    result = _redact(copy.deepcopy(prediction), secrets)
    existing = result.get("metadata", {})
    if not isinstance(existing, dict):
        raise ExternalPredictionError("prediction metadata must be an object", external_metadata)
    existing["external"] = _redact(external_metadata, secrets)
    result["metadata"] = existing
    return result


def _validated_prediction(prediction, observation, external_metadata, secrets):
    result = _attach_metadata(prediction, external_metadata, secrets)
    from .schema import validate_prediction
    try:
        validate_prediction(result, observation)
    except (TypeError, ValueError) as exc:
        metadata = _redact(copy.deepcopy(external_metadata), secrets)
        metadata["error_type"] = type(exc).__name__
        raise ExternalPredictionError("external prediction failed the canonical output contract", metadata) from None
    return result


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to a redirected origin.
        return None


class ChatCompletionBaseline:
    def __init__(self, method_id, config):
        if method_id not in {"B2", "B3"}:
            raise ValueError("direct chat is only B2/B3; Mentis requires official command integration")
        self.method_id = method_id
        self.config = copy.deepcopy(config)
        if "api_key" in self.config:
            raise ValueError("do not store API keys in configuration; use api_key_env")

    def fit(self, train_pairs):
        """These are training-free baselines; labels are never inserted into prompts."""
        return self

    def _settings(self):
        cfg = self.config
        base = cfg.get("base_url") or os.environ.get(cfg.get("base_url_env", "MWM_LLM_BASE_URL"), "")
        model = cfg.get("model") or os.environ.get(cfg.get("model_env", "MWM_LLM_MODEL"), "")
        key = os.environ.get(cfg.get("api_key_env", "MWM_LLM_API_KEY"), "")
        return str(base).strip(), str(model).strip(), key

    def availability(self):
        if self.config.get("enabled", False) is not True:
            return {"available": False, "reason": "LLM integration disabled; no remote call was made"}
        base, model, key = self._settings()
        missing = []
        if not base:
            missing.append(self.config.get("base_url_env", "MWM_LLM_BASE_URL"))
        if not model:
            missing.append(self.config.get("model_env", "MWM_LLM_MODEL"))
        if not key and self.config.get("require_api_key", True):
            missing.append(self.config.get("api_key_env", "MWM_LLM_API_KEY"))
        if missing:
            return {"available": False, "reason": "missing configuration/environment: " + ", ".join(missing)}
        try:
            parts = parse.urlsplit(base)
        except ValueError:
            return {"available": False, "reason": "invalid base URL"}
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
            return {"available": False, "reason": "base URL must be HTTP(S), without credentials, query or fragment"}
        return {"available": True, "reason": "configuration present; real endpoint/model has not been health-checked"}

    def spec(self):
        base, model, _ = self._settings()
        return {
            "method_id": self.method_id,
            "implementation": "openai_compatible_chat_completions",
            "training": "none",
            "history": "all cutoff observations",
            "prompt_variant": "direct" if self.method_id == "B2" else "structured",
            "model": _redact(model, _secret_values(self.config)),
            "endpoint_configured": bool(base),
            "temperature": self.config.get("temperature", 0),
            "max_output_tokens": self.config.get("max_output_tokens", 1024),
            "token_parameter": self.config.get("token_parameter", "max_completion_tokens"),
            "max_retries": self.config.get("max_retries", 2),
            **_seed_details(self.config, "http"),
            "availability": self.availability(),
            "probability_source": "model-reported; calibration requires measurement",
        }

    def _messages(self, observation):
        contract = (
            'Return one strict JSON object with exactly these fields: '
            'resume_label ("resume" or "not_resume"), resume_step (task step ID or null), '
            'p_resume (number 0..1 or null), conditional_step_probs (object mapping task steps '
            'to probabilities summing to 1, or null), state_probs (object mapping factors V/F/A/B/C/Q '
            'to label probability objects, or {}), evidence_event_ids (list of observed event IDs), '
            'reason (brief evidence-based explanation), metadata (object). '
            'Do not invent missing evidence or treat objective world events as automatically known '
            'to the person. Predict within horizon, based solely on the supplied cutoff observation. '
            'Use null/empty distributions if you cannot provide probabilities. '
            'For not_resume use resume_step=null. Do not claim to have observed future behavior. '
        )
        if self.method_id == "B3":
            variant = (
                'Organize your analysis around: original goal; objective validity and feasibility; '
                'information the person could access and understand; goal commitment; completed '
                'and remaining steps. These are prompt headings, not a persistent state updater. '
            )
        else:
            variant = 'Predict resumption directly from the complete event history. '
        return [
            {"role": "system", "content": variant + contract},
            {"role": "user", "content": json.dumps(observation, ensure_ascii=False, sort_keys=True, allow_nan=False)},
        ]

    def predict(self, observation):
        status = self.availability()
        if not status["available"]:
            raise UnavailableError(status["reason"])
        obs = _observation_copy(observation)
        base, model, key = self._settings()
        cfg = self.config
        seed_details = _seed_details(cfg, "http")
        token_parameter = cfg.get("token_parameter", "max_completion_tokens")
        if token_parameter not in {"max_completion_tokens", "max_tokens"}:
            raise ValueError("token_parameter must be max_completion_tokens or max_tokens")
        max_tokens = cfg.get("max_output_tokens", 1024)
        retries = cfg.get("max_retries", 2)
        if type(max_tokens) is not int or max_tokens <= 0 or type(retries) is not int or not 0 <= retries <= 10:
            raise ValueError("invalid output-token or retry budget")
        payload = {"model": model, "messages": self._messages(obs), token_parameter: max_tokens,
                   "response_format": {"type": "json_object"}}
        if cfg.get("temperature", 0) is not None:
            payload["temperature"] = cfg.get("temperature", 0)
        if seed_details["effective_seed_requested"] is not None:
            payload["seed"] = seed_details["effective_seed_requested"]
        endpoint = base.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        opener = request.build_opener(_NoRedirect)
        started = time.perf_counter()
        secrets = _secret_values(cfg)
        attempts = 0
        failures = []
        attempt_usages = []
        response_data = None
        for attempt in range(retries + 1):
            attempts += 1
            try:
                req = request.Request(endpoint, data=body, headers=headers, method="POST")
                with opener.open(req, timeout=float(cfg.get("timeout_seconds", 120))) as reply:
                    raw_bytes = reply.read(int(cfg.get("max_response_bytes", 8_388_608)) + 1)
                if len(raw_bytes) > int(cfg.get("max_response_bytes", 8_388_608)):
                    raise ExternalPredictionError("external response exceeded configured byte limit", {
                        "model": _redact(model, secrets), "attempts": attempts,
                        **_redact(_usage_accounting(attempt_usages + [None]), secrets), **seed_details,
                    })
                response_data = _json_loads(raw_bytes.decode("utf-8"))
                attempt_usages.append(_reported_usage(response_data))
                break
            except error.HTTPError as exc:
                code = int(exc.code)
                # Keep only structured usage; error bodies can echo credentials.
                reported = None
                try:
                    error_body = exc.read(int(cfg.get("max_response_bytes", 8_388_608)))
                    reported = _reported_usage(_json_loads(error_body.decode("utf-8")))
                except (ValueError, UnicodeError, OSError):
                    pass
                exc.close()
                attempt_usages.append(reported)
                failures.append({"kind": "http", "status": code})
                retryable = code == 429 or 500 <= code <= 599
            except (error.URLError, TimeoutError, OSError) as exc:
                # Exception strings can contain credential-bearing URLs; record type only.
                failures.append({"kind": "transport", "type": type(exc).__name__})
                attempt_usages.append(None)
                retryable = True
            except (ValueError, UnicodeError) as exc:
                raise ExternalPredictionError("chat endpoint returned invalid JSON", {
                    "model": _redact(model, secrets), "attempts": attempts, "latency_ms": (time.perf_counter() - started) * 1000,
                    "error_type": type(exc).__name__,
                    **_redact(_usage_accounting(attempt_usages + [None]), secrets), **seed_details,
                }) from None
            if not retryable or attempt == retries:
                raise ExternalPredictionError("chat request failed; see sanitized transport metadata", {
                    "model": _redact(model, secrets), "attempts": attempts, "retries": attempts - 1,
                    "latency_ms": (time.perf_counter() - started) * 1000, "failures": failures,
                    **_redact(_usage_accounting(attempt_usages), secrets), **seed_details,
                }) from None
            delay = min(float(cfg.get("retry_delay_seconds", 1)) * (2 ** attempt), 10)
            if delay > 0:
                time.sleep(delay)
        metadata = {
            "transport": "chat_completions", "requested_model": model,
            "model": response_data.get("model", model) if isinstance(response_data, dict) else model,
            "response_id": response_data.get("id") if isinstance(response_data, dict) else None,
            **_usage_accounting(attempt_usages),
            "response_usage": response_data.get("usage") if isinstance(response_data, dict) else None,
            "system_fingerprint": response_data.get("system_fingerprint") if isinstance(response_data, dict) else None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "attempts": attempts, "retries": attempts - 1, "failures": failures,
            "temperature": cfg.get("temperature", 0), "max_output_tokens": max_tokens,
            "real_http_execution": True,
            **seed_details,
        }
        try:
            raw = response_data["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise ValueError("message content is not text")
            metadata["raw_output"] = _redact(raw, secrets)
            prediction = _json_loads(raw)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            metadata["error_type"] = type(exc).__name__
            raise ExternalPredictionError("chat response did not contain a strict JSON prediction", _redact(metadata, secrets)) from None
        return _validated_prediction(prediction, obs, metadata, secrets)


class CommandBaseline:
    """One observation on stdin, one canonical prediction JSON on stdout.

    This is OUR adapter contract, not the upstream Mentis CLI contract.
    Modes are supplied via environment; observation contents remain identical.
    """

    def __init__(self, method_id, config, ablations=None):
        self.method_id = method_id
        self.config = copy.deepcopy(config)
        self.ablations = copy.deepcopy(ablations or {})

    def fit(self, train_pairs):
        return self

    def availability(self):
        cfg = self.config
        argv = cfg.get("argv")
        if cfg.get("enabled", False) is not True:
            return {"available": False, "reason": "external command integration disabled; real dependency not run"}
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            return {"available": False, "reason": "missing argv list for an explicit local task adapter"}
        if cfg.get("cwd") and not Path(cfg["cwd"]).is_dir():
            return {"available": False, "reason": "adapter working directory does not exist"}
        missing_env = [name for name in cfg.get("required_env", []) if not os.environ.get(name)]
        if missing_env:
            return {"available": False, "reason": "missing adapter environment: " + ", ".join(missing_env)}
        for name, relative_file in cfg.get("required_root_files", {}).items():
            if not os.environ.get(name) or not (Path(os.environ[name]) / relative_file).is_file():
                return {"available": False, "reason": "missing local dependency file under environment " + name}
        executable = argv[0]
        candidate = Path(executable)
        if cfg.get("cwd") and not candidate.is_absolute():
            candidate = Path(cfg["cwd"]) / candidate
        if not candidate.is_file() and shutil.which(executable) is None:
            return {"available": False, "reason": "adapter executable was not found"}
        if self.method_id in {"B8", "B9", "MENTIS_STRUCTURED"}:
            provenance = cfg.get("provenance", {})
            if not provenance.get("repository") or not provenance.get("commit"):
                return {"available": False, "reason": "official Mentis repository and pinned commit provenance required"}
        return {"available": True, "reason": "command configured; upstream task adaptation/model execution not yet verified"}

    def spec(self):
        cfg = self.config
        # Do not echo arbitrary argv: it might contain operator-provided credentials.
        ablations = {
            name: {"description": description, "config_path": self.ablations.get(name),
                   "status": "configured_reference" if self.ablations.get(name) else "awaiting_A_implementation"}
            for name, description in ABLATIONS.items()
        } if self.method_id == "B10" else {}
        return {
            "method_id": self.method_id, "implementation": "external_command_adapter",
            "mode": cfg.get("mode", MODES.get(self.method_id, self.method_id)),
            "interface": "observation JSON stdin -> canonical prediction JSON stdout",
            "command_configured": bool(cfg.get("argv")), "shell": False,
            "provenance": _redact(cfg.get("provenance", {}), _secret_values(cfg)),
            "adapter_is_upstream_api": False,
            "availability": self.availability(), "ablations": ablations,
            **_seed_details(cfg, "command"),
        }

    def predict(self, observation):
        status = self.availability()
        if not status["available"]:
            raise UnavailableError(status["reason"])
        obs = _observation_copy(observation)
        cfg = self.config
        seed_details = _seed_details(cfg, "command")
        env = os.environ.copy()
        env.pop("MWM_SEED", None)
        if seed_details["effective_seed_requested"] is not None:
            env["MWM_SEED"] = str(seed_details["effective_seed_requested"])
        env["PYTHONIOENCODING"] = "utf-8"
        env["MWM_METHOD_ID"] = self.method_id
        env["MWM_ADAPTER_MODE"] = str(cfg.get("mode", MODES.get(self.method_id, self.method_id)))
        # Config may name existing environment variables, never contain key values.
        secrets = _secret_values(cfg)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                cfg["argv"], input=json.dumps(obs, ensure_ascii=False, allow_nan=False),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8",
                cwd=cfg.get("cwd") or None, env=env, shell=False,
                timeout=float(cfg.get("timeout_seconds", 300)), check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            reported = None
            try:
                if len(partial.encode("utf-8")) <= int(cfg.get("max_response_bytes", 8_388_608)):
                    reported = _reported_usage(_json_loads(partial))
            except (ValueError, UnicodeError):
                pass
            raise ExternalPredictionError("external adapter timed out", {
                "method_id": self.method_id, "mode": env["MWM_ADAPTER_MODE"],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "error_type": "TimeoutExpired",
                **_redact(_usage_accounting([reported]), secrets), **seed_details,
            }) from None
        except (OSError, ValueError) as exc:
            raise ExternalPredictionError("external adapter could not start", {
                "method_id": self.method_id, "error_type": type(exc).__name__,
                "usage": None, **seed_details,
            }) from None
        metadata = {
            "transport": "local_command", "mode": env["MWM_ADAPTER_MODE"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "returncode": completed.returncode, "attempts": 1, "retries": 0,
            "raw_output": _redact(completed.stdout, secrets),
            "stderr": _redact(completed.stderr, secrets),
            "provenance": _redact(cfg.get("provenance", {}), secrets),
            "real_child_process_execution": True,
            "usage": None,
            **seed_details,
        }
        if len(completed.stdout.encode("utf-8")) > int(cfg.get("max_response_bytes", 8_388_608)):
            metadata.pop("raw_output", None)
            raise ExternalPredictionError("external adapter output exceeded configured byte limit", metadata)
        try:
            prediction = _json_loads(completed.stdout)
        except (ValueError, UnicodeError) as exc:
            metadata["error_type"] = type(exc).__name__
            message = ("external adapter exited unsuccessfully" if completed.returncode
                       else "external adapter stdout must be one strict JSON object")
            raise ExternalPredictionError(message, metadata) from None
        metadata.update(_redact(_usage_accounting([_reported_usage(prediction)]), secrets))
        if completed.returncode:
            raise ExternalPredictionError("external adapter exited unsuccessfully", metadata)
        return _validated_prediction(prediction, obs, metadata, secrets)


def make_external_baselines(config: dict) -> dict:
    """Registry entries exist even when unavailable; runner must record skipped status."""
    llm = copy.deepcopy(config.get("llm", {}))
    llm["requested_seed"] = config.get("run_seed", llm.get("seed"))
    commands = config.get("commands", {})
    methods = {method_id: ChatCompletionBaseline(method_id, llm) for method_id in ("B2", "B3")}
    for method_id in ("B8", "B9", "B10", "MENTIS_STRUCTURED"):
        command = copy.deepcopy(commands.get(method_id, {}))
        if method_id in {"B9", "MENTIS_STRUCTURED"}:
            # Context controls must use the same official engine/checkout as B8.
            original = copy.deepcopy(commands.get("B8", {}))
            variant_enabled = command.get("enabled", original.get("enabled", False))
            original.update({key: value for key, value in command.items()
                             if key not in {"argv", "cwd", "provenance", "required_env", "required_root_files", "mode"}})
            command = original
            command["enabled"] = variant_enabled
            command["mode"] = MODES[method_id]
        command["requested_seed"] = config.get("run_seed", command.get("seed"))
        methods[method_id] = CommandBaseline(method_id, command, config.get("ablations", {}))
    return methods
