"""可独立运行的 C 侧训练/校准/评价编排，无 mock 结果冒充外部方法。"""

import copy
import json
import math
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from mwm_eval.calibration import apply_temperature, fit_temperature
from mwm_eval.external import UnavailableError, make_external_baselines
from mwm_eval.local_baselines import make_local_baselines
from mwm_eval.metrics import evaluate
from mwm_eval.schema import audit_groups, canonical_hash, file_hash, load_jsonl, validate_dataset, validate_prediction
from mwm_eval.statistics import paired_cluster_bootstrap


ROOT = Path(__file__).resolve().parents[1]


def _usage(metadata):
    if not isinstance(metadata, dict):
        return None
    external = metadata.get("external", {})
    return (external.get("usage") if isinstance(external, dict) else None) or metadata.get("usage")


def dump_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def dump_jsonl(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def actual_observation(record, method_id):
    obs = copy.deepcopy(record["observation"])
    if method_id == "B1":
        obs["events"] = obs["events"][-5:]
    return obs


def predict_rows(method, records, seed, unavailable_reason=None, failure_status="unavailable"):
    rows = []
    for record in records:
        obs = actual_observation(record, method.method_id)
        row = {
            "sample_id": record["sample_id"], "method_id": method.method_id, "seed": seed,
            "split": record["split"], "input_hash": canonical_hash(obs),
            "source_input_hash": canonical_hash(record["observation"]),
            "actual_input_event_ids": [event["event_id"] for event in obs["events"]],
            "cutoff": obs["cutoff"], "horizon": obs["horizon"], "status": failure_status if unavailable_reason else "ok",
            "prediction": None, "error": unavailable_reason, "latency_ms": 0.0,
            "input_event_count": len(obs["events"]), "input_characters": len(json.dumps(obs, ensure_ascii=False)),
            "usage": None, "attempted": False,
            "seed_control": "local_seed" if method.method_id in {"B0", "B1", "B4", "B5", "B6", "B7"}
                            else method.spec().get("seed_control", "not_guaranteed"),
        }
        if unavailable_reason:
            rows.append(row)
            continue
        started = time.perf_counter()
        row["attempted"] = True
        try:
            prediction = method.predict(copy.deepcopy(obs))
            if isinstance(prediction, dict):
                row["usage"] = _usage(prediction.get("metadata"))
            validate_prediction(prediction, obs)
            canonical_hash(prediction)  # Logs must remain finite, serializable JSON.
            row["prediction"] = prediction
        except UnavailableError as exc:
            row["status"], row["error"] = "unavailable", str(exc)
        except Exception as exc:
            row["status"], row["error"] = "error", f"{type(exc).__name__}: {exc}"
            if hasattr(exc, "metadata"):
                row["failure_metadata"] = exc.metadata
                row["usage"] = _usage(exc.metadata) or row["usage"]
        row["latency_ms"] = (time.perf_counter() - started) * 1000
        rows.append(row)
    return rows


def _cost(rows):
    known = [row["usage"] for row in rows if isinstance(row.get("usage"), dict)]
    totals = {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        values = [usage[name] for usage in known if isinstance(usage.get(name), (int, float))
                  and not isinstance(usage[name], bool) and math.isfinite(usage[name]) and usage[name] >= 0]
        totals[name] = sum(values) if values else None
    timings = sorted(row["latency_ms"] for row in rows if row["status"] == "ok")
    return {"n_attempted": sum(row.get("attempted", row["status"] != "unavailable") for row in rows),
            "n_usage_known": len(known), "n_latency_known": len(timings),
            "tokens": totals, "total_measured_ms": sum(row["latency_ms"] for row in rows),
            "median_ms": timings[len(timings)//2] if timings else None,
            "p95_ms": timings[min(len(timings)-1, int((len(timings)-1)*.95))] if timings else None,
            "gpu_usage": None, "money_cost": None,
            "note": "CPU host wall time measured; unavailable tokens/GPU/money are null, never fabricated zero"}


def _aggregate(runs):
    result = {}
    for method in sorted({run["method_id"] for run in runs}):
        matching = [run for run in runs if run["method_id"] == method]
        result[method] = {"n_seeds": len(matching), "metrics": {}}
        for name in ("accuracy_all_eligible", "resume_f1", "step_accuracy"):
            values = [(run["metrics"] or {}).get(name) for run in matching if run["status"] != "unavailable"]
            values = [value for value in values if value is not None]
            mean = sum(values)/len(values) if values else None
            sd = (sum((value-mean)**2 for value in values)/(len(values)-1))**.5 if len(values)>1 else None
            result[method]["metrics"][name] = {"mean": mean, "sample_sd": sd, "n_defined": len(values)}
        result[method]["statuses"] = dict(Counter(run["status"] for run in matching))
    return result


def _subgroup_scores(rows, golds, records):
    results = {}
    for key in ("domain", "task_family", "person_id"):
        results[key] = {}
        for value in sorted({record[key] for record in records}):
            subset = [record for record in records if record[key] == value]
            ids = {record["sample_id"] for record in subset}
            # A subset may contain only part of a pair; suppress pair-only metadata for subgroup aggregation.
            selected_golds = copy.deepcopy([gold for gold in golds if gold["sample_id"] in ids])
            for gold in selected_golds:
                gold.pop("pair_id", None)
                gold.pop("pair_relation", None)
            results[key][value] = evaluate([row for row in rows if row["sample_id"] in ids], selected_golds, subset)
    return results


def run_experiment(inputs_path, labels_path, output_dir, config, methods, seeds, suite="all", enable_external=False):
    if not methods or not seeds or len(set(methods)) != len(methods) or len(set(seeds)) != len(seeds):
        raise ValueError("methods and seeds must be nonempty and unique")
    records, golds = load_jsonl(inputs_path), load_jsonl(labels_path)
    validation = validate_dataset(records, golds)
    horizons = {canonical_hash(record["observation"]["horizon"]) for record in records}
    if len(horizons) != 1:
        raise ValueError("This pipeline requires a fixed horizon; run different horizon types/values separately")
    group_audit = audit_groups(records)
    if group_audit["person_id"]["pairwise_overlap"]["train__calibration"]:
        raise ValueError("calibration and training must use disjoint people")
    for key in config.get("evaluation", {}).get("required_group_isolation", []):
        if key not in group_audit:
            raise ValueError("unknown required_group_isolation key")
        if group_audit[key]["n_overlap"]:
            raise ValueError(f"required held-out group overlaps train/test: {key}")
    train = [record for record in records if record["split"] == "train"]
    calibration_records = [record for record in records if record["split"] == "calibration"]
    test = [record for record in records if record["split"] == "test"]
    if not test:
        raise ValueError("a nonempty frozen test split is required")
    by_gold = {gold["sample_id"]: gold for gold in golds}
    test_golds = [by_gold[record["sample_id"]] for record in test]
    calibration_golds = [by_gold[record["sample_id"]] for record in calibration_records]
    train_pairs = [(copy.deepcopy(record["observation"]), copy.deepcopy(by_gold[record["sample_id"]])) for record in train]
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    settings = copy.deepcopy(config)
    if not enable_external:
        settings.setdefault("llm", {})["enabled"] = False
        for command in settings.get("commands", {}).values():
            command["enabled"] = False
    effective_config_hash = canonical_hash(settings)
    all_rows, all_calibration_rows, runs, comparisons, stress, statuses = [], [], [], [], [], {}
    first_seed_rows, first_seed_models = {}, {}
    for seed in seeds:
        settings["run_seed"] = seed
        registry = {**make_local_baselines(seed), **make_external_baselines(settings)}
        for method_id in methods:
            if method_id not in registry:
                raise ValueError(f"unknown method: {method_id}")
            method = registry[method_id]
            available = method.availability() if hasattr(method, "availability") else {"available": True, "reason": "local implementation"}
            reason = available["reason"] if not available["available"] else None
            failure_status = "unavailable"
            fit_started = time.perf_counter()
            if reason is None:
                try:
                    method.fit(copy.deepcopy(train_pairs))
                except Exception as exc:
                    reason = f"fit failed: {type(exc).__name__}: {exc}"
                    failure_status = "error"
            fit_ms = (time.perf_counter()-fit_started)*1000
            calibration_rows = predict_rows(method, calibration_records, seed, reason, failure_status)
            calibration = fit_temperature(calibration_rows, calibration_golds)
            calibration_evaluation = evaluate(calibration_rows, calibration_golds, calibration_records) if calibration_records else None
            calibration_counts = calibration_evaluation["counts"] if calibration_evaluation else {"n_planned": 0, "n_success": 0, "n_error": 0, "n_unavailable": 0}
            calibration["prediction_counts"] = calibration_counts
            calibration["eligible_probability_coverage"] = calibration_evaluation["t1"]["probability"]["coverage"] if calibration_evaluation else None
            raw_rows = predict_rows(method, test, seed, reason, failure_status)
            rows = apply_temperature(raw_rows, calibration)
            metrics = evaluate(rows, test_golds, test)
            raw_metrics = evaluate(raw_rows, test_golds, test)
            if calibration_counts["n_error"]:
                run_status = "error"
                reason = reason or "calibration prediction errors; see calibration_predictions.jsonl"
            elif all(row["status"] == "unavailable" for row in rows):
                run_status = "unavailable"
                reason = reason or rows[0]["error"]
            else:
                run_status = "error" if metrics["counts"]["n_failure"] else "completed"
            counts = metrics["counts"]
            if run_status == "unavailable":
                metrics, raw_metrics = None, None
            entry = {"method_id": method_id, "seed": seed, "status": run_status, "reason": reason,
                     "spec": method.spec(), "fit_ms": fit_ms, "calibration": calibration,
                     "metrics": metrics, "raw_metrics": raw_metrics, "counts": counts, "cost": _cost(rows),
                     "calibration_cost": _cost(calibration_rows)}
            if suite == "all" and run_status != "unavailable":
                entry["subgroups"] = _subgroup_scores(rows, test_golds, test)
            runs.append(entry)
            all_rows.extend(rows)
            all_calibration_rows.extend(calibration_rows)
            priority = {"completed": 0, "unavailable": 1, "error": 2}
            if method_id not in statuses or priority[run_status] >= priority[statuses[method_id]["status"]]:
                statuses[method_id] = {"status": run_status, "reason": reason, "implementation": entry["spec"]}
            if seed == seeds[0]:
                first_seed_rows[method_id] = rows
                if run_status == "completed":
                    first_seed_models[method_id] = method
            print(f"  seed={seed} {method_id}: {run_status}", flush=True)

    # Compare independently trained methods on the SAME test records; never pool repeated seeds as new people.
    for method_id in methods:
        if method_id != "B0" and method_id in first_seed_models and "B0" in first_seed_models:
            comparison = paired_cluster_bootstrap(first_seed_rows[method_id], first_seed_rows["B0"],
                                                  test_golds, test, metric="accuracy", seed=seeds[0], n_bootstrap=500)
            comparisons.append({"method_a": method_id, "method_b": "B0", "seed": seeds[0], **comparison})
    if suite == "all":
        stress = _stress_runs(first_seed_models, test, test_golds, seeds[0])
    code_paths = [ROOT / "run_evaluation.py"]
    for folder in ("mwm_eval", "integration", "tools"):
        code_paths.extend(path for path in (ROOT/folder).rglob("*.py") if "__pycache__" not in str(path))
    manifest = {"protocol": "c-engineering-draft-0.2", "created_utc": datetime.now(timezone.utc).isoformat(),
                "purpose": "synthetic integration verification only" if validation["dataset_layer"] == "integration_fixture" else "research evaluation",
                "python": sys.version, "platform": platform.platform(), "validation": validation,
                "inputs_sha256": file_hash(inputs_path), "labels_sha256": file_hash(labels_path),
                "configuration_sha256": canonical_hash(config), "effective_configuration_sha256": effective_config_hash,
                "code_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): file_hash(path) for path in sorted(set(code_paths)) if path.exists()},
                "methods": methods, "seeds": seeds, "suite": suite, "external_enabled": enable_external,
                "train_n": len(train), "calibration_n": len(calibration_records), "test_n": len(test),
                "development_usage": "dev split retained; no test-based hyperparameter tuning",
                "group_audit": group_audit, "bootstrap": "paired by base_story_id, first seed only, 500 samples",
                "calibration": "temperature selected on calibration split only, separately for each method/seed"}
    overall = ("completed_with_errors" if any(run["status"] == "error" for run in runs)
               else "no_methods_executed" if not any(run["status"] == "completed" for run in runs)
               else "independent_C_pipeline_completed")
    status = {"methods": statuses, "external_methods_not_run": [key for key, value in statuses.items() if value["status"] == "unavailable"],
              "formal_P0": "not_supplied" if validation["dataset_layer"] != "P0" else "see input provenance",
              "formal_P1": "not_supplied" if validation["dataset_layer"] != "P1" else "see input provenance",
              "member_A_model_and_ablations": "not_supplied" if statuses.get("B10", {}).get("status") != "completed" else "see model manifest",
              "overall": overall}
    summary = {"dataset_layer": validation["dataset_layer"], "runs": runs, "aggregate": _aggregate(runs)}
    cases = []
    for row in all_rows:
        if row["seed"] != seeds[0]:
            continue
        gold = by_gold[row["sample_id"]]
        if gold["resume_label"] not in {"resume", "not_resume"}:
            continue
        if gold["dataset_layer"] == "P1" and not gold["window_complete"] and gold["resume_label"] != "resume":
            continue
        prediction = row.get("prediction")
        if row["status"] == "unavailable":
            continue
        errors = []
        if row["status"] != "ok":
            errors.append("execution_error")
        elif prediction["resume_label"] != gold["resume_label"]:
            errors.append("false_resume" if prediction["resume_label"] == "resume" else "missed_resume")
        if row["status"] == "ok" and gold["resume_label"] == "resume" and gold["resume_step"] is not None and prediction["resume_step"] != gold["resume_step"]:
            errors.append("wrong_or_missing_step")
        if errors:
            cases.append({"sample_id": row["sample_id"], "method_id": row["method_id"], "seed": row["seed"],
                          "error_types": errors, "gold_label": gold["resume_label"], "gold_step": gold["resume_step"],
                          "prediction": prediction, "execution_error": row["error"],
                          "scope": "post-inference error audit; gold was never supplied to predict"})
    for name, value in (("summary.json", summary), ("manifest.json", manifest), ("comparisons.json", comparisons),
                        ("stress.json", stress), ("status.json", status), ("error_cases.json", cases)):
        dump_json(output/name, value)
    dump_jsonl(output/"predictions.jsonl", all_rows)
    dump_jsonl(output/"calibration_predictions.jsonl", all_calibration_rows)
    write_report(output/"report.md", summary, manifest, comparisons, stress, status)
    return summary, status


def _stress_runs(models, records, golds, seed):
    results = []
    # Insert observable, explicitly non-task events only. Labels remain conditional scripted targets.
    # This probes event-window sensitivity; it is not a new real-world benchmark.
    for padding in (0, 5, 20):
        changed = copy.deepcopy(records)
        for record in changed:
            obs = record["observation"]
            for index in range(padding):
                obs["events"].append({
                    "event_id": f"stress_pad_{index}", "time": obs["cutoff"], "actor": "observer",
                    "event_type": "neutral_observation", "goal_id": None, "step_id": None,
                    "world_effect": None, "observer_evidence": "No task action or new task-relevant information.",
                    "person_access_evidence": {"status": "NOT_ACCESSED", "understood": None},
                    "source": "synthetic_stress_transform", "certainty": 1.0, "semantic": {"kind": "neutral_observation"},
                })
        for method_id, method in models.items():
            # Real external calls are deliberately excluded from synthetic stress sweeps.
            if method_id not in {"B0", "B1", "B4", "B5", "B6", "B7"}:
                continue
            rows = predict_rows(method, changed, seed)
            results.append({"transform": "neutral_event_padding", "padding_events": padding,
                            "method_id": method_id, "metrics": evaluate(rows, golds, changed), "cost": _cost(rows),
                            "scope": "synthetic length stress only; nested/task-count/missing-evidence sweeps still require validated data"})
    return results


def write_report(path, summary, manifest, comparisons, stress, status):
    def percent(value):
        return "—" if value is None else f"{value:.1%}"

    fixture = summary["dataset_layer"] == "integration_fixture"
    lines = ["# C 独立工程运行报告", "", f"数据层：`{summary['dataset_layer']}`。总体状态：`{status['overall']}`。", "",
             ("本次数据为合成集成样例，用于验收工程连接、规则执行、训练/校准隔离、统计与日志；不证明真实行为预测或新算法优势。"
              if fixture else "本次使用外部提供的研究数据。指标含义受数据层、许可、标签证据和划分质量限制，数据责任方仍需核验来源。"), "",
             f"训练 {manifest['train_n']} 条，独立校准 {manifest['calibration_n']} 条，测试 {manifest['test_n']} 条；种子 {manifest['seeds']}。", "",
             "## 实际完成状态", "", "| 方法 | 状态 | Accuracy均值 | Resume F1均值 | 步骤准确率均值 |", "| --- | --- | --- | --- | --- |"]
    for method_id, aggregated in summary["aggregate"].items():
        metrics = aggregated["metrics"]
        lines.append(f"| {method_id} | {status['methods'][method_id]['status']} | "
                     f"{percent(metrics['accuracy_all_eligible']['mean'])} | {percent(metrics['resume_f1']['mean'])} | "
                     f"{percent(metrics['step_accuracy']['mean'])} |")
    completed = [method for method, item in status["methods"].items() if item["status"] == "completed"]
    errors = [method for method, item in status["methods"].items() if item["status"] == "error"]
    lines += ["", "unavailable 表示未接入真实依赖，该方法未运行，表中的空值不是零分。", "",
              f"本次完成方法：{', '.join(completed) or '无'}；执行错误方法：{', '.join(errors) or '无'}。", "",
              "## 概率、校准与成本", "",
              "以下按首个种子列出；概率指标只覆盖实际提供概率的样本，完整分母见 summary.json。硬标签方法不补造概率。", "",
              "| 方法 | T1有效n | 概率覆盖 | Brier原始→校准 | ECE校准 | 温度T | 测试累计ms |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for run in summary["runs"]:
        if run["seed"] != manifest["seeds"][0] or run["metrics"] is None:
            continue
        metrics = run["metrics"]
        prob = metrics["t1"]["probability"]
        raw = run["raw_metrics"]["t1"]["probability"]
        def decimal(value):
            return "—" if value is None else f"{value:.4f}"
        lines.append(f"| {run['method_id']} | {metrics['t1']['n_eligible']} | {percent(prob['coverage'])} | "
                     f"{decimal(raw['brier'])} → {decimal(prob['brier'])} | {decimal(prob['ece'])} | "
                     f"{run['calibration']['temperature'] if run['calibration']['applicable'] else '—'} | {run['cost']['total_measured_ms']:.2f} |")
    lines += ["", "温度只在 calibration 划分选择，不改变硬标签。耗时为本机测量，GPU/费用/未知tokens记 null；不能据此推断部署成本。", "",
              "## 实现范围", "",
              "- B0 最近活动、B1 最近五事件、B4 无认知门控的持久记忆、B5 证据规则 BDI；B1 不声称严格复现 SET-PR。",
              "- B6 使用时长/负荷/线索的训练型逻辑回归；B7 为训练型 HMM，非 SIPS。HMM 潜态只有全部获得证据锚定才发布语义 C 分布。",
              "- 步骤分布是规则候选的点质量分布，不是学习到的步骤不确定性。未提供的状态因子或概率均保留缺失。",
              "- T1/T2、状态掩码、AUROC/AP、Brier/ECE、显式约束、成对诊断、覆盖率及分组统计。",
              "- train/calibration/test 分离，按故事簇配对 Bootstrap；逐样例预测、代码与数据哈希、实际耗时。",
              "- 外部协议的本机测试结果见测试日志；真实外部方法是否运行以上表和 status.json 为准。", "",
              "## 研究依赖", "",
              f"- 正式 P0：`{status['formal_P0']}`；正式 P1：`{status['formal_P1']}`。",
              f"- A 模型及消融：`{status['member_A_model_and_ablations']}`。",
              f"- 本次未运行方法：{', '.join(status['external_methods_not_run']) or '无'}。",
              "- B9 需要严格 token 等量控制；字符摘要预备适配器不能视为预算公平验收通过。", "",
              "## 核查入口", "",
              "- summary.json：每个方法/种子的完整指标、分母、覆盖率、训练参数、原始与校准结果。",
              "- predictions.jsonl / calibration_predictions.jsonl：逐条实际结果及输入/错误/资源记录。",
              "- comparisons.json：首种子按故事簇配对的差值区间；不将多个种子当新增人物。",
              "- stress.json：中性事件增加的长度敏感性；尚不能替代全部复杂度/鲁棒性实验。",
              "- error_cases.json：首种子 T1/T2 错误类别与逐例预测，仅在推理后对照答案生成。",
              "- manifest.json / status.json：可复现指纹、划分重叠和真实依赖状态。", "",
              "## 统计边界", "",
              ("规则生成模板在各集合共享，虽然故事ID/人物/任务族隔离，这仍是生成器内自检，不能据此声称跨域泛化。" if fixture else
               "分组重叠见 manifest.json；是否存在共享模板/受试者关联还需按数据卡复核。"),
              "小样本校准及Bootstrap区间的统计能力有限；工程验收通过不等于方法有效性已获证明。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
