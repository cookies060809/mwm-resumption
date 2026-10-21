"""Build the P0 uncertainty candidate batch (batch v0.3, schema p0-record/v0.2.0).

v0.2 reaches its 240-record target while 11 uncertainty-bearing enum values stay
empty, so the filter can be trained on data where every fact is CERTAIN, every
delivery succeeds and every commitment is observable. Those 11 slots are the gap
A reported; this batch fills them with paired families instead of more volume.

Every UNKNOWN here is a scripted epistemic predicament, never an annotator's
gap: `validate_data.check_record` forces UNKNOWN to carry no evidence and forces
UNCERTAIN/UNRESOLVED/ACTIVE to carry at least one, so a lazy label fails
validation rather than silently shipping. See handbook section 1.4.

Drafting was done by an agent (commit c27f3cd) and B ticked both spot-audit
worksheets on 2026-10-21, so the batch now carries B's sign-off exactly like
v0.2 does: `annotator_id` names the person accountable for the labels, not the
keyboard. `second_reviewer_id` stays null because the A/C blind review is a
separate worksheet and has not happened yet.

Usage: python scripts/build_p0_uncertainty.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "p0" / "p0_samples_v0.3.json"

ANNOTATED_AT = "2026-10-21"
ANNOTATOR = "B"
REVIEWED_AT = "2026-10-21"
SEMANTIC_NONE = {"kind": "none", "value": None, "interpretation": "none"}


def ev(
    event_id: str,
    time: str,
    actor: str,
    event_type: str,
    goal: str | None,
    step: str | None,
    access: str,
    description: str,
    *,
    world: str | None = None,
    obs: str | None = None,
    acc_ev: str | None = None,
    source: str = "direct_observation",
    certainty: str = "CERTAIN",
    comp: str = "NOT_APPLICABLE",
    sem: dict[str, Any] | None = None,
    supports: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "time": time,
        "actor": actor,
        "event_type": event_type,
        "goal_id": goal,
        "step_id": step,
        "person_access": access,
        "person_comprehension": comp,
        "person_available_semantics": sem or dict(SEMANTIC_NONE),
        "world_effect": world,
        "observer_evidence": obs,
        "person_access_evidence": acc_ev,
        "source": source,
        "certainty": certainty,
        "description": description,
        "_supports": set(supports),
    }


def cancel_notice(
    event_id: str,
    time: str,
    access: str,
    certainty: str,
    acc_ev: str,
    text: str,
    comp: str = "NOT_APPLICABLE",
) -> dict[str, Any]:
    return ev(
        event_id,
        time,
        "system",
        "notification_sent",
        None,
        None,
        access,
        text,
        world="取消通知已发出。",
        obs="外发日志有记录。",
        acc_ev=acc_ev,
        source="notification",
        certainty=certainty,
        comp=comp,
        sem={"kind": "cancellation", "value": "任务已取消", "interpretation": "none"},
        supports=("A",),
    )


def build_family(
    family: str,
    domain: str,
    mechanism: str,
    split: str,
    goal_id: str,
    goal_description: str,
    steps: list[str],
    dependencies: list[dict[str, str]],
    completed: list[str],
    variants: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for variant in ("A", "B"):
        spec = variants[variant]
        events = [dict(event) for event in spec["events"]]
        if any(event["time"] > events[index + 1]["time"] for index, event in enumerate(events[:-1])):
            raise ValueError(f"{family}-{variant}: event times are not ordered")
        for index, event in enumerate(events, start=1):
            event["goal_id"] = event["goal_id"] or (goal_id if event["actor"] == "person" else None)
            event["event_id"] = f"e{index:02d}"

        evidence = {factor: [] for factor in ("V", "F", "A", "B", "C", "Q")}
        for event in events:
            for factor in event.pop("_supports"):
                evidence[factor].append(event["event_id"])
        ordered_ids = [event["event_id"] for event in events]
        flat = [
            event_id
            for event_id in ordered_ids
            if any(event_id in ids for ids in evidence.values())
        ]
        state = spec["state"]
        for factor, value in state.items():
            if value != "UNKNOWN" and not evidence[factor]:
                raise ValueError(f"{family}-{variant}: {factor}={value} has no evidence event")
            if value == "UNKNOWN" and factor != "Q" and evidence[factor]:
                raise ValueError(f"{family}-{variant}: {factor}=UNKNOWN carries evidence")

        record = {
            "schema_version": "p0-record/v0.2.0",
            "sample_id": f"{family}-{variant}",
            "base_story_id": family,
            "variant": variant,
            "split": split,
            "domain": domain,
            "mechanism": mechanism,
            "goal_id": goal_id,
            "goal_description": goal_description,
            "cutoff_event_id": ordered_ids[-1],
            "horizon": spec.get("horizon", {"type": "decision_opportunities", "value": 3}),
            "task_steps": steps,
            "task_dependencies": dependencies,
            "completed_steps_at_cutoff": completed,
            "observed_events": events,
            "state_at_cutoff": state,
            "state_evidence_event_ids": flat,
            "state_evidence_by_factor": evidence,
            "p0_scripted_policy": spec["policy"],
            "p0_expected_action": spec["action"],
            "p0_expected": spec["expected"],
            "p0_design": spec["design"],
            "p1_observed_resume": None,
            "p1_observed_first_step": None,
            "p1_censoring_status": "not_collected",
            "annotation": {
                "annotator_id": ANNOTATOR,
                "status": "reviewed",
                "source_confidence": "high",
                "annotated_at": ANNOTATED_AT,
                "reviewed_at": REVIEWED_AT,
                "second_reviewer_id": None,
            },
            "notes": spec["notes"],
        }
        if spec.get("interruption"):
            record["interruption"] = spec["interruption"]
        records.append(record)
    return records


def person(
    event_id,
    time,
    event_type,
    step,
    description,
    *,
    world=None,
    supports=(),
    obs="观察者直接观察",
    acc_ev="人物本人执行或陈述",
    **kw,
):
    return ev(
        event_id, time, "person", event_type, None, step, "ACCESSED", description,
        world=world, obs=obs, acc_ev=acc_ev, supports=supports, **kw
    )


FAMILIES: list[dict[str, Any]] = [
    # 1) A=UNCERTAIN + event person_access=UNCERTAIN + event certainty=UNCERTAIN
    {
        "family": "P01-W6",
        "domain": "work",
        "mechanism": "contact_cancellation",
        "split": "train",
        "goal_id": "expense_E42",
        "goal_description": "提交报销单 E42：收齐票据、填写报销表单、送审。",
        "steps": ["collect_receipts", "fill_expense_form", "submit_approval"],
        "dependencies": [
            {"before": "collect_receipts", "after": "fill_expense_form"},
            {"before": "fill_expense_form", "after": "submit_approval"},
        ],
        "completed": ["collect_receipts"],
        "variants": {
            "A": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "UNCERTAIN",
                    "B": "UNKNOWN", "C": "SUSPENDED", "Q": "fill_expense_form",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "resume_fill_expense_form",
                "expected": {
                    "resume_within_horizon": True,
                    "first_step": "fill_expense_form",
                    "behavior_note": "接触不可确认时按未收到取消处理，从第一个未完成步骤继续。",
                },
                "design": {
                    "manipulated_factor": "取消通知的投递回执完整度",
                    "paired_variable": "P01-W6-B（回执完整）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "standup_meeting",
                    "demand_level": "medium",
                    "goal_priority": "high",
                },
                "events": [
                    person("x", "09:00", "goal_start", None, "开始处理报销单 E42。",
                           world="目标激活。", supports=("V",)),
                    person("x", "09:20", "step_completed", "collect_receipts",
                           "票据收齐。报销系统与打印机均可访问。",
                           world="collect_receipts 完成；后续条件就绪。", supports=("Q", "F")),
                    person("x", "09:30", "interruption_started", "fill_expense_form",
                           "被拉去站会，报销表单填写暂停。",
                           world="原目标因 standup_meeting 暂停。", supports=("C",)),
                    ev("x", "09:40", "system", "task_cancelled", "expense_E42", None,
                       "NOT_ACCESSED", "财务在后台把报销单 E42 撤销。",
                       world="报销单 E42 客观已撤销。", obs="后台记录确认。",
                       acc_ev="人物不在场，无接触通道。", source="backend_record",
                       supports=("V",)),
                    cancel_notice(
                        "x", "09:41", "UNCERTAIN", "UNCERTAIN",
                        "外发日志有记录，但没有终端接收回执；该时段网关超时状态未知。",
                        "系统向人物推送报销单撤销通知，投递结果不明。",
                    ),
                ],
                "notes": (
                    "P01-W6-A：撤销通知投递结果不明 → A=UNCERTAIN（证据=通知事件本身）；"
                    "人物无陈述无行动 → B=UNKNOWN（无任何 B 证据）。"
                ),
            },
            "B": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "UNKNOWN", "C": "SUSPENDED", "Q": "fill_expense_form",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：投递可确认，接触通道与 A 臂唯一不同。",
                },
                "design": {
                    "manipulated_factor": "取消通知的投递回执完整度",
                    "paired_variable": "P01-W6-A（回执不明）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "standup_meeting",
                    "demand_level": "medium",
                    "goal_priority": "high",
                },
                "events": [
                    person("x", "09:00", "goal_start", None, "开始处理报销单 E42。",
                           world="目标激活。", supports=("V",)),
                    person("x", "09:20", "step_completed", "collect_receipts",
                           "票据收齐。报销系统与打印机均可访问。",
                           world="collect_receipts 完成；后续条件就绪。", supports=("Q", "F")),
                    person("x", "09:30", "interruption_started", "fill_expense_form",
                           "被拉去站会，报销表单填写暂停。",
                           world="原目标因 standup_meeting 暂停。", supports=("C",)),
                    ev("x", "09:40", "system", "task_cancelled", "expense_E42", None,
                       "NOT_ACCESSED", "财务在后台把报销单 E42 撤销。",
                       world="报销单 E42 客观已撤销。", obs="后台记录确认。",
                       acc_ev="人物不在场，无接触通道。", source="backend_record",
                       supports=("V",)),
                    cancel_notice(
                        "x", "09:41", "ACCESSED", "CERTAIN",
                        "终端接收回执已记录；人物抬头看了通知栏。",
                        "系统向人物推送报销单撤销通知，人物已接收。",
                        comp="UNCERTAIN",
                    ),
                ],
                "notes": (
                    "P01-W6-B：与 A 臂只差 e05 的投递可确认性（person_access / certainty，"
                    "以及由此带出的 comprehension 档），其余事件与状态完全同构。"
                ),
            },
        },
    },
    # 2) B=UNRESOLVED + event certainty=PROBABLE
    {
        "family": "P01-S6",
        "domain": "collaboration_service",
        "mechanism": "contact_cancellation",
        "split": "train",
        "goal_id": "order_O55",
        "goal_description": "完成订单 O55 的分拣、包装与出库登记。",
        "steps": ["pick_items", "pack_order", "register_outbound"],
        "dependencies": [
            {"before": "pick_items", "after": "pack_order"},
            {"before": "pack_order", "after": "register_outbound"},
        ],
        "completed": ["pick_items"],
        "variants": {
            "A": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "UNRESOLVED", "C": "SUSPENDED", "Q": "pack_order",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "取消通知已确认送达且被正确理解，政策据此不续做；矛盾转述让人物信念未调和，本臂留在原地等确认。",
                },
                "design": {
                    "manipulated_factor": "是否存在与后台记录矛盾的第二来源通知",
                    "paired_variable": "P01-S6-B（只有后台记录）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "rush_ticket",
                    "demand_level": "high",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "14:00", "goal_start", None, "开始处理订单 O55。",
                           world="目标激活。"),
                    person("x", "14:10", "step_completed", "pick_items",
                           "拣货完成，包装台可用。",
                           world="pick_items 完成；包装材料充足。", supports=("F",)),
                    person("x", "14:20", "interruption_started", "pack_order",
                           "被叫去处理加急工单，包装暂停。",
                           world="原目标因 rush_ticket 暂停。", supports=("C", "Q")),
                    ev("x", "14:30", "system", "task_cancelled", "order_O55", None,
                       "ACCESSED", "订单系统把 O55 取消并推送通知，人物点开。",
                       world="订单 O55 客观已取消。", obs="后台记录确认。",
                       acc_ev="人物点击了取消通知。", source="backend_record",
                       sem={"kind": "cancellation", "value": "订单已取消", "interpretation": "accurate"},
                       comp="UNDERSTOOD", supports=("V", "A")),
                    ev("x", "14:35", "manager", "notification_sent", "order_O55", None,
                       "ACCESSED", "主管口头转述“O55 客户又说要，先别撤”",
                       world="主管的说法不改变后台记录。", obs="观察者听到原话。",
                       acc_ev="人物当面听到。", source="third_party_report",
                       certainty="PROBABLE",
                       sem={"kind": "cancellation", "value": "客户撤回取消", "interpretation": "unresolved"},
                       comp="UNCERTAIN", supports=("A", "B")),
                    person("x", "14:36", "person_statement", "pack_order",
                           "人物说“到底是撤还是不撤？我等一下确认再说。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           acc_ev="人物本人陈述。", source="person_report",
                           supports=("B",)),
                ],
                "notes": (
                    "P01-S6-A：两条矛盾通知均 ACCESSED，人物明确表示未调和 → B=UNRESOLVED"
                    "（有证据，非标注者未知）；主管转述属 third_party_report → certainty=PROBABLE。"
                    "两臂期望动作同为 do_not_resume：本对操控的是信念是否调和这一状态维度，动作标签刻意保持不变。"
                ),
            },
            "B": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_INVALID", "C": "SUSPENDED", "Q": "pack_order",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：无矛盾来源，人物形成稳定信念“已取消”。",
                },
                "design": {
                    "manipulated_factor": "是否存在与后台记录矛盾的第二来源通知",
                    "paired_variable": "P01-S6-A（存在矛盾转述）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "rush_ticket",
                    "demand_level": "high",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "14:00", "goal_start", None, "开始处理订单 O55。",
                           world="目标激活。"),
                    person("x", "14:10", "step_completed", "pick_items",
                           "拣货完成，包装台可用。",
                           world="pick_items 完成；包装材料充足。", supports=("F",)),
                    person("x", "14:20", "interruption_started", "pack_order",
                           "被叫去处理加急工单，包装暂停。",
                           world="原目标因 rush_ticket 暂停。", supports=("C", "Q")),
                    ev("x", "14:30", "system", "task_cancelled", "order_O55", None,
                       "ACCESSED", "订单系统把 O55 取消并推送通知，人物点开。",
                       world="订单 O55 客观已取消。", obs="后台记录确认。",
                       acc_ev="人物点击了取消通知。", source="backend_record",
                       sem={"kind": "cancellation", "value": "订单已取消", "interpretation": "accurate"},
                       comp="UNDERSTOOD", supports=("V", "A")),
                    person("x", "14:36", "person_statement", "pack_order",
                           "人物说“O55 取消了，那我不包了。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           acc_ev="人物本人陈述。", source="person_report",
                           supports=("B", "Q")),
                ],
                "notes": (
                    "P01-S6-B：去掉矛盾转述后，同一条取消通知形成稳定的 BELIEVES_INVALID，"
                    "把 UNRESOLVED 这一档隔离出来。"
                ),
            },
        },
    },
    # 3) F=UNKNOWN
    {
        "family": "P05-D6",
        "domain": "daily_life",
        "mechanism": "resource_availability",
        "split": "train",
        "goal_id": "laundry_L07",
        "goal_description": "洗完并烘干一筐衣物。",
        "steps": ["load_washer", "run_wash", "run_dry", "fold_clothes"],
        "dependencies": [
            {"before": "load_washer", "after": "run_wash"},
            {"before": "run_wash", "after": "run_dry"},
            {"before": "run_dry", "after": "fold_clothes"},
        ],
        "completed": ["load_washer", "run_wash"],
        "variants": {
            "A": {
                "state": {
                    "V": "VALID", "F": "UNKNOWN", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "run_dry",
                },
                "policy": "execute_if_ready_else_wait",
                "action": "wait_for_tool",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "烘干机状态从未被观察到，正确行为是先确认再动作。",
                },
                "design": {
                    "manipulated_factor": "烘干设备状态是否在 cutoff 前可观察",
                    "paired_variable": "P05-D6-B（观察到设备故障）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "doorbell_delivery",
                    "demand_level": "low",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "08:00", "goal_start", None, "开始洗一筐衣物。",
                           world="目标激活。", supports=("V",)),
                    person("x", "08:05", "step_completed", "load_washer", "装洗衣机完成。",
                           world="load_washer 完成。"),
                    person("x", "08:50", "step_completed", "run_wash", "洗涤程序结束。",
                           world="run_wash 完成。", supports=("Q", "A")),
                    person("x", "08:55", "interruption_started", "run_dry", "门铃响，去收快递。",
                           world="原目标因 doorbell_delivery 暂停。", supports=("C",)),
                    person("x", "09:00", "person_statement", "run_dry",
                           "人物说“洗完了，等下拿去烘干。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("B",)),
                ],
                "notes": (
                    "P05-D6-A：cutoff 前没有任何 resource_available / resource_missing 事件，"
                    "F 无证据 → F=UNKNOWN（不是“B 没想”，而是脚本刻意不暴露设备状态）。"
                    "A=ACCESSED 只指人物接触到自己这侧的进度通道，不代表收到烘干机状态。"
                ),
            },
            "B": {
                "state": {
                    "V": "VALID", "F": "BLOCKED", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "run_dry",
                },
                "policy": "execute_if_ready_else_wait",
                "action": "wait_for_tool",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：观察到烘干机故障，等待修好而非反复尝试。",
                },
                "design": {
                    "manipulated_factor": "烘干设备状态是否在 cutoff 前可观察",
                    "paired_variable": "P05-D6-A（状态不可观察）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "doorbell_delivery",
                    "demand_level": "low",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "08:00", "goal_start", None, "开始洗一筐衣物。",
                           world="目标激活。", supports=("V",)),
                    person("x", "08:05", "step_completed", "load_washer", "装洗衣机完成。",
                           world="load_washer 完成。"),
                    person("x", "08:50", "step_completed", "run_wash", "洗涤程序结束。",
                           world="run_wash 完成。", supports=("Q", "A")),
                    person("x", "08:55", "interruption_started", "run_dry", "门铃响，去收快递。",
                           world="原目标因 doorbell_delivery 暂停。", supports=("C",)),
                    person("x", "09:00", "person_statement", "run_dry",
                           "人物说“洗完了，等下拿去烘干。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("B",)),
                    ev("x", "09:05", "environment", "resource_missing", "laundry_L07", "run_dry",
                       "NOT_ACCESSED", "烘干机报错 E21，暂时无法启动。",
                       world="run_dry 的前置条件不满足。", obs="观察者直接观察报错面板。",
                       acc_ev="人物尚未接触该信息。", source="sensor_log",
                       sem={"kind": "resource_missing", "value": "烘干机故障 E21", "interpretation": "none"},
                       supports=("F",)),
                ],
                "notes": "P05-D6-B：同一蓝图多一条 resource_missing，F=BLOCKED，与 A 臂隔离“可观察性”这一因子。",
            },
        },
    },
    # 4) person_comprehension=NOT_UNDERSTOOD
    {
        "family": "P08-W7",
        "domain": "work",
        "mechanism": "comprehension",
        "split": "dev",
        "goal_id": "shift_S12",
        "goal_description": "将周三班次调整为与同事对调并报备主管。",
        "steps": ["draft_swap_request", "get_colleague_confirm", "report_manager"],
        "dependencies": [
            {"before": "draft_swap_request", "after": "get_colleague_confirm"},
            {"before": "get_colleague_confirm", "after": "report_manager"},
        ],
        "completed": ["draft_swap_request"],
        "variants": {
            "A": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_INVALID", "C": "ABANDONED", "Q": "NOT_APPLICABLE",
                },
                "policy": "act_on_believed_status",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：人物正确理解“对调已被驳回”，不再推进。",
                },
                "design": {
                    "manipulated_factor": "人物对驳回通知的理解是否正确",
                    "paired_variable": "P08-W7-B（收到但没看懂）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "customer_call",
                    "demand_level": "medium",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "11:00", "goal_start", None, "开始办周三班次对调。",
                           world="目标激活。", supports=("V",)),
                    person("x", "11:10", "step_completed", "draft_swap_request",
                           "对调申请已填写。", world="draft_swap_request 完成。", supports=("Q",)),
                    person("x", "11:20", "interruption_started", "get_colleague_confirm",
                           "接客户电话，对调流程暂停。",
                           world="原目标因 customer_call 暂停。"),
                    ev("x", "11:30", "system", "task_cancelled", "shift_S12", None,
                       "ACCESSED", "排班系统驳回并关闭该对调申请。",
                       world="对调目标客观已取消。", obs="后台记录确认。",
                       acc_ev="人物读完全文并复述：“对调没批，流程关了。”",
                       source="notification",
                       sem={"kind": "cancellation", "value": "对调申请被驳回关闭", "interpretation": "accurate"},
                       comp="UNDERSTOOD", supports=("V", "A", "B", "Q")),
                    person("x", "11:32", "person_statement", None,
                           "人物说“对调驳回了，那这周就不办了。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("C", "B", "Q")),
                    ev("x", "11:35", "system", "resource_available", "shift_S12", None,
                       "NOT_ACCESSED", "排班系统正常可访问。",
                       world="继续执行的条件满足。", obs="系统状态面板。",
                       acc_ev="人物未查看。", source="backend_record", supports=("F",)),
                ],
                "notes": (
                    "P08-W7-A：V=CANCELLED 且人物理解到位 → 目标被放弃，C=ABANDONED；"
                    "按 §1.4，C=ABANDONED/COMPLETED 时进度不再适用，故 Q=NOT_APPLICABLE，"
                    "并用 e02/e04/e05 作为“进度已不适用”的证据。与 B 臂只差 e04 的 comprehension。"
                ),
            },
            "B": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "get_colleague_confirm",
                },
                "policy": "act_on_believed_status",
                "action": "suspend_or_wait",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "人物收到驳回通知但没看懂，仍把对调当作未完成的目标；cutoff 时保持暂停等待，不在视野内推进步骤。",
                },
                "design": {
                    "manipulated_factor": "人物对驳回通知的理解是否正确",
                    "paired_variable": "P08-W7-A（正确理解）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "customer_call",
                    "demand_level": "medium",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "11:00", "goal_start", None, "开始办周三班次对调。",
                           world="目标激活。", supports=("V",)),
                    person("x", "11:10", "step_completed", "draft_swap_request",
                           "对调申请已填写。", world="draft_swap_request 完成。", supports=("Q",)),
                    person("x", "11:20", "interruption_started", "get_colleague_confirm",
                           "接客户电话，对调流程暂停。",
                           world="原目标因 customer_call 暂停。", supports=("C",)),
                    ev("x", "11:30", "system", "task_cancelled", "shift_S12", None,
                       "ACCESSED", "排班系统驳回并关闭该对调申请。",
                       world="对调目标客观已取消。", obs="后台记录确认。",
                       acc_ev="人物点开了通知，但只回一句“这写的什么没看懂”。",
                       source="notification",
                       sem={"kind": "cancellation", "value": "对调申请被驳回关闭", "interpretation": "none"},
                       comp="NOT_UNDERSTOOD", supports=("V", "A")),
                    person("x", "11:32", "person_statement", "get_colleague_confirm",
                           "人物说“没看懂那条通知，先去找小李确认下时间。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("B", "Q")),
                    ev("x", "11:35", "system", "resource_available", "shift_S12", None,
                       "NOT_ACCESSED", "排班系统正常可访问。",
                       world="继续执行的条件满足。", obs="系统状态面板。",
                       acc_ev="人物未查看。", source="backend_record", supports=("F",)),
                ],
                "notes": "P08-W7-B：person_access=ACCESSED 但 person_comprehension=NOT_UNDERSTOOD → 接触不等于理解；人物仍把对调当作有效目标，cutoff 时保持暂停（与 v0.2 的 15 个误解臂同为 suspend_or_wait）。",
            },
        },
    },
    # 5) person_comprehension=UNCERTAIN
    {
        "family": "P08-S7",
        "domain": "collaboration_service",
        "mechanism": "comprehension",
        "split": "dev",
        "goal_id": "install_I21",
        "goal_description": "上门安装净水器并完成使用讲解与签单。",
        "steps": ["unpack_device", "mount_filter", "explain_usage", "sign_ticket"],
        "dependencies": [
            {"before": "unpack_device", "after": "mount_filter"},
            {"before": "mount_filter", "after": "explain_usage"},
            {"before": "explain_usage", "after": "sign_ticket"},
        ],
        "completed": ["unpack_device"],
        "variants": {
            "A": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_INVALID", "C": "ABANDONED", "Q": "NOT_APPLICABLE",
                },
                "policy": "act_on_believed_status",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：人物正确理解“工单改派”，放弃本单。",
                },
                "design": {
                    "manipulated_factor": "接收后是否有可核查的理解证据",
                    "paired_variable": "P08-S7-B（收到但无从判定理解）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "client_paperwork",
                    "demand_level": "low",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "15:00", "goal_start", None, "开始上门安装净水器。",
                           world="目标激活。"),
                    person("x", "15:10", "step_completed", "unpack_device", "设备开箱完成。",
                           world="unpack_device 完成。", supports=("Q",)),
                    ev("x", "15:12", "system", "resource_available", "install_I21", "mount_filter",
                       "NOT_ACCESSED", "工具与水质检测条件均满足。",
                       world="继续执行的条件满足。", obs="工具清点表确认。",
                       acc_ev="人物未查看清点表。", source="backend_record", supports=("F",)),
                    person("x", "15:20", "interruption_started", "mount_filter",
                           "客户叫到门口核对前置单据，安装暂停。",
                           world="原目标因 client_paperwork 暂停。", supports=("C", "Q")),
                    ev("x", "15:25", "system", "task_cancelled", "install_I21", None,
                       "ACCESSED", "派工系统把这单改派给另一位安装工并关闭了工单。",
                       world="安装目标客观已取消。", obs="后台记录确认。",
                       acc_ev="人物复述：“这单转给别人了，我不用装了，对吧？”",
                       source="notification",
                       sem={"kind": "cancellation", "value": "工单改派并关闭", "interpretation": "accurate"},
                       comp="UNDERSTOOD", supports=("V", "A", "B", "Q")),
                    person("x", "15:27", "person_statement", None,
                           "人物说“改派了？那这单我不跟了。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("C", "B", "Q")),
                ],
                "notes": (
                    "P08-S7-A：接收且有正确复述 → comprehension=UNDERSTOOD；按 v0.2 的 comprehension "
                    "惯例，理解到位的一臂 C=ABANDONED、Q=NOT_APPLICABLE、do_not_resume。"
                ),
            },
            "B": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "UNKNOWN", "C": "SUSPENDED", "Q": "mount_filter",
                },
                "policy": "act_on_believed_status",
                "action": "suspend_or_wait",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "工单关闭通知确认送达，但之后没有任何陈述或行动可反映理解程度。",
                },
                "design": {
                    "manipulated_factor": "接收后是否有可核查的理解证据",
                    "paired_variable": "P08-S7-A（有正确复述）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "client_paperwork",
                    "demand_level": "low",
                    "goal_priority": "medium",
                },
                "events": [
                    person("x", "15:00", "goal_start", None, "开始上门安装净水器。",
                           world="目标激活。"),
                    person("x", "15:10", "step_completed", "unpack_device", "设备开箱完成。",
                           world="unpack_device 完成。", supports=("Q",)),
                    ev("x", "15:12", "system", "resource_available", "install_I21", "mount_filter",
                       "NOT_ACCESSED", "工具与水质检测条件均满足。",
                       world="继续执行的条件满足。", obs="工具清点表确认。",
                       acc_ev="人物未查看清点表。", source="backend_record", supports=("F",)),
                    person("x", "15:20", "interruption_started", "mount_filter",
                           "客户叫到门口核对前置单据，安装暂停。",
                           world="原目标因 client_paperwork 暂停。", supports=("C", "Q")),
                    ev("x", "15:25", "system", "task_cancelled", "install_I21", None,
                       "ACCESSED", "派工系统把这单改派给另一位安装工并关闭了工单。",
                       world="安装目标客观已取消。", obs="推送记录 + 已读回执。",
                       acc_ev="已读回执存在，但之后人物没有陈述也没有任何动作。",
                       source="notification",
                       sem={"kind": "cancellation", "value": "工单改派并关闭", "interpretation": "none"},
                       comp="UNCERTAIN", supports=("V", "A")),
                ],
                "notes": (
                    "P08-S7-B：person_access=ACCESSED 但理解无通道可核查 → "
                    "person_comprehension=UNCERTAIN，B 只能 UNKNOWN（缺的证据是人物对改派通知的任何陈述）。"
                    "Q 不跟着写 UNKNOWN：人物自己完成过 unpack_device、在 mount_filter 被打断，步骤线索还在。"
                    "本臂比 A 臂少 1 个事件——设计要点就是“通知之后什么都不发生”，不补中性事件凑条数。"
                ),
            },
        },
    },
    # 6) C=ACTIVE 与 C=UNKNOWN
    {
        "family": "P02-D7",
        "domain": "daily_life",
        "mechanism": "long_term_commitment",
        "split": "test",
        "goal_id": "shelf_H03",
        "goal_description": "周末把书房的置物架装好并把书归位。",
        "steps": ["carry_parts_inside", "assemble_frame", "anchor_to_wall", "put_books_back"],
        "dependencies": [
            {"before": "carry_parts_inside", "after": "assemble_frame"},
            {"before": "assemble_frame", "after": "anchor_to_wall"},
            {"before": "anchor_to_wall", "after": "put_books_back"},
        ],
        "completed": ["carry_parts_inside"],
        "variants": {
            "A": {
                "state": {
                    "V": "VALID", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "ACTIVE", "Q": "assemble_frame",
                },
                "policy": "resume_if_committed_and_unfinished",
                "action": "resume_assemble_frame",
                "expected": {
                    "resume_within_horizon": True,
                    "first_step": "assemble_frame",
                    "behavior_note": "人物明确表达仍然要做，且中途回头查看零件。",
                },
                "design": {
                    "manipulated_factor": "承诺是否留下可观察证据",
                    "paired_variable": "P02-D7-B（无承诺也无放弃的证据）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": "e07",
                    "duration_minutes": 25,
                    "interrupting_task": "lunch_invite",
                    "demand_level": "low",
                    "goal_priority": "low",
                },
                "events": [
                    person("x", "10:00", "goal_start", None, "开始装书房置物架。",
                           world="目标激活。", supports=("V", "B")),
                    person("x", "10:10", "step_completed", "carry_parts_inside", "板材与五金搬进书房。",
                           world="carry_parts_inside 完成。", supports=("Q",)),
                    ev("x", "10:12", "environment", "resource_available", "shelf_H03", "assemble_frame",
                       "ACCESSED", "电动螺丝刀电量充足，工具在桌上。",
                       world="assemble_frame 的前置条件满足。", obs="观察者直接观察。",
                       acc_ev="人物拿起了工具。", source="direct_observation", supports=("F", "A")),
                    person("x", "10:20", "interruption_started", "assemble_frame",
                           "家人喊先去吃饭。", world="原目标因 lunch_invite 暂停。"),
                    person("x", "10:21", "commitment_expressed", "assemble_frame",
                           "人物说“架子今天必须装完，吃完回来接着干。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("C", "B")),
                    person("x", "10:25", "person_action", "assemble_frame",
                           "出门前人物回头把板材靠墙立好，避免被踩。",
                           world="未改变世界状态。", obs="观察者直接观察。",
                           source="direct_observation", supports=("C", "Q")),
                    person("x", "10:45", "return_to_task", "assemble_frame",
                           "人物回到书房，站在板材前。", world="cutoff 时刻。",
                           obs="观察者直接观察。", source="direct_observation", supports=("Q",)),
                ],
                "notes": (
                    "P02-D7-A：明确承诺 + 保护材料的持续行动 → C=ACTIVE（v0.2 的 240 条里 C 从未取过 ACTIVE）。"
                ),
            },
            "B": {
                "state": {
                    "V": "VALID", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "UNKNOWN", "Q": "assemble_frame",
                },
                "policy": "resume_if_committed_and_unfinished",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "cutoff 前没有任何承诺、放弃或完成的证据，政策前置条件不满足 → 不恢复。这是对策略的判定，不是断言人物已放弃。",
                },
                "design": {
                    "manipulated_factor": "承诺是否留下可观察证据",
                    "paired_variable": "P02-D7-A（有承诺与持续行动）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e04",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "lunch_invite",
                    "demand_level": "low",
                    "goal_priority": "low",
                },
                "events": [
                    person("x", "10:00", "goal_start", None, "开始装书房置物架。",
                           world="目标激活。", supports=("V", "B")),
                    person("x", "10:10", "step_completed", "carry_parts_inside", "板材与五金搬进书房。",
                           world="carry_parts_inside 完成。", supports=("Q",)),
                    ev("x", "10:12", "environment", "resource_available", "shelf_H03", "assemble_frame",
                       "ACCESSED", "电动螺丝刀电量充足，工具在桌上。",
                       world="assemble_frame 的前置条件满足。", obs="观察者直接观察。",
                       acc_ev="人物拿起了工具。", source="direct_observation", supports=("F", "A")),
                    person("x", "10:20", "interruption_started", "assemble_frame",
                           "家人喊先去吃饭。", world="原目标因 lunch_invite 暂停。"),
                    person("x", "10:21", "person_statement", None,
                           "人物“哦”了一声就走出书房，之后没有任何后续动作或陈述。",
                           world="未改变世界状态。", obs="观察者直接观察。",
                           source="person_report"),
                ],
                "notes": (
                    "P02-D7-B：既无承诺陈述也无持续行动，也没有放弃或完成的信号 → C=UNKNOWN，"
                    "校验强制该因子的证据列表为空；“暂停不等于放弃”，所以不写 SUSPENDED。"
                    "B 仍取 BELIEVES_VALID，证据是 e01 目标激活（沿用 v0.2 惯例：人物开始做该目标本身就是信念证据），"
                    "“哦”一声不改变它。信念有效不等于承诺仍在，两个因子各自取证。"
                    "Q 仍是 assemble_frame：搬板材这一步是人物自己做完的，步骤线索并没有消失。"
                ),
            },
        },
    },
    # 7) V=UNKNOWN（世界事实未定，但脚本策略仍可判定点标签）
    {
        "family": "P01-W8",
        "domain": "work",
        "mechanism": "contact_cancellation",
        "split": "test",
        "goal_id": "audit_A09",
        "goal_description": "准备季度审计材料包并递交给合规组。",
        "steps": ["gather_records", "build_summary", "submit_package"],
        "dependencies": [
            {"before": "gather_records", "after": "build_summary"},
            {"before": "build_summary", "after": "submit_package"},
        ],
        "completed": ["gather_records"],
        "variants": {
            "A": {
                "state": {
                    "V": "UNKNOWN", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "build_summary",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "resume_build_summary",
                "expected": {
                    "resume_within_horizon": True,
                    "first_step": "build_summary",
                    "behavior_note": "V 未定但没有任何已确认的取消：政策条件“无已知取消”成立，从第一个未完成步骤继续。",
                },
                "design": {
                    "manipulated_factor": "取消申请是否在 cutoff 前得到后台确认",
                    "paired_variable": "P01-W8-B（确认已到达）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "incident_response",
                    "demand_level": "high",
                    "goal_priority": "high",
                },
                "events": [
                    person("x", "13:00", "goal_start", None, "开始准备季度审计材料包。", world="目标激活。"),
                    person("x", "13:30", "step_completed", "gather_records", "原始凭证已取到。",
                           world="gather_records 完成；台账系统可访问。", supports=("Q", "F")),
                    person("x", "13:40", "interruption_started", "build_summary",
                           "线上故障，人物被拉去处理事故。",
                           world="原目标因 incident_response 暂停。", supports=("C",)),
                    ev("x", "13:50", "manager", "notification_sent", None, None,
                       "ACCESSED", "合规同事口头转述“审计那边好像提了个取消，还没批”",
                       world="转述本身不改变世界状态。", obs="观察者听到原话。",
                       acc_ev="人物当面听到。", source="third_party_report",
                       certainty="UNCERTAIN",
                       sem={"kind": "cancellation", "value": "取消申请提交但未确认", "interpretation": "unresolved"},
                       comp="UNCERTAIN", supports=("A",)),
                    person("x", "13:55", "person_statement", "build_summary",
                           "人物说“应该还是要做的，先把汇总写完。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("B", "Q")),
                ],
                "notes": (
                    "P01-W8-A：脚本未固定世界事实——没有任何 task_cancelled / task_completed_by_other 事件，"
                    "只有一条 certainty=UNCERTAIN 的转述，不足以判定 V，因此 V=UNKNOWN 且 V 证据为空。"
                    "V 未定 ≠ 标签未定：政策看的是“有没有已知取消”，答案是没有，所以期望动作仍是恢复 "
                    "build_summary，而不是 indeterminate（indeterminate 只用于输入不可区分的家族）。"
                    "V 未定也无法断言人物理解错，故该转述 comprehension=UNCERTAIN 而非 MISUNDERSTOOD。"
                ),
            },
            "B": {
                "state": {
                    "V": "CANCELLED", "F": "READY", "A": "ACCESSED",
                    "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": "build_summary",
                },
                "policy": "continue_if_no_known_cancellation",
                "action": "do_not_resume",
                "expected": {
                    "resume_within_horizon": False,
                    "first_step": None,
                    "behavior_note": "对照臂：后台确认撤销已到达，客观 V=CANCELLED，仍有人物滞后信念。",
                },
                "design": {
                    "manipulated_factor": "取消申请是否在 cutoff 前得到后台确认",
                    "paired_variable": "P01-W8-A（从未确认）",
                    "undefined_target": False,
                },
                "interruption": {
                    "start_event_id": "e03",
                    "end_event_id": None,
                    "duration_minutes": None,
                    "interrupting_task": "incident_response",
                    "demand_level": "high",
                    "goal_priority": "high",
                },
                "events": [
                    person("x", "13:00", "goal_start", None, "开始准备季度审计材料包。", world="目标激活。"),
                    person("x", "13:30", "step_completed", "gather_records", "原始凭证已取到。",
                           world="gather_records 完成；台账系统可访问。", supports=("Q", "F")),
                    person("x", "13:40", "interruption_started", "build_summary",
                           "线上故障，人物被拉去处理事故。",
                           world="原目标因 incident_response 暂停。", supports=("C",)),
                    ev("x", "13:50", "system", "task_cancelled", "audit_A09", None,
                       "ACCESSED", "合规系统确认季度审计材料包已撤销。",
                       world="审计材料包目标客观已取消。", obs="后台记录确认。",
                       acc_ev="人物看到了确认通知，但以为是“暂停”。", source="backend_record",
                       sem={"kind": "cancellation", "value": "审计已撤销", "interpretation": "defer"},
                       comp="MISUNDERSTOOD", supports=("V", "A")),
                    person("x", "13:55", "person_statement", "build_summary",
                           "人物说“先缓缓，回头再做汇总。”",
                           world="未改变世界状态。", obs="观察者听到原话。",
                           source="person_report", supports=("B", "Q")),
                ],
                "notes": (
                    "P01-W8-B：同一蓝图补上后台确认 → V 从 UNKNOWN 变 CANCELLED，"
                    "人物因 interpretation=defer 仍 BELIEVES_VALID，隔离“世界事实是否可判定”这一因子。"
                ),
            },
        },
    },
]


def build() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in FAMILIES:
        records.extend(
            build_family(
                spec["family"], spec["domain"], spec["mechanism"], spec["split"],
                spec["goal_id"], spec["goal_description"], spec["steps"],
                spec["dependencies"], spec["completed"], spec["variants"],
            )
        )
    return records


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    records = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # .gitattributes pins *.json to LF; without newline="\n" Windows writes CRLF
    # and the CI reproducibility check shows a spurious whole-file diff.
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(records)} records to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
