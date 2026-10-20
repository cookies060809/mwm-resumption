"""Create an offline dashboard and CSV from an actual, already completed run."""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mwm_eval.schema import file_hash, load_jsonl


NAMES = {
    "B0": "最近动作", "B1": "五事件窗口", "B2": "完整历史 LLM", "B3": "结构化提示 LLM",
    "B4": "持久目标记忆", "B5": "证据规则 BDI", "B6": "激活逻辑回归", "B7": "贝叶斯 HMM",
    "B8": "公开版 MENTIS", "B9": "记忆增强 MENTIS", "B10": "A 的 ECR-MWM",
    "MENTIS_STRUCTURED": "结构化 MENTIS 适配对照"}
LOCAL = {"B0", "B1", "B4", "B5", "B6", "B7"}
STATUS = {"completed": "已运行", "unavailable": "待接入", "error": "运行错误", "not_requested": "未纳入本次运行"}


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _mean(values):
    values = [value for value in values if _number(value) is not None]
    return sum(values) / len(values) if values else None


def _percent(value):
    return "—" if _number(value) is None else f"{value:.1%}"


def _decimal(value):
    return "—" if _number(value) is None else f"{value:.3f}"


def _escape(value):
    return html.escape(str(value), quote=True)


def _json_script(value):
    # JSON is inert data. Escaping '<' prevents every form of </script> break-out.
    return (json.dumps(value, ensure_ascii=False, allow_nan=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _ordered_methods(methods):
    ordered = [method for method in NAMES if method in methods]
    return ordered + sorted(set(methods) - set(ordered))


def make_payload(summary, manifest, status, predictions, records, golds):
    methods = _ordered_methods(set(summary.get("aggregate", {})) | set(status.get("methods", {})))
    table = []
    for method_id in methods:
        aggregate = summary.get("aggregate", {}).get(method_id, {})
        selected = [run for run in summary.get("runs", []) if run["method_id"] == method_id]
        defined = [run for run in selected if run.get("status") != "unavailable" and run.get("metrics")]
        first = defined[0] if defined else {}
        entry = status.get("methods", {}).get(method_id, {})
        metrics = aggregate.get("metrics", {})
        probabilities = [(run.get("metrics") or {}).get("t1", {}).get("probability", {}) for run in defined]
        state = entry.get("status", "not_requested")
        table.append({
            "method_id": method_id, "name": NAMES.get(method_id, method_id), "status": state,
            "status_text": STATUS.get(state, state), "reason": entry.get("reason"),
            "local": method_id in LOCAL, "n_seeds": aggregate.get("n_seeds", len(selected)),
            "accuracy_mean": metrics.get("accuracy_all_eligible", {}).get("mean"),
            "accuracy_sd": metrics.get("accuracy_all_eligible", {}).get("sample_sd"),
            "resume_f1_mean": metrics.get("resume_f1", {}).get("mean"),
            "resume_f1_sd": metrics.get("resume_f1", {}).get("sample_sd"),
            "step_accuracy_mean": metrics.get("step_accuracy", {}).get("mean"),
            "step_accuracy_sd": metrics.get("step_accuracy", {}).get("sample_sd"),
            "brier_mean": _mean(probability.get("brier") for probability in probabilities),
            "ece_mean": _mean(probability.get("ece") for probability in probabilities),
            "first_seed_n_eligible_t1": first.get("metrics", {}).get("counts", {}).get("n_eligible_t1"),
            "first_seed_n_eligible_t2": first.get("metrics", {}).get("n_eligible_t2"),
            "n_success_all_seeds": sum((run.get("metrics") or {}).get("counts", {}).get("n_success", 0) for run in selected),
            "n_error_all_seeds": sum((run.get("metrics") or {}).get("counts", {}).get("n_error", 0) for run in selected),
        })
    available_ids = {row["sample_id"] for row in predictions}
    selected_records = [record for record in records if record["sample_id"] in available_ids]
    return {"dataset_layer": summary["dataset_layer"], "manifest": manifest,
            "overall": status.get("overall"), "table": table,
            "predictions": predictions, "records": selected_records,
            "golds": [gold for gold in golds if gold["sample_id"] in available_ids]}


def _csv_text(table):
    fields = ["method_id", "name", "status", "n_seeds", "accuracy_mean", "accuracy_sd",
              "resume_f1_mean", "resume_f1_sd", "step_accuracy_mean", "step_accuracy_sd",
              "brier_mean", "ece_mean", "first_seed_n_eligible_t1", "first_seed_n_eligible_t2",
              "n_success_all_seeds", "n_error_all_seeds"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in table:
        values = {key: row.get(key) for key in fields}
        for key, value in values.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                values[key] = "'" + value
        writer.writerow(values)
    return stream.getvalue()


def _chart(table):
    local = [row for row in table if row["local"]]
    width, row_height = 620, 39
    height = len(local) * row_height + 36
    pieces = [f'<svg role="img" aria-label="六个本地基线在工程样例上的准确率" viewBox="0 0 {width} {height}">']
    for index, row in enumerate(local):
        y, value = 27 + index * row_height, _number(row["accuracy_mean"])
        pieces.append(f'<text x="0" y="{y + 3}" class="chart-label">{_escape(row["method_id"])} {_escape(row["name"])}</text>')
        pieces.append(f'<rect x="194" y="{y - 12}" width="340" height="19" rx="5" fill="#edf0f5"/>')
        if value is not None:
            bar_width = max(0, min(1, value)) * 340
            pieces.append(f'<rect x="194" y="{y - 12}" width="{bar_width:.2f}" height="19" rx="5" fill="#426cdb"/>')
        pieces.append(f'<text x="546" y="{y + 3}" class="chart-value">{_percent(value)}</text>')
    pieces.append(f'<text x="194" y="{height - 1}" class="chart-foot">0%</text><text x="502" y="{height - 1}" class="chart-foot">100%</text></svg>')
    return "".join(pieces)


def render_dashboard(payload, links=None):
    links = links or {"report": "report.md", "csv": "metrics.csv", "summary": "summary.json"}
    manifest, table = payload["manifest"], payload["table"]
    is_fixture = payload["dataset_layer"] == "integration_fixture"
    layer_title = "工程联调样例 · 不能作为比赛成绩" if is_fixture else "研究评测结果 · 以输入来源与报告为准"
    counts = Counter(row["status"] for row in table)
    date = manifest.get("created_utc", "")
    try:
        date = datetime.fromisoformat(date).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M 北京时间")
    except (ValueError, TypeError):
        date = "未记录运行时间"
    cards = "".join(f'<div class="stat"><span>{_escape(label)}</span><strong>{_escape(value)}</strong></div>'
                    for label, value in (("训练样例", manifest.get("train_n", "—")),
                                         ("独立校准", manifest.get("calibration_n", "—")),
                                         ("测试样例", manifest.get("test_n", "—")),
                                         ("已运行方法", counts["completed"]),
                                         ("待接入方法", counts["unavailable"])))
    rows = []
    for row in table:
        state = row["status"] if row["status"] in STATUS else "not_requested"
        name = _escape(row["name"])
        rows.append(f'<tr><td><strong>{_escape(row["method_id"])}</strong><span class="method-name">{name}</span></td>'
                    f'<td><span class="badge {state}" title="{_escape(row.get("reason") or "")}">{_escape(row["status_text"])}</span></td>'
                    f'<td>{_percent(row["accuracy_mean"])}</td><td>{_percent(row["resume_f1_mean"])}</td>'
                    f'<td>{_percent(row["step_accuracy_mean"])}</td><td>{_decimal(row["brier_mean"])}</td>'
                    f'<td>{_decimal(row["ece_mean"])}</td></tr>')
    template = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>C 工作现场演示 · 心智世界模型评测</title><style>
:root{color-scheme:light;--ink:#18263d;--muted:#64738b;--line:#e5e9f1;--blue:#426cdb;--bg:#f3f5fa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1240px;margin:auto;padding:38px 30px 60px}header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:22px}
h1{font-size:30px;line-height:1.3;margin:4px 0 8px;letter-spacing:-.5px}h2{font-size:19px;margin:0 0 13px}h3{font-size:16px;margin:0 0 8px}.eyebrow{font-size:12px;color:var(--blue);letter-spacing:2px;font-weight:700}
p{margin:8px 0}.muted{color:var(--muted)}.meta{font-size:12px;color:var(--muted)}.links{display:flex;gap:8px;flex-wrap:wrap}.links a{color:#3156ac;text-decoration:none;background:white;border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13px}
.notice{border:1px solid #eac897;background:#fff7e9;color:#72501c;border-radius:12px;padding:16px 19px;margin:20px 0}.notice strong{display:block;font-size:17px;margin-bottom:4px}.notice p{font-size:13px;margin:0}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:22px 0}.stat{padding:15px 19px;background:white;border:1px solid var(--line);border-radius:12px}.stat span{display:block;font-size:12px;color:var(--muted)}.stat strong{font-size:28px;font-weight:650}
.panel{background:#fff;border:1px solid var(--line);border-radius:14px;padding:23px;margin-bottom:20px;box-shadow:0 5px 18px #21355904}.overview{display:grid;grid-template-columns:1.35fr 1fr;gap:20px}.overview .panel{margin:0}.overview{margin-bottom:20px}
table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:var(--muted);font-size:12px;font-weight:600;border-bottom:1px solid var(--line);padding:10px 12px;white-space:nowrap}td{border-bottom:1px solid #eef1f5;padding:11px 12px;vertical-align:top}tr:last-child td{border-bottom:0}.scroll{overflow:auto}.method-name{display:block;font-size:12px;color:var(--muted)}.badge{display:inline-block;font-size:11px;padding:3px 8px;border-radius:5px;white-space:nowrap}.completed,.ok{background:#edf6f0;color:#347553}.unavailable,.not_requested{background:#f0f2f6;color:#6c778c}.error{background:#fff0ef;color:#b54740}.chart-label{fill:#354862;font:13px "Segoe UI","Microsoft YaHei",sans-serif}.chart-value{fill:#18263d;font:600 13px "Segoe UI",sans-serif}.chart-foot{fill:#8590a4;font:11px "Segoe UI",sans-serif}svg{width:100%;height:auto;display:block}.fact{padding:10px 0;border-bottom:1px solid var(--line)}.fact:last-child{border:0}.fact strong{font-size:13px;display:block}.fact span{font-size:12px;color:var(--muted)}
.controls{display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:20px}label{font-size:12px;color:var(--muted)}label span{display:block;margin-bottom:4px}select{min-width:155px;max-width:100%;border:1px solid #d8deea;border-radius:8px;padding:9px 32px 9px 10px;background:white;color:var(--ink);font:inherit}#sample{min-width:240px}.outcomes{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px}.outcome{padding:18px;background:#f7f9fc;border:1px solid var(--line);border-radius:10px}.outcome.gold{background:#f7faf7}dl{display:grid;grid-template-columns:100px 1fr;gap:6px 12px;font-size:13px;margin:10px 0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}#error{display:none;padding:12px 15px;border-radius:8px;background:#fff3e8;color:#8b5323;font-size:13px;margin:0 0 16px;white-space:pre-wrap;overflow-wrap:anywhere}.context{font-size:12px;color:var(--muted);margin-bottom:10px}.toggle{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:12px;margin:12px 0}.discarded{opacity:.48}.event-kind{color:#4463a1;font-size:12px;display:block}.tiny{font-size:11px;color:var(--muted)}details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;color:#476187;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 Consolas,monospace;background:#f5f7fb;padding:15px;border-radius:8px;max-height:420px;overflow:auto}.footnote{font-size:12px;color:var(--muted);margin-top:13px}.empty{color:var(--muted);padding:20px;text-align:center}
@media(max-width:900px){main{padding:24px 15px}.overview,.outcomes{grid-template-columns:1fr}.stats{grid-template-columns:repeat(3,1fr)}header{display:block}.links{margin-top:14px}h1{font-size:25px}}@media(max-width:520px){.stats{grid-template-columns:repeat(2,1fr)}.panel{padding:16px}select,#sample{min-width:0;width:100%}.controls label{width:100%}}
</style></head><body><main>
<header><div><div class="eyebrow">C · 系统 / 基线 / 实验</div><h1>跨中断恢复预测 · 运行现场</h1><div class="meta">__DATE__ · 完全离线，可直接打开</div></div><div class="links"><a href="__REPORT__">完整报告</a><a href="__CSV__" download>下载指标 CSV</a><a href="__SUMMARY__">原始汇总</a></div></header>
<div class="notice"><strong>__LAYER_TITLE__</strong><p>__BOUNDARY__</p></div>
<div class="stats">__CARDS__</div>
<div class="overview"><section class="panel"><h2>六个本地基线的工程样例准确率</h2>__CHART__<p class="footnote">各随机种子的均值。空值表示没有可用测量；种子复跑不会增加独立样本数。</p></section><section class="panel"><h2>这次演示能核查什么</h2><div class="fact"><strong>同一输入协议与冻结测试集</strong><span>从截止前事件出发，保存每个方法实际收到的历史与输入指纹。</span></div><div class="fact"><strong>预测和答案分别保存</strong><span>下方可以直接核对事件、恢复判断、步骤及失败原因。</span></div><div class="fact"><strong>训练、校准和测试分开</strong><span>模型参数来自训练集；温度只在独立校准集选择。</span></div><div class="fact"><strong>真实外部依赖如实列出</strong><span>待接入的方法没有伪造预测；未知成本和缺失指标保留为空。</span></div></section></div>
<section class="panel"><h2>方法与结果</h2><div class="scroll"><table><thead><tr><th>方法</th><th>实际状态</th><th>恢复准确率</th><th>Resume F1</th><th>恢复步骤准确率</th><th>Brier</th><th>ECE</th></tr></thead><tbody>__ROWS__</tbody></table></div><p class="footnote">T1 排除删失与未知答案；T2 只评价确实恢复且步骤可辨认的记录。Brier / ECE 仅在提供恢复概率的记录上计算。— 表示缺失或不适用；CSV 空单元格同义。种子标准差与各指标分母见 CSV / 完整报告。</p></section>
<section class="panel"><h2>逐条核对：输入 → 预测 → 答案</h2><div class="controls"><label><span>方法</span><select id="method"></select></label><label><span>随机种子</span><select id="seed"></select></label><label><span>测试样例</span><select id="sample"></select></label></div><div id="error"></div><div id="context" class="context"></div><div class="outcomes"><div class="outcome"><h3>方法输出</h3><div id="prediction"></div></div><div class="outcome gold"><h3>独立保存的脚本答案</h3><div id="gold"></div></div></div><h3>截止前事件</h3><label class="toggle"><input type="checkbox" id="full-history">显示完整来源历史（包含未传给窗口方法的前缀）</label><div class="scroll"><table><thead><tr><th>时间 / ID</th><th>事件 / 步骤</th><th>人物接触 / 理解</th><th>观察证据</th><th>本方法输入</th></tr></thead><tbody id="events"></tbody></table></div><details><summary>查看完整记录、输入指纹与输出</summary><pre id="raw"></pre></details></section>
<p class="footnote">这是已保存结果的静态快照；切换选择不会重新调用模型。共享脚本模板的工程验收结果不能支持真实人类预测、新算法优势或跨域泛化结论。完整可追溯信息见同目录 manifest.json、status.json、predictions.jsonl。</p>
</main><script type="application/json" id="dashboard-data">__PAYLOAD__</script><script>
"use strict";
const D=JSON.parse(document.getElementById('dashboard-data').textContent), records=new Map(D.records.map(x=>[x.sample_id,x])), golds=new Map(D.golds.map(x=>[x.sample_id,x]));
const $=id=>document.getElementById(id), label={resume:'恢复',not_resume:'不恢复',censored:'后续观察不足（删失）',unknown:'无法辨认（未知）'};
function text(node,value){node.textContent=value===null||value===undefined?'—':String(value);}
function option(select,value,name){const o=document.createElement('option');o.value=String(value);o.textContent=name;select.appendChild(o);}
function facts(node,entries){node.replaceChildren();const dl=document.createElement('dl');for(const [key,value] of entries){const dt=document.createElement('dt'),dd=document.createElement('dd');text(dt,key);text(dd,value);dl.append(dt,dd);}node.appendChild(dl);}
const pct=p=>p===null||p===undefined?'—':(100*p).toFixed(1)+'%';
for(const row of D.table)option($('method'),row.method_id,row.method_id+' · '+row.name+'（'+row.status_text+'）');
const seeds=[...new Set(D.predictions.map(x=>x.seed))].sort((a,b)=>a-b);for(const seed of seeds)option($('seed'),seed,String(seed));
for(const record of D.records)option($('sample'),record.sample_id,record.sample_id+' · '+record.domain);
function refresh(){const method=$('method').value,seed=$('seed').value,sid=$('sample').value,record=records.get(sid),gold=golds.get(sid),row=D.predictions.find(x=>x.method_id===method&&String(x.seed)===seed&&x.sample_id===sid),meta=D.table.find(x=>x.method_id===method);if(!record||!gold){text($('context'),'本快照没有可显示的测试记录。');return;}const p=row&&row.prediction;const error=row&&row.error||(row?null:'本方法 / 种子没有保存该样例的预测。');$('error').style.display=error?'block':'none';text($('error'),error);facts($('prediction'),[['运行状态',row?({'ok':'成功','error':'错误','unavailable':'待接入'}[row.status]||row.status):'缺失'],['恢复判断',p?label[p.resume_label]:null],['恢复步骤',p&&p.resume_step],['恢复概率',p?pct(p.p_resume):null],['原因',p&&p.reason]]);const excluded=gold.resume_label==='censored'||gold.resume_label==='unknown'||(gold.dataset_layer==='P1'&&!gold.window_complete&&gold.resume_label==='not_resume');facts($('gold'),[['未来窗口',label[gold.resume_label]],['实际恢复步骤',gold.resume_step],['窗口完整',gold.window_complete?'是':'否'],['T1 统计',excluded?'排除：观察不足或答案未知':'纳入'],['截止状态',Object.entries(gold.state_labels||{}).map(([k,v])=>k+'='+v).join('；')]]);text($('context'),'人物：'+record.person_id+'　|　目标：'+record.observation.goal_id+'　|　截止：'+record.observation.cutoff+'　|　范围：'+record.observation.horizon.value+' 个'+(record.observation.horizon.type==='seconds'?'秒':'决策机会')+'　|　记录层：'+gold.dataset_layer);const actual=new Set(row?row.actual_input_event_ids:record.observation.events.map(x=>x.event_id));$('events').replaceChildren();for(const e of record.observation.events){const included=actual.has(e.event_id);if(!included&&!$('full-history').checked)continue;const tr=document.createElement('tr');if(!included)tr.className='discarded';const values=[String(e.time)+' / '+e.event_id,((e.semantic||{}).kind||e.event_type)+(e.step_id?' · '+e.step_id:''),e.person_access_evidence.status+' / '+(e.person_access_evidence.understood===true?'明确理解':e.person_access_evidence.understood===false?'未确认理解':'未知'),e.observer_evidence,included?'已提供':'已截去'];for(const value of values){const td=document.createElement('td');text(td,value);tr.appendChild(td);}$('events').appendChild(tr);}text($('raw'),JSON.stringify({record,gold,prediction_row:row||null},null,2));}
for(const id of ['method','seed','sample','full-history'])$(id).addEventListener('change',refresh);refresh();
</script></body></html>'''
    boundary = ("全部答案与截止状态来自合成脚本，仅验收工程流程。正式 P0/P1、真实 LLM / MENTIS 与 A 的模型，以实际运行状态为准。"
                if is_fixture else "本页显示已保存的运行数据。样本来源、标签证据、数据许可及结论范围必须与完整报告一致。")
    replacements = {"__DATE__": _escape(date), "__LAYER_TITLE__": _escape(layer_title),
                    "__BOUNDARY__": _escape(boundary), "__CARDS__": cards, "__CHART__": _chart(table),
                    "__ROWS__": "".join(rows), "__PAYLOAD__": _json_script(payload),
                    "__REPORT__": _escape(links["report"]), "__CSV__": _escape(links["csv"]),
                    "__SUMMARY__": _escape(links["summary"])}
    # Replace each original token once; user data containing token text is never rescanned.
    import re
    return re.sub("|".join(map(re.escape, replacements)), lambda match: replacements[match.group()], template)


def build(results_dir=None, inputs=None, labels=None, output_html=None):
    directory = Path(results_dir or ROOT / "results" / "full_run").resolve()
    inputs, labels = Path(inputs or ROOT / "data" / "integration" / "inputs.jsonl"), Path(labels or ROOT / "data" / "integration" / "labels.jsonl")
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8-sig"))
    summary, manifest, status = read("summary.json"), read("manifest.json"), read("status.json")
    if file_hash(inputs) != manifest["inputs_sha256"] or file_hash(labels) != manifest["labels_sha256"]:
        raise ValueError("Input/label files differ from the actual run manifest; refusing a misleading dashboard")
    payload = make_payload(summary, manifest, status, load_jsonl(directory / "predictions.jsonl"),
                           load_jsonl(inputs), load_jsonl(labels))
    output = Path(output_html or directory / "demo.html").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "metrics.csv"
    links = {key: os.path.relpath(path, output.parent).replace("\\", "/")
             for key, path in {"report": directory / "report.md", "csv": csv_path,
                               "summary": directory / "summary.json"}.items()}
    output.write_text(render_dashboard(payload, links), encoding="utf-8")
    csv_path.write_text(_csv_text(payload["table"]), encoding="utf-8-sig")
    return {"html": str(output), "csv": str(csv_path), "n_methods": len(payload["table"]),
            "n_predictions": len(payload["predictions"]), "dataset_layer": payload["dataset_layer"]}


def self_test():
    malicious = '</script><script>alert("escaped")</script>&\u2028'
    payload = make_payload({"dataset_layer": "integration_fixture", "aggregate": {"B8": {
        "n_seeds": 1, "metrics": {"accuracy_all_eligible": {"mean": None}}}}, "runs": []},
        {"train_n": 1, "test_n": 1}, {"methods": {"B8": {"status": "unavailable", "reason": malicious}}}, [], [], [])
    rendered = render_dashboard(payload)
    assert malicious not in rendered
    assert rendered.count("</script>") == 2
    assert "\\u003c/script\\u003e" in rendered
    assert "src=" not in rendered
    csv_result = list(csv.DictReader(io.StringIO(_csv_text(payload["table"]))))
    assert csv_result[0]["accuracy_mean"] == ""
    assert csv_result[0]["status"] == "unavailable"
    assert _percent(0) == "0.0%" and _percent(None) == "—"
    print("Dashboard self-test passed: script escaping, offline assets, null CSV and zero distinction.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--output-html", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        print(json.dumps(build(args.results_dir, args.inputs, args.labels, args.output_html),
                         ensure_ascii=False, indent=2))
