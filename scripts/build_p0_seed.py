"""Build the P0 seed batch (P01-P08, A/B pairs).

This is a reproducibility helper for the first handoff only. The output is
data/p0/p0_samples.json. P0 labels are scripted expectations, not human data.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "p0" / "p0_samples.json"

SCHEMA_VERSION = "p0-record/v0.1.0"
ANNOTATION = {
    "annotator_id": "B",
    "status": "draft",
    "source_confidence": "medium",
    "annotated_at": "2026-10-20",
}


def ev(
    event_id,
    time,
    actor,
    event_type,
    goal_id,
    step_id,
    person_access,
    description,
    world_effect=None,
    observer_evidence=None,
    person_access_evidence=None,
    source="direct_observation",
    certainty="CERTAIN",
):
    return {
        "event_id": event_id,
        "time": time,
        "actor": actor,
        "event_type": event_type,
        "goal_id": goal_id,
        "step_id": step_id,
        "person_access": person_access,
        "world_effect": world_effect,
        "observer_evidence": observer_evidence,
        "person_access_evidence": person_access_evidence,
        "source": source,
        "certainty": certainty,
        "description": description,
    }


def person(
    event_id,
    time,
    event_type,
    goal_id,
    step_id,
    description,
    world_effect=None,
    observer_evidence="观察者直接观察",
    person_access_evidence="人物本人执行或陈述",
    source="direct_observation",
    certainty="CERTAIN",
):
    return ev(
        event_id,
        time,
        "person",
        event_type,
        goal_id,
        step_id,
        "ACCESSED",
        description,
        world_effect,
        observer_evidence,
        person_access_evidence,
        source,
        certainty,
    )


def background(
    event_id,
    time,
    actor,
    event_type,
    goal_id,
    step_id,
    person_access,
    description,
    world_effect=None,
    observer_evidence=None,
    person_access_evidence=None,
    source="backend_record",
    certainty="CERTAIN",
):
    return ev(
        event_id,
        time,
        actor,
        event_type,
        goal_id,
        step_id,
        person_access,
        description,
        world_effect,
        observer_evidence,
        person_access_evidence,
        source,
        certainty,
    )


def deps(*pairs):
    return [{"before": before, "after": after} for before, after in pairs]


def make_record(
    base_story_id,
    variant,
    domain,
    goal_id,
    goal_description,
    cutoff_event_id,
    task_steps,
    task_dependencies,
    completed_steps_at_cutoff,
    observed_events,
    state_at_cutoff,
    state_evidence_by_factor,
    p0_scripted_policy,
    p0_expected_action,
    p0_expected,
    interruption=None,
    interrupting_task=None,
    notes="",
):
    ordered_ids = [event["event_id"] for event in observed_events]
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError(f"{base_story_id}-{variant}: duplicate event_id")
    if ordered_ids[-1] != cutoff_event_id:
        raise ValueError(f"{base_story_id}-{variant}: cutoff must be last event")
    for factor, ids in state_evidence_by_factor.items():
        unknown = [event_id for event_id in ids if event_id not in ordered_ids]
        if unknown:
            raise ValueError(
                f"{base_story_id}-{variant}: {factor} references unknown events {unknown}"
            )
    flat_evidence = [
        event_id
        for event_id in ordered_ids
        if any(event_id in ids for ids in state_evidence_by_factor.values())
    ]
    record = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": f"{base_story_id}-{variant}",
        "base_story_id": base_story_id,
        "variant": variant,
        "domain": domain,
        "goal_id": goal_id,
        "goal_description": goal_description,
        "cutoff_event_id": cutoff_event_id,
        "horizon": {"type": "decision_opportunities", "value": 3},
        "task_steps": task_steps,
        "task_dependencies": task_dependencies,
        "completed_steps_at_cutoff": completed_steps_at_cutoff,
        "observed_events": observed_events,
        "state_at_cutoff": state_at_cutoff,
        "state_evidence_event_ids": flat_evidence,
        "state_evidence_by_factor": state_evidence_by_factor,
        "p0_scripted_policy": p0_scripted_policy,
        "p0_expected_action": p0_expected_action,
        "p0_expected": p0_expected,
        "p1_observed_resume": None,
        "p1_censoring_status": "not_collected",
        "annotation": ANNOTATION,
    }
    if interruption is not None:
        record["interruption"] = interruption
    if interrupting_task is not None:
        record["interrupting_task"] = interrupting_task
    if notes:
        record["notes"] = notes
    return record


def p01():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "order_O17",
            None,
            "开始处理订单 O17。",
            "目标激活；订单 O17 处理中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "order_O17",
            "verify_address",
            "核对收货地址完成。",
            "verify_address 完成。",
        ),
        person(
            "e03",
            "10:02",
            "step_started",
            "order_O17",
            "pack_item",
            "开始包装商品；包装台工具可用。",
            "pack_item 进行中；包装工具可用。",
        ),
        person(
            "e04",
            "10:03",
            "interruption_started",
            "order_O17",
            "pack_item",
            "接听客服电话，暂停包装。",
            "原目标因 support_call 暂停。",
        ),
        background(
            "e05",
            "10:04",
            "customer",
            "task_cancelled",
            "order_O17",
            None,
            "NOT_ACCESSED",
            "客户在后台取消订单 O17。",
            "订单 O17 状态=CANCELLED。",
            "后台订单记录",
            "仅后台记录，无人物可见通知",
            "backend_record",
        ),
    ]
    notification_a = ev(
        "e06",
        "10:05",
        "system",
        "notification_sent",
        "order_O17",
        None,
        "ACCESSED",
        "取消通知显示在人物屏幕上；人物打开并确认取消。",
        "通知已显示并被人物确认。",
        "通知投递日志",
        "屏幕显示，人物点击确认",
        "notification",
    )
    notification_b = ev(
        "e06",
        "10:05",
        "system",
        "notification_sent",
        "order_O17",
        None,
        "NOT_ACCESSED",
        "取消通知仅进入后台运营队列；工作台无可见或可听提示。",
        "通知仅进入后台运营队列。",
        "通知投递日志",
        "未投递到任何人物可见通道",
        "notification",
    )
    tail = [
        person(
            "e07",
            "10:06",
            "interruption_ended",
            "order_O17",
            "pack_item",
            "电话结束。",
            "中断结束。",
        ),
        person(
            "e08",
            "10:07",
            "return_to_task",
            "order_O17",
            "pack_item",
            "人物回到同一工作台。",
            "人物位于工作台，处于决策点。",
        ),
    ]
    steps = ["verify_address", "pack_item", "print_label"]
    dependencies = deps(("verify_address", "pack_item"), ("pack_item", "print_label"))
    interruption = {
        "start_event_id": "e04",
        "end_event_id": "e07",
        "duration_minutes": 3,
        "interrupting_task": "support_call",
        "demand_level": "medium",
        "goal_priority": "high",
    }

    a = make_record(
        "P01",
        "A",
        "collaboration_service",
        "order_O17",
        "完成订单 O17 的地址核对、包装与运单打印。",
        "e08",
        steps,
        dependencies,
        ["verify_address"],
        common + [notification_a] + tail,
        {
            "V": "CANCELLED",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_INVALID",
            "C": "ABANDONED",
            "Q": "NOT_APPLICABLE",
        },
        {
            "V": ["e05"],
            "F": ["e03"],
            "A": ["e06"],
            "B": ["e06"],
            "C": ["e06"],
            "Q": ["e06"],
        },
        "continue_if_no_known_cancellation",
        "do_not_resume",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "人物已确认取消，按脚本策略停止原任务。",
        },
        interruption=interruption,
        notes="P01-A：人物确认取消通知；V=CANCELLED 且 B=BELIEVES_INVALID，预期不恢复。",
    )
    b = make_record(
        "P01",
        "B",
        "collaboration_service",
        "order_O17",
        "完成订单 O17 的地址核对、包装与运单打印。",
        "e08",
        steps,
        dependencies,
        ["verify_address"],
        common + [notification_b] + tail,
        {
            "V": "CANCELLED",
            "F": "READY",
            "A": "NOT_ACCESSED",
            "B": "UNKNOWN",
            "C": "SUSPENDED",
            "Q": "pack_item",
        },
        {
            "V": ["e05"],
            "F": ["e03"],
            "A": ["e05", "e06"],
            "B": [],
            "C": ["e04"],
            "Q": ["e03", "e04"],
        },
        "continue_if_no_known_cancellation",
        "resume_pack_item",
        {
            "resume_within_horizon": True,
            "first_step": "pack_item",
            "behavior_note": "人物未接触取消通知，按旧信息继续包装。",
        },
        interruption=interruption,
        notes="P01-B：人物未接触取消通知；B=UNKNOWN，按旧信息恢复包装。",
    )
    return [a, b]


def p02():
    common = [
        person(
            "e01",
            "08:40",
            "goal_start",
            "report_R12",
            None,
            "开始撰写月度报告 R12。",
            "目标激活；报告 R12 处理中。",
        ),
        person(
            "e02",
            "08:50",
            "step_completed",
            "report_R12",
            "collect_data",
            "资料收集完成。",
            "collect_data 完成。",
        ),
        ev(
            "e04",
            "09:30",
            "other",
            "interruption_started",
            "report_R12",
            None,
            "ACCESSED",
            "人物去参加团队会议。",
            "team_meeting 开始。",
            "观察者看到人物进入会议室",
            "人物进入并参与会议",
            "direct_observation",
        ),
        person(
            "e05",
            "10:00",
            "interruption_ended",
            "report_R12",
            None,
            "会议结束。",
            "中断结束。",
        ),
        person(
            "e06",
            "10:02",
            "return_to_task",
            "report_R12",
            None,
            "人物回到工位。",
            "人物回到工位。",
        ),
        person(
            "e07",
            "10:03",
            "person_action",
            "report_R12",
            None,
            "人物坐下并打开电脑。",
            None,
        ),
        person(
            "e08",
            "10:05",
            "person_action",
            "report_R12",
            None,
            "人物浏览屏幕，处于决策点。",
            "到达预测截断点。",
        ),
    ]
    early_a = person(
        "e03",
        "09:00",
        "commitment_expressed",
        "report_R12",
        None,
        "人物明确说：开完会后继续写第三节。",
        "人物对报告 R12 作出继续承诺。",
        observer_evidence="人物当面明确陈述",
        person_access_evidence="人物明确自述",
        source="person_report",
    )
    early_b = person(
        "e03",
        "09:00",
        "goal_abandoned",
        "report_R12",
        None,
        "人物明确说：我放弃报告 R12，不再继续。",
        "人物明确放弃报告 R12。",
        observer_evidence="人物当面明确陈述",
        person_access_evidence="人物明确自述",
        source="person_report",
    )
    steps = ["collect_data", "draft_section_3", "revise_section_3", "submit_report"]
    dependencies = deps(
        ("collect_data", "draft_section_3"),
        ("draft_section_3", "revise_section_3"),
        ("revise_section_3", "submit_report"),
    )
    interruption = {
        "start_event_id": "e04",
        "end_event_id": "e05",
        "duration_minutes": 30,
        "interrupting_task": "team_meeting",
        "demand_level": "high",
        "goal_priority": "medium",
    }

    a = make_record(
        "P02",
        "A",
        "work",
        "report_R12",
        "完成月度报告 R12 的第三节并提交。",
        "e08",
        steps,
        dependencies,
        ["collect_data"],
        common[:2] + [early_a] + common[2:],
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "draft_section_3",
        },
        {
            "V": ["e01"],
            "F": ["e01"],
            "A": ["e03"],
            "B": ["e01", "e03"],
            "C": ["e03", "e04"],
            "Q": ["e02"],
        },
        "resume_if_committed_and_unfinished",
        "resume_draft_section_3",
        {
            "resume_within_horizon": True,
            "first_step": "draft_section_3",
            "behavior_note": "人物早前明确承诺会后继续，按承诺恢复。",
        },
        interruption=interruption,
        notes="P02-A：早前明确承诺继续；最后五个事件与 B 相同，预期恢复。",
    )
    b = make_record(
        "P02",
        "B",
        "work",
        "report_R12",
        "完成月度报告 R12 的第三节并提交。",
        "e08",
        steps,
        dependencies,
        ["collect_data"],
        common[:2] + [early_b] + common[2:],
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "ABANDONED",
            "Q": "NOT_APPLICABLE",
        },
        {
            "V": ["e01"],
            "F": ["e01"],
            "A": ["e03"],
            "B": ["e01", "e03"],
            "C": ["e03"],
            "Q": ["e03"],
        },
        "resume_if_committed_and_unfinished",
        "do_not_resume",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "人物早前已明确放弃，尽管最近事件相同也不应恢复。",
        },
        interruption=interruption,
        notes="P02-B：早前明确放弃；最后五个事件与 A 相同，预期不恢复。",
    )
    return [a, b]


def p03():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "order_O21",
            None,
            "开始处理订单 O21。",
            "目标激活；订单 O21 处理中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "order_O21",
            "verify_address",
            "地址核对完成。",
            "verify_address 完成。",
        ),
        person(
            "e03",
            "10:04",
            "step_completed",
            "order_O21",
            "pack_item",
            "包装完成。",
            "pack_item 完成。",
        ),
    ]
    print_a = person(
        "e04",
        "10:06",
        "step_completed",
        "order_O21",
        "print_label",
        "人物打印并核对运单，确认打印完成。",
        "print_label 完成；运单已核对。",
    )
    print_b = person(
        "e04",
        "10:06",
        "step_attempted",
        "order_O21",
        "print_label",
        "人物准备打印；打印任务尚未触发，运单缺失，人物看到未完成状态。",
        "print job not triggered；运单缺失。",
    )
    tail = [
        person(
            "e05",
            "10:10",
            "interruption_started",
            "order_O21",
            None,
            "接听客户电话，暂停订单处理。",
            "原目标因 customer_call 暂停。",
        ),
        person(
            "e06",
            "10:13",
            "interruption_ended",
            "order_O21",
            None,
            "电话结束。",
            "中断结束。",
        ),
        person(
            "e07",
            "10:14",
            "return_to_task",
            "order_O21",
            None,
            "人物回到同一工作台。",
            "人物位于工作台，处于决策点。",
        ),
    ]
    steps = ["verify_address", "pack_item", "print_label", "handoff_courier"]
    dependencies = deps(
        ("verify_address", "pack_item"),
        ("pack_item", "print_label"),
        ("print_label", "handoff_courier"),
    )
    interruption = {
        "start_event_id": "e05",
        "end_event_id": "e06",
        "duration_minutes": 3,
        "interrupting_task": "customer_call",
        "demand_level": "medium",
        "goal_priority": "high",
    }

    a = make_record(
        "P03",
        "A",
        "collaboration_service",
        "order_O21",
        "完成订单 O21 的运单打印与快递交接。",
        "e07",
        steps,
        dependencies,
        ["verify_address", "pack_item", "print_label"],
        common + [print_a] + tail,
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "handoff_courier",
        },
        {
            "V": ["e01"],
            "F": ["e04"],
            "A": ["e04"],
            "B": ["e01", "e04"],
            "C": ["e05"],
            "Q": ["e04"],
        },
        "resume_at_first_incomplete_known_step",
        "resume_handoff_courier",
        {
            "resume_within_horizon": True,
            "first_step": "handoff_courier",
            "behavior_note": "运单已打印核对，首个未完成步骤是交接快递。",
        },
        interruption=interruption,
        notes="P03-A：中断前已打印并核对运单；恢复点为 handoff_courier。",
    )
    b = make_record(
        "P03",
        "B",
        "collaboration_service",
        "order_O21",
        "完成订单 O21 的运单打印与快递交接。",
        "e07",
        steps,
        dependencies,
        ["verify_address", "pack_item"],
        common + [print_b] + tail,
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "print_label",
        },
        {
            "V": ["e01"],
            "F": ["e04"],
            "A": ["e04"],
            "B": ["e01", "e04"],
            "C": ["e05"],
            "Q": ["e04"],
        },
        "resume_at_first_incomplete_known_step",
        "resume_print_label",
        {
            "resume_within_horizon": True,
            "first_step": "print_label",
            "behavior_note": "运单未打印且人物知情，首个未完成步骤是打印运单。",
        },
        interruption=interruption,
        notes="P03-B：中断前打印未执行且人物知情；恢复点为 print_label。",
    )
    return [a, b]


def p04():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "expense_E9",
            None,
            "开始处理报销单 E9。",
            "目标激活；报销单 E9 处理中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "expense_E9",
            "collect_receipts",
            "收集并整理发票。",
            "collect_receipts 完成。",
        ),
        person(
            "e03",
            "10:03",
            "step_started",
            "expense_E9",
            "fill_form",
            "开始填写报销表单。",
            "fill_form 进行中。",
        ),
        person(
            "e04",
            "10:04",
            "interruption_started",
            "expense_E9",
            "fill_form",
            "接听电话，暂停报销单处理。",
            "原目标因 phone_call 暂停。",
        ),
    ]
    completion_a = ev(
        "e05",
        "10:06",
        "colleague",
        "task_completed_by_other",
        "expense_E9",
        None,
        "ACCESSED",
        "同事完成并提交报销单；同事发消息告知人物，人物在电话中看到并回复。",
        "fill_form 与 submit_portal 完成；门户状态=SUBMITTED。",
        "门户提交记录与同事陈述",
        "同事消息送达并被人物回复",
        "third_party_report",
    )
    completion_b = ev(
        "e05",
        "10:06",
        "colleague",
        "task_completed_by_other",
        "expense_E9",
        None,
        "NOT_ACCESSED",
        "同事完成并提交报销单；同事未通知人物，随后离开；人物未查看门户。",
        "fill_form 与 submit_portal 完成；门户状态=SUBMITTED。",
        "门户提交记录与同事陈述",
        "无消息、无可见提示；人物未查看门户",
        "third_party_report",
    )
    tail = [
        person(
            "e06",
            "10:08",
            "interruption_ended",
            "expense_E9",
            "fill_form",
            "电话结束。",
            "中断结束。",
        ),
        person(
            "e07",
            "10:09",
            "return_to_task",
            "expense_E9",
            "fill_form",
            "人物回到工位。",
            "人物位于工位，处于决策点。",
        ),
    ]
    steps = ["collect_receipts", "fill_form", "submit_portal"]
    dependencies = deps(
        ("collect_receipts", "fill_form"),
        ("fill_form", "submit_portal"),
    )
    interruption = {
        "start_event_id": "e04",
        "end_event_id": "e06",
        "duration_minutes": 4,
        "interrupting_task": "phone_call",
        "demand_level": "medium",
        "goal_priority": "high",
    }

    a = make_record(
        "P04",
        "A",
        "work",
        "expense_E9",
        "提交报销单 E9。",
        "e07",
        steps,
        dependencies,
        ["collect_receipts", "fill_form", "submit_portal"],
        common + [completion_a] + tail,
        {
            "V": "FULFILLED",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "COMPLETED",
            "Q": "NOT_APPLICABLE",
        },
        {
            "V": ["e05"],
            "F": ["e02", "e05"],
            "A": ["e05"],
            "B": ["e01", "e05"],
            "C": ["e05"],
            "Q": ["e05"],
        },
        "avoid_repeat_if_known_completed",
        "do_not_resume",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "人物已知任务由同事完成，避免重复提交。",
        },
        interruption=interruption,
        notes="P04-A：人物被明确告知同事已完成；C=COMPLETED，预期不重复。",
    )
    b = make_record(
        "P04",
        "B",
        "work",
        "expense_E9",
        "提交报销单 E9。",
        "e07",
        steps,
        dependencies,
        ["collect_receipts", "fill_form", "submit_portal"],
        common + [completion_b] + tail,
        {
            "V": "FULFILLED",
            "F": "READY",
            "A": "NOT_ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "fill_form",
        },
        {
            "V": ["e05"],
            "F": ["e02", "e05"],
            "A": ["e05"],
            "B": ["e01", "e03"],
            "C": ["e03", "e04"],
            "Q": ["e03"],
        },
        "avoid_repeat_if_known_completed",
        "resume_fill_form",
        {
            "resume_within_horizon": True,
            "first_step": "fill_form",
            "behavior_note": "人物未获知完成事实，可能从 fill_form 重复推进。",
        },
        interruption=interruption,
        notes="P04-B：人物未获知同事已完成；C=SUSPENDED，可能重复推进。",
    )
    return [a, b]


def p05():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "chair_repair_R5",
            None,
            "开始修理松动椅架。",
            "目标激活；椅架修理进行中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "chair_repair_R5",
            "remove_old_bracket",
            "拆下旧支架。",
            "remove_old_bracket 完成。",
        ),
        person(
            "e03",
            "10:02",
            "interruption_started",
            "chair_repair_R5",
            None,
            "接听电话，暂停修理。",
            "原目标因 phone_call 暂停。",
        ),
        person(
            "e04",
            "10:05",
            "interruption_ended",
            "chair_repair_R5",
            None,
            "电话结束。",
            "中断结束。",
        ),
    ]
    tool_a = ev(
        "e05",
        "10:06",
        "environment",
        "resource_available",
        "chair_repair_R5",
        "attach_new_bracket",
        "ACCESSED",
        "工具盒中螺丝刀可见；人物拿起螺丝刀。",
        "screwdriver present。",
        "人物直接查看工具盒",
        "人物看到并拿起螺丝刀",
        "direct_observation",
    )
    tool_b = ev(
        "e05",
        "10:06",
        "environment",
        "resource_missing",
        "chair_repair_R5",
        "attach_new_bracket",
        "ACCESSED",
        "人物检查工具盒；螺丝刀缺失，空位清晰可见。",
        "screwdriver missing。",
        "人物直接查看工具盒",
        "人物看到空位并确认缺失",
        "direct_observation",
    )
    tail = [
        person(
            "e06",
            "10:07",
            "return_to_task",
            "chair_repair_R5",
            "attach_new_bracket",
            "人物回到椅架旁。",
            "人物位于任务点，处于决策点。",
        )
    ]
    steps = ["remove_old_bracket", "attach_new_bracket", "tighten_screws", "test_stability"]
    dependencies = deps(
        ("remove_old_bracket", "attach_new_bracket"),
        ("attach_new_bracket", "tighten_screws"),
        ("tighten_screws", "test_stability"),
    )
    interruption = {
        "start_event_id": "e03",
        "end_event_id": "e04",
        "duration_minutes": 3,
        "interrupting_task": "phone_call",
        "demand_level": "low",
        "goal_priority": "medium",
    }

    a = make_record(
        "P05",
        "A",
        "daily_life",
        "chair_repair_R5",
        "修好松动椅架。",
        "e06",
        steps,
        dependencies,
        ["remove_old_bracket"],
        common + [tool_a] + tail,
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "attach_new_bracket",
        },
        {
            "V": ["e01"],
            "F": ["e05"],
            "A": ["e05"],
            "B": ["e01"],
            "C": ["e03", "e05"],
            "Q": ["e02"],
        },
        "execute_if_ready_else_wait",
        "resume_attach_new_bracket",
        {
            "resume_within_horizon": True,
            "first_step": "attach_new_bracket",
            "behavior_note": "工具可用且人物知情，执行原步骤。",
        },
        interruption=interruption,
        notes="P05-A：工具可用；F=READY，预期执行 attach_new_bracket。",
    )
    b = make_record(
        "P05",
        "B",
        "daily_life",
        "chair_repair_R5",
        "修好松动椅架。",
        "e06",
        steps,
        dependencies,
        ["remove_old_bracket"],
        common + [tool_b] + tail,
        {
            "V": "VALID",
            "F": "BLOCKED",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "attach_new_bracket",
        },
        {
            "V": ["e01"],
            "F": ["e05"],
            "A": ["e05"],
            "B": ["e01"],
            "C": ["e03", "e05"],
            "Q": ["e02"],
        },
        "execute_if_ready_else_wait",
        "wait_for_tool",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "工具缺失且人物知情；保持目标但等待/寻找工具，H 内不执行原步骤。",
        },
        interruption=interruption,
        notes="P05-B：工具缺失；F=BLOCKED 且 C=SUSPENDED，预期等待而非执行。",
    )
    return [a, b]


def p06():
    common = [
        person(
            "e01",
            "09:00",
            "goal_start",
            "report_R7",
            None,
            "开始处理报告 R7。",
            "目标激活；报告 R7 处理中。",
        ),
        person(
            "e02",
            "09:05",
            "step_completed",
            "report_R7",
            "draft_intro",
            "完成报告引言。",
            "draft_intro 完成。",
        ),
        person(
            "e03",
            "09:15",
            "step_started",
            "report_R7",
            "analyze_data",
            "开始分析数据。",
            "analyze_data 进行中。",
        ),
        person(
            "e04",
            "09:20",
            "interruption_started",
            "report_R7",
            "analyze_data",
            "打印机卡纸，人物转向插入任务 fix_printer。",
            "report_R7 暂停；fix_printer 开始。",
        ),
        person(
            "e05",
            "09:22",
            "step_completed",
            "printer_P3",
            "clear_jam",
            "清除卡纸。",
            "clear_jam 完成。",
        ),
        person(
            "e06",
            "09:24",
            "step_started",
            "printer_P3",
            "replace_toner",
            "开始更换硒鼓。",
            "replace_toner 进行中。",
        ),
    ]
    printer_done = [
        person(
            "e07",
            "09:27",
            "step_completed",
            "printer_P3",
            "replace_toner",
            "更换硒鼓完成。",
            "replace_toner 完成。",
        ),
        person(
            "e08",
            "09:28",
            "step_completed",
            "printer_P3",
            "test_print",
            "测试打印成功。",
            "test_print 完成；fix_printer 完成。",
        ),
    ]
    printer_unfinished = [
        person(
            "e07",
            "09:27",
            "step_attempted",
            "printer_P3",
            "replace_toner",
            "硒鼓只装到一半；尚未完成时被电话打断。",
            "replace_toner 未完成；test_print 无法执行。",
        )
    ]
    nested_call = [
        ev(
            "e09",
            "09:30",
            "manager",
            "interruption_started",
            None,
            None,
            "ACCESSED",
            "经理来电，当前活动暂停。",
            "manager_call 开始。",
            "人物接听电话，观察者在场",
            "人物接听经理电话",
            "direct_observation",
        ),
        person(
            "e10",
            "09:40",
            "interruption_ended",
            None,
            None,
            "经理电话结束。",
            "manager_call 结束。",
        ),
        person(
            "e11",
            "09:41",
            "person_action",
            "report_R7",
            "analyze_data",
            "人物回到工作区，同时面对未完成的报告与打印机任务。",
            "到达预测截断点。",
        ),
    ]
    steps = ["draft_intro", "analyze_data", "write_conclusion", "submit_report"]
    dependencies = deps(
        ("draft_intro", "analyze_data"),
        ("analyze_data", "write_conclusion"),
        ("write_conclusion", "submit_report"),
    )
    interruption = {
        "start_event_id": "e04",
        "end_event_id": None,
        "duration_minutes": None,
        "interrupting_task": "fix_printer",
        "demand_level": "high",
        "goal_priority": "high",
    }
    task_done = {
        "task_id": "fix_printer",
        "goal_id": "printer_P3",
        "parent_goal_id": "report_R7",
        "steps": ["clear_jam", "replace_toner", "test_print"],
        "status_at_cutoff": "COMPLETED",
        "completed_steps_at_cutoff": ["clear_jam", "replace_toner", "test_print"],
    }
    task_unfinished = {
        "task_id": "fix_printer",
        "goal_id": "printer_P3",
        "parent_goal_id": "report_R7",
        "steps": ["clear_jam", "replace_toner", "test_print"],
        "status_at_cutoff": "IN_PROGRESS",
        "completed_steps_at_cutoff": ["clear_jam"],
    }

    a = make_record(
        "P06",
        "A",
        "work",
        "report_R7",
        "完成报告 R7；期间插入打印机维修任务。",
        "e11",
        steps,
        dependencies,
        ["draft_intro"],
        common + printer_done + nested_call,
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "analyze_data",
        },
        {
            "V": ["e01"],
            "F": ["e03"],
            "A": ["e07"],
            "B": ["e01"],
            "C": ["e04", "e09"],
            "Q": ["e03"],
        },
        "finish_nested_task_before_parent",
        "resume_analyze_data",
        {
            "resume_within_horizon": True,
            "first_step": "analyze_data",
            "behavior_note": "插入任务已完成，按脚本优先级回到原目标。",
        },
        interruption=interruption,
        interrupting_task=task_done,
        notes="P06-A：结束嵌套电话时 fix_printer 已完成；预期回到 report_R7。",
    )
    b = make_record(
        "P06",
        "B",
        "work",
        "report_R7",
        "完成报告 R7；期间插入打印机维修任务。",
        "e11",
        steps,
        dependencies,
        ["draft_intro"],
        common + printer_unfinished + nested_call,
        {
            "V": "VALID",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "analyze_data",
        },
        {
            "V": ["e01"],
            "F": ["e03"],
            "A": ["e07"],
            "B": ["e01"],
            "C": ["e04", "e09"],
            "Q": ["e03"],
        },
        "finish_nested_task_before_parent",
        "resume_replace_toner",
        {
            "resume_within_horizon": False,
            "first_step": "replace_toner",
            "behavior_note": "插入任务未完成；按脚本优先级先完成 fix_printer，H 内不恢复原目标。",
        },
        interruption=interruption,
        interrupting_task=task_unfinished,
        notes="P06-B：结束嵌套电话时 fix_printer 仍未完成；预期先完成插入任务。",
    )
    return [a, b]


def p07():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "order_O44",
            None,
            "开始处理订单 O44。",
            "目标激活；订单 O44 处理中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "order_O44",
            "verify_address",
            "核对收货地址完成。",
            "verify_address 完成。",
        ),
        person(
            "e03",
            "10:03",
            "step_started",
            "order_O44",
            "pack_item",
            "开始包装商品。",
            "pack_item 进行中。",
        ),
        person(
            "e04",
            "10:04",
            "interruption_started",
            "order_O44",
            "pack_item",
            "接听客服电话，暂停包装。",
            "原目标因 support_call 暂停。",
        ),
        person(
            "e05",
            "10:07",
            "interruption_ended",
            "order_O44",
            "pack_item",
            "电话结束。",
            "中断结束。",
        ),
        person(
            "e06",
            "10:08",
            "return_to_task",
            "order_O44",
            "pack_item",
            "人物回到同一工作台。",
            "人物位于工作台，处于决策点。",
        ),
    ]
    steps = ["verify_address", "pack_item", "print_label"]
    dependencies = deps(("verify_address", "pack_item"), ("pack_item", "print_label"))
    interruption = {
        "start_event_id": "e04",
        "end_event_id": "e05",
        "duration_minutes": 3,
        "interrupting_task": "support_call",
        "demand_level": "medium",
        "goal_priority": "high",
    }
    state = {
        "V": "VALID",
        "F": "READY",
        "A": "ACCESSED",
        "B": "BELIEVES_VALID",
        "C": "SUSPENDED",
        "Q": "pack_item",
    }
    evidence = {
        "V": ["e01"],
        "F": ["e03"],
        "A": ["e04", "e06"],
        "B": ["e01"],
        "C": ["e04"],
        "Q": ["e03"],
    }
    expected = {
        "resume_within_horizon": True,
        "first_step": "pack_item",
        "behavior_note": "截断点输入无已知阻碍，按脚本策略恢复包装；截断后设计结果不进入输入或标签。",
    }
    common_args = dict(
        base_story_id="P07",
        domain="collaboration_service",
        goal_id="order_O44",
        goal_description="完成订单 O44 的地址核对、包装与运单打印。",
        cutoff_event_id="e06",
        task_steps=steps,
        task_dependencies=dependencies,
        completed_steps_at_cutoff=["verify_address"],
        observed_events=common,
        state_at_cutoff=state,
        state_evidence_by_factor=evidence,
        p0_scripted_policy="resume_if_committed_and_unfinished",
        p0_expected_action="resume_pack_item",
        p0_expected=expected,
        interruption=interruption,
    )
    a = make_record(
        **common_args,
        variant="A",
        notes=(
            "P07-A：未来泄漏负对照。截断前输入与 P07-B 完全一致；"
            "设计上的截断后结果为人物恢复包装。截断后结果仅用于设计说明，绝不作为模型输入。"
        ),
    )
    b = make_record(
        **common_args,
        variant="B",
        notes=(
            "P07-B：未来泄漏负对照。截断前输入与 P07-A 完全一致；"
            "设计上的截断后结果为人物在 H 内不恢复。截断后结果仅用于设计说明，绝不作为模型输入。"
        ),
    )
    return [a, b]


def p08():
    common = [
        person(
            "e01",
            "10:00",
            "goal_start",
            "order_O33",
            None,
            "开始处理订单 O33。",
            "目标激活；订单 O33 处理中。",
        ),
        person(
            "e02",
            "10:01",
            "step_completed",
            "order_O33",
            "verify_address",
            "核对收货地址完成。",
            "verify_address 完成。",
        ),
        person(
            "e03",
            "10:02",
            "step_started",
            "order_O33",
            "pack_item",
            "开始包装商品。",
            "pack_item 进行中。",
        ),
        background(
            "e04",
            "10:03",
            "customer",
            "task_cancelled",
            "order_O33",
            None,
            "NOT_ACCESSED",
            "客户在后台取消订单 O33。",
            "订单 O33 状态=CANCELLED。",
            "后台订单记录",
            "仅后台记录，无人物可见通知",
            "backend_record",
        ),
        ev(
            "e05",
            "10:04",
            "system",
            "notification_sent",
            "order_O33",
            None,
            "ACCESSED",
            "通知文本：订单 O33 已取消；人物在屏幕上读到该通知。",
            "通知已显示；文本=order cancelled。",
            "通知投递日志与屏幕记录",
            "屏幕显示，人物阅读",
            "notification",
        ),
    ]
    statement_a = person(
        "e06",
        "10:05",
        "person_statement",
        "order_O33",
        "pack_item",
        "人物说：订单已取消，停止包装。",
        "人物正确理解取消。",
        observer_evidence="人物当面陈述",
        person_access_evidence="人物明确自述",
        source="person_report",
    )
    statement_b = person(
        "e06",
        "10:05",
        "person_statement",
        "order_O33",
        "pack_item",
        "人物说：通知说先暂缓，先把东西放一边等进一步通知。",
        "人物把取消误读为暂缓。",
        observer_evidence="人物当面陈述",
        person_access_evidence="人物明确自述",
        source="person_report",
    )
    tail = [
        person(
            "e07",
            "10:06",
            "interruption_started",
            "order_O33",
            "pack_item",
            "接听电话。",
            "原目标因 phone_call 暂停。",
        ),
        person(
            "e08",
            "10:09",
            "interruption_ended",
            "order_O33",
            "pack_item",
            "电话结束。",
            "中断结束。",
        ),
        person(
            "e09",
            "10:10",
            "return_to_task",
            "order_O33",
            "pack_item",
            "人物回到同一工作台。",
            "人物位于工作台，处于决策点。",
        ),
    ]
    steps = ["verify_address", "pack_item", "print_label"]
    dependencies = deps(("verify_address", "pack_item"), ("pack_item", "print_label"))
    interruption = {
        "start_event_id": "e07",
        "end_event_id": "e08",
        "duration_minutes": 3,
        "interrupting_task": "phone_call",
        "demand_level": "medium",
        "goal_priority": "high",
    }

    a = make_record(
        "P08",
        "A",
        "collaboration_service",
        "order_O33",
        "完成订单 O33 的地址核对、包装与运单打印。",
        "e09",
        steps,
        dependencies,
        ["verify_address"],
        common + [statement_a] + tail,
        {
            "V": "CANCELLED",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_INVALID",
            "C": "ABANDONED",
            "Q": "NOT_APPLICABLE",
        },
        {
            "V": ["e04"],
            "F": ["e03"],
            "A": ["e05"],
            "B": ["e05", "e06"],
            "C": ["e06"],
            "Q": ["e06"],
        },
        "act_on_believed_status",
        "do_not_resume",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "人物已读且正确理解取消，停止原任务。",
        },
        interruption=interruption,
        notes="P08-A：人物已读且正确理解取消；A=ACCESSED 且 B=BELIEVES_INVALID。",
    )
    b = make_record(
        "P08",
        "B",
        "collaboration_service",
        "order_O33",
        "完成订单 O33 的地址核对、包装与运单打印。",
        "e09",
        steps,
        dependencies,
        ["verify_address"],
        common + [statement_b] + tail,
        {
            "V": "CANCELLED",
            "F": "READY",
            "A": "ACCESSED",
            "B": "BELIEVES_VALID",
            "C": "SUSPENDED",
            "Q": "pack_item",
        },
        {
            "V": ["e04"],
            "F": ["e03"],
            "A": ["e05"],
            "B": ["e05", "e06"],
            "C": ["e06", "e07"],
            "Q": ["e03"],
        },
        "act_on_believed_status",
        "suspend_or_wait",
        {
            "resume_within_horizon": False,
            "first_step": None,
            "behavior_note": "人物把取消误读为暂缓；保持承诺但等待，不在 H 内继续包装。",
        },
        interruption=interruption,
        notes="P08-B：人物已读但误读为暂缓；A=ACCESSED 但 B=BELIEVES_VALID，C=SUSPENDED。",
    )
    return [a, b]


def main():
    records = []
    for builder in (p01, p02, p03, p04, p05, p06, p07, p08):
        records.extend(builder())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # .gitattributes pins *.json to LF; without newline="\n" Windows writes CRLF
    # and the "reproducible build" check shows a spurious whole-file diff.
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(records)} records to {OUT}")


if __name__ == "__main__":
    main()
