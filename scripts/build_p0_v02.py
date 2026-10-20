"""Build the ECR-MWM P0 v0.2 diagnostic batch (120 families / 240 records).

Design: 8 controlled mechanisms x 15 task blueprints = 120 families, each with an
A/B minimal pair. The 8 hand-written v0.1 seed families (P01-P08) are preserved
and upgraded in place; the other 112 families are generated from blueprint +
mechanism. Generation is deterministic and every record must pass
`python scripts/validate_data.py`.

Honest scope: this is scripted diagnostic data. Sentences follow per-mechanism
templates and vary by task blueprint and entity; it is not human behaviour and
must not be reported as real resumption prediction.

Usage:
    python scripts/build_p0_v02.py            # write data/p0/p0_samples_v0.2.json
    python scripts/build_p0_v02.py --check    # build in memory and validate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "p0" / "p0_samples.json"
OUT_PATH = ROOT / "data" / "p0" / "p0_samples_v0.2.json"
SCHEMA_VERSION = "p0-record/v0.2.0"
BUILD_DATE = "2026-10-20"

# ---------------------------------------------------------------- blueprints
# 15 task blueprints, 5 per domain. Each family reuses one blueprint's task
# structure but gets its own goal id, so families differ in task and entity,
# not only in wording.
BLUEPRINTS: list[dict[str, Any]] = [
    {
        "id": "W1",
        "domain": "work",
        "goal": "提交本月差旅报销（工单 BX-2041）",
        "doc": "报销工单 BX-2041",
        "steps": [
            ("collect_invoices", "收齐差旅发票"),
            ("fill_form", "填写报销单"),
            ("attach_scan", "扫描并上传附件"),
            ("submit_portal", "在财务门户提交"),
        ],
        "tool": "扫描仪",
        "colleague": "财务同事",
        "cause": "供应商电话打进来",
        "interrupt_actor": "customer",
    },
    {
        "id": "W2",
        "domain": "work",
        "goal": "安排候选人终面（候选人 C-118）",
        "doc": "面试安排 C-118",
        "steps": [
            ("confirm_slots", "确认双方可用时间"),
            ("book_room", "预订面试会议室"),
            ("send_invite", "发送日历邀请"),
            ("prep_questions", "准备面试提纲"),
        ],
        "tool": "会议室预订系统",
        "colleague": "HR 同事",
        "cause": "用人经理临时来问进度",
        "interrupt_actor": "manager",
    },
    {
        "id": "W3",
        "domain": "work",
        "goal": "完成季度数据报告（报告 R7）",
        "doc": "季度报告 R7",
        "steps": [
            ("pull_data", "从仓库拉取数据"),
            ("clean_data", "清洗异常值"),
            ("run_analysis", "运行分析脚本"),
            ("write_summary", "撰写结论部分"),
        ],
        "tool": "分析服务器",
        "colleague": "数据组同事",
        "cause": "部门临时周会",
        "interrupt_actor": "manager",
    },
    {
        "id": "W4",
        "domain": "work",
        "goal": "归档供应商合同（合同 HT-552）",
        "doc": "合同 HT-552",
        "steps": [
            ("check_signature", "核对签字页"),
            ("scan_copy", "扫描合同原件"),
            ("rename_file", "按规则重命名"),
            ("upload_archive", "上传归档库"),
        ],
        "tool": "扫描仪",
        "colleague": "行政同事",
        "cause": "快递员到前台取件",
        "interrupt_actor": "other",
    },
    {
        "id": "W5",
        "domain": "work",
        "goal": "提交产线检修申请（申请 MX-091）",
        "doc": "检修申请 MX-091",
        "steps": [
            ("inspect_fault", "记录故障现象"),
            ("fill_request", "填写检修申请"),
            ("get_approval", "取得班组长审批"),
            ("submit_maintenance", "提交检修系统"),
        ],
        "tool": "检修系统账号",
        "colleague": "班组长",
        "cause": "车间安全巡检叫停",
        "interrupt_actor": "manager",
    },
    {
        "id": "S1",
        "domain": "collaboration_service",
        "goal": "处理客户退换货工单（工单 CS-3312）",
        "doc": "售后工单 CS-3312",
        "steps": [
            ("verify_order", "核对原始订单"),
            ("check_policy", "核对退换政策"),
            ("create_return", "创建退货单"),
            ("notify_customer", "通知客户寄回"),
        ],
        "tool": "售后系统",
        "colleague": "售后同事",
        "cause": "客户电话插进来",
        "interrupt_actor": "customer",
    },
    {
        "id": "S2",
        "domain": "collaboration_service",
        "goal": "完成客户投诉回访（投诉 CMP-77）",
        "doc": "投诉单 CMP-77",
        "steps": [
            ("read_case", "阅读投诉记录"),
            ("call_customer", "电话回访客户"),
            ("log_result", "记录回访结果"),
            ("close_ticket", "关闭投诉工单"),
        ],
        "tool": "外呼系统",
        "colleague": "客服主管",
        "cause": "质检员来抽听录音",
        "interrupt_actor": "colleague",
    },
    {
        "id": "S3",
        "domain": "collaboration_service",
        "goal": "安排门店保养预约（预约 SV-208）",
        "doc": "预约单 SV-208",
        "steps": [
            ("check_capacity", "查询工位余量"),
            ("confirm_time", "与客户确认时间"),
            ("lock_slot", "锁定保养工位"),
            ("send_sms", "发送确认短信"),
        ],
        "tool": "排期系统",
        "colleague": "门店主管",
        "cause": "前台来了临时客户",
        "interrupt_actor": "customer",
    },
    {
        "id": "S4",
        "domain": "collaboration_service",
        "goal": "审核异常退款（退款 RF-1409）",
        "doc": "退款单 RF-1409",
        "steps": [
            ("match_orders", "匹配关联订单"),
            ("check_risk", "完成风控核验"),
            ("approve_refund", "提交审核结论"),
            ("notify_finance", "通知财务放款"),
        ],
        "tool": "风控后台",
        "colleague": "财务同事",
        "cause": "风控例会开始",
        "interrupt_actor": "manager",
    },
    {
        "id": "S5",
        "domain": "collaboration_service",
        "goal": "安排上门安装（安装单 IN-663）",
        "doc": "安装单 IN-663",
        "steps": [
            ("confirm_address", "确认安装地址"),
            ("check_parts", "核对配件清单"),
            ("schedule_visit", "约上门时间"),
            ("send_reminder", "发送上门提醒"),
        ],
        "tool": "配件库系统",
        "colleague": "安装师傅",
        "cause": "用户到店咨询",
        "interrupt_actor": "customer",
    },
    {
        "id": "D1",
        "domain": "daily_life",
        "goal": "准备周六家庭聚餐（聚餐 DN-12）",
        "doc": "聚餐清单 DN-12",
        "steps": [
            ("plan_menu", "定好菜单"),
            ("buy_groceries", "采购食材"),
            ("prep_ingredients", "洗切备菜"),
            ("cook_dishes", "下锅做菜"),
        ],
        "tool": "高压锅",
        "colleague": "家人",
        "cause": "孩子放学回家敲门",
        "interrupt_actor": "other",
    },
    {
        "id": "D2",
        "domain": "daily_life",
        "goal": "报修厨房漏水（报修 WX-58）",
        "doc": "报修单 WX-58",
        "steps": [
            ("photograph_leak", "拍照记录漏水点"),
            ("submit_request", "提交报修申请"),
            ("confirm_visit", "确认上门时间"),
            ("clear_access", "留出检修通道"),
        ],
        "tool": "物业 App",
        "colleague": "邻居",
        "cause": "物业电话回拨",
        "interrupt_actor": "other",
    },
    {
        "id": "D3",
        "domain": "daily_life",
        "goal": "预约年度体检（体检 TJ-30）",
        "doc": "体检预约 TJ-30",
        "steps": [
            ("choose_package", "选好体检套餐"),
            ("book_date", "选择体检日期"),
            ("prepare_docs", "准备证件和医保卡"),
            ("note_fasting", "记下空腹要求"),
        ],
        "tool": "体检预约平台",
        "colleague": "同事",
        "cause": "家人来电问行程",
        "interrupt_actor": "other",
    },
    {
        "id": "D4",
        "domain": "daily_life",
        "goal": "学完线上课程第三章（课程 PY-3）",
        "doc": "课程笔记 PY-3",
        "steps": [
            ("watch_lecture", "看完第三节视频"),
            ("do_exercise", "做完课后练习"),
            ("take_quiz", "完成章节测验"),
            ("write_notes", "整理课程笔记"),
        ],
        "tool": "课程平台",
        "colleague": "同班同学",
        "cause": "室友叫去取快递",
        "interrupt_actor": "other",
    },
    {
        "id": "D5",
        "domain": "daily_life",
        "goal": "打包书房物品（搬家 BJ-4）",
        "doc": "打包清单 BJ-4",
        "steps": [
            ("sort_books", "把书分类"),
            ("pack_boxes", "装箱封箱"),
            ("label_boxes", "贴上标签"),
            ("move_to_hall", "搬到客厅"),
        ],
        "tool": "封箱胶带",
        "colleague": "室友",
        "cause": "搬家师傅上门看楼层",
        "interrupt_actor": "other",
    },
]

NESTED_STEPS = [
    ("clear_jam", "清除卡纸"),
    ("replace_part", "更换耗材"),
    ("test_run", "试运行"),
]

MECHANISMS = [
    "contact_cancellation",
    "long_term_commitment",
    "resume_position",
    "other_completion",
    "resource_availability",
    "nested_interruption",
    "future_leak",
    "comprehension",
]

MECHANISM_LABEL = {
    "contact_cancellation": "取消通知是否到达人物",
    "long_term_commitment": "长期承诺与近期放弃",
    "resume_position": "中断前关键步骤是否完成且人物知情",
    "other_completion": "他人代完成后人物是否获知",
    "resource_availability": "必要条件可用或缺失（人物均知情）",
    "nested_interruption": "嵌套任务在截断时是否完成",
    "future_leak": "截断前输入相同、仅截断后设计结果不同",
    "comprehension": "同样接触到取消信息，理解或误解",
}

SEED_MECHANISM = {
    "P01": "contact_cancellation",
    "P02": "long_term_commitment",
    "P03": "resume_position",
    "P04": "other_completion",
    "P05": "resource_availability",
    "P06": "nested_interruption",
    "P07": "future_leak",
    "P08": "comprehension",
}


def ev(
    off: int,
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
    role: str | None = None,
) -> dict[str, Any]:
    return {
        "_off": off,
        "_supports": set(supports),
        "_role": role,
        "actor": actor,
        "event_type": event_type,
        "goal_id": goal,
        "step_id": step,
        "person_access": access,
        "person_comprehension": comp,
        "person_available_semantics": sem or {"kind": "none"},
        "world_effect": world,
        "observer_evidence": obs,
        "person_access_evidence": acc_ev,
        "source": source,
        "certainty": certainty,
        "description": description,
    }


def base_events(
    bp: dict[str, Any], gid: str, *, f_support: bool = True, b_support: bool = True
) -> list[dict[str, Any]]:
    steps = bp["steps"]
    return [
        ev(
            0,
            "person",
            "goal_start",
            gid,
            None,
            "ACCESSED",
            f"人物开始处理「{bp['goal']}」，{bp['doc']} 已建单。",
            world=f"{bp['doc']} 处于进行中",
            obs="任务系统建单记录",
            acc_ev="人物本人打开任务并在操作",
            comp="NOT_APPLICABLE",
            supports=("V", "C", "A"),
        ),
        ev(
            6,
            "person",
            "step_completed",
            gid,
            steps[0][0],
            "ACCESSED",
            f"完成「{steps[0][1]}」。",
            world=f"{steps[0][0]} 已完成",
            obs="操作日志",
            acc_ev="人物本人操作",
            supports=("Q", "F") if f_support else ("Q",),
        ),
        ev(
            12,
            "person",
            "step_started",
            gid,
            steps[1][0],
            "ACCESSED",
            f"开始「{steps[1][1]}」，进度停在这一步。",
            world=None,
            obs="操作日志",
            acc_ev="人物本人操作",
            supports=("Q", "C") + (("B",) if b_support else ()),
        ),
        ev(
            18,
            bp["interrupt_actor"],
            "interruption_started",
            gid,
            None,
            "ACCESSED",
            f"{bp['cause']}，正在进行的「{steps[1][1]}」被迫中断。",
            world=None,
            obs="现场观察",
            acc_ev="人物当场停下并应对",
            sem={"kind": "interruption"},
            supports=("C",),
            role="interrupt_start",
        ),
    ]


def closing_events(bp: dict[str, Any], gid: str) -> list[dict[str, Any]]:
    return [
        ev(
            30,
            bp["interrupt_actor"],
            "interruption_ended",
            gid,
            None,
            "ACCESSED",
            "打断结束，环境恢复安静。",
            world=None,
            obs="现场观察",
            acc_ev="人物在场，打断结束可见",
            sem={"kind": "interruption"},
            supports=("C",),
            role="interrupt_end",
        ),
        ev(
            32,
            "person",
            "return_to_task",
            gid,
            None,
            "ACCESSED",
            f"人物回到工作位，面对 {bp['doc']} 的剩余步骤。",
            world=None,
            obs="现场观察",
            acc_ev="人物本人回到工作位",
            supports=("C",),
            role="cutoff",
        ),
    ]


def spec(
    events_a: list[dict[str, Any]],
    events_b: list[dict[str, Any]],
    *,
    state_a: dict[str, str],
    state_b: dict[str, str],
    exp_a: dict[str, Any],
    exp_b: dict[str, Any],
    policy: str,
    notes: str,
    design: dict[str, Any],
    interrupting: bool = False,
) -> dict[str, Any]:
    return {
        "events_a": events_a,
        "events_b": events_b,
        "state_a": state_a,
        "state_b": state_b,
        "exp_a": exp_a,
        "exp_b": exp_b,
        "policy": policy,
        "notes": notes,
        "design": design,
        "interrupting": interrupting,
    }


def mech_contact_cancellation(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1]
    nxt = bp["steps"][1][0]
    cancel_desc = f"系统把 {bp['doc']} 标记为已取消。"
    a = base_events(bp, gid) + [
        ev(
            24,
            "system",
            "task_cancelled",
            gid,
            None,
            "ACCESSED",
            cancel_desc + "取消提示直接弹在人物屏幕上，人物点了确认。",
            world=f"{bp['doc']} 已取消",
            obs="后台取消记录",
            acc_ev="屏幕弹窗，人物点击确认",
            source="notification",
            comp="UNDERSTOOD",
            sem={"kind": "cancellation", "value": "任务已取消", "interpretation": "accurate"},
            supports=("V", "A", "Q"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            "人物说：这单已经取消了，不用再做了。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("B", "C"),
        ),
    ] + closing_events(bp, gid)
    b = base_events(bp, gid) + [
        ev(
            24,
            "system",
            "task_cancelled",
            gid,
            None,
            "NOT_ACCESSED",
            cancel_desc + "该记录只进后台运营队列，工作台没有任何可见或可听提示。",
            world=f"{bp['doc']} 已取消",
            obs="后台取消记录",
            acc_ev="未投递到任何人物可见通道",
            source="backend_record",
            comp="NOT_APPLICABLE",
            sem={"kind": "cancellation", "value": "任务已取消"},
            supports=("V", "A"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            "人物说：还剩两步，回来接着弄。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("C",),
        ),
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "CANCELLED", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_INVALID", "C": "ABANDONED", "Q": "NOT_APPLICABLE"},
        state_b={"V": "CANCELLED", "F": "READY", "A": "NOT_ACCESSED", "B": "UNKNOWN", "C": "SUSPENDED", "Q": nxt},
        exp_a={"action": "do_not_resume", "resume": False, "first_step": None,
               "note": "人物已确认取消，按脚本策略停止原任务。"},
        exp_b={"action": f"resume_{nxt}", "resume": True, "first_step": nxt,
               "note": "人物未接触取消通知，按旧信息继续推进到被中断的步骤。"},
        policy="continue_if_no_known_cancellation",
        notes=f"{bp['id']}：A/B 仅取消通知是否到达人物不同；客观取消状态两版相同。",
        design={"manipulated_factor": "取消通知是否到达人物", "paired_variable": None, "undefined_target": False},
    )


def mech_long_term_commitment(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1][0]
    a = base_events(bp, gid) + [
        ev(
            8,
            "person",
            "commitment_expressed",
            gid,
            None,
            "ACCESSED",
            f"人物早前表示：这周的 {bp['doc']} 我一定会做完。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            comp="NOT_APPLICABLE",
            sem={"kind": "commitment", "value": "继续完成"},
            supports=("A", "B", "C"),
        )
    ] + closing_events(bp, gid)
    b = base_events(bp, gid) + [
        ev(
            8,
            "person",
            "goal_abandoned",
            gid,
            None,
            "ACCESSED",
            f"人物早前表示：这个 {bp['doc']} 先不做了，别再安排。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            comp="NOT_APPLICABLE",
            sem={"kind": "abandonment", "value": "不再推进"},
            supports=("A", "B", "Q"),
        )
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        state_b={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "ABANDONED", "Q": "NOT_APPLICABLE"},
        exp_a={"action": f"resume_{s1}", "resume": True, "first_step": s1,
               "note": "人物早前明确承诺，且步骤未完，按脚本策略恢复。"},
        exp_b={"action": "do_not_resume", "resume": False, "first_step": None,
               "note": "人物早前已明确放弃，最后几个事件与 A 版相同，但长期承诺不同。"},
        policy="resume_if_committed_and_unfinished",
        notes=f"{bp['id']}：A/B 仅早前承诺事件不同；其后中断与返回事件逐条相同。",
        design={"manipulated_factor": "长期承诺还是明确放弃", "paired_variable": None, "undefined_target": False},
    )


def mech_resume_position(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1, s2 = bp["steps"][1], bp["steps"][2]
    a = base_events(bp, gid, f_support=False) + [
        ev(
            14,
            "person",
            "step_completed",
            gid,
            s1[0],
            "ACCESSED",
            f"「{s1[1]}」已做完，设备回执正常。",
            world=f"{s1[0]} 已完成",
            obs="设备回执",
            acc_ev="人物本人操作并看到回执",
            supports=("Q", "F", "A"),
        )
    ] + closing_events(bp, gid)
    b = base_events(bp, gid) + [
        ev(
            14,
            "person",
            "step_attempted",
            gid,
            s1[0],
            "ACCESSED",
            f"「{s1[1]}」试了一次没有成功，设备本身可用，只是还没做完。",
            world=f"{s1[0]} 未完成",
            obs="现场观察",
            acc_ev="人物本人操作并看到失败提示",
            supports=("Q", "A", "F"),
        )
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s2[0]},
        state_b={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1[0]},
        exp_a={"action": f"resume_{s2[0]}", "resume": True, "first_step": s2[0],
               "note": f"人物知道「{s1[1]}」已完成，从下一步恢复。"},
        exp_b={"action": f"resume_{s1[0]}", "resume": True, "first_step": s1[0],
               "note": f"人物认为「{s1[1]}」还没做完，仍从这一步恢复；设备可用不是故障。"},
        policy="resume_at_first_incomplete_known_step",
        notes=f"{bp['id']}：A/B 仅「{s1[1]}」是否完成且人物知情不同；客观可行性两版都是 READY。",
        design={"manipulated_factor": "关键步骤是否完成且人物知情", "paired_variable": None, "undefined_target": False},
    )


def mech_other_completion(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1][0]
    a = base_events(bp, gid) + [
        ev(
            24,
            "colleague",
            "task_completed_by_other",
            gid,
            None,
            "ACCESSED",
            f"{bp['colleague']} 已经把这单剩下的步骤做完了，并在群里说明。",
            world=f"{bp['doc']} 已由他人完成",
            obs="后台完成记录与群消息",
            acc_ev="人物看到了群消息并复述",
            source="third_party_report",
            comp="UNDERSTOOD",
            sem={"kind": "completion_by_other", "value": "同事已完成", "interpretation": "accurate"},
            supports=("V", "A", "F"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            "人物说：既然同事做完了，我这边就不用重复了。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("B", "C", "Q"),
        ),
    ] + closing_events(bp, gid)
    b = base_events(bp, gid) + [
        ev(
            24,
            "colleague",
            "task_completed_by_other",
            gid,
            None,
            "NOT_ACCESSED",
            f"{bp['colleague']} 已经把这单剩下的步骤做完了，但没有通知人物。",
            world=f"{bp['doc']} 已由他人完成",
            obs="后台完成记录",
            acc_ev="无任何通知投递到人物",
            source="backend_record",
            comp="NOT_APPLICABLE",
            sem={"kind": "completion_by_other", "value": "同事已完成"},
            supports=("V", "A", "F"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            f"人物说：回来把这单的「{bp['steps'][1][1]}」收个尾。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("B", "C"),
        ),
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "FULFILLED", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "COMPLETED", "Q": "NOT_APPLICABLE"},
        state_b={"V": "FULFILLED", "F": "READY", "A": "NOT_ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        exp_a={"action": "do_not_resume", "resume": False, "first_step": None,
               "note": "人物知道已完成，不重复推进。"},
        exp_b={"action": "do_not_resume", "resume": False, "first_step": None,
               "note": f"人物不知道已完成，可能重复「{s1}」；但重复已完成步骤不算 T1 恢复，故记 do_not_resume，主观滞后只体现在 Q。"},
        policy="avoid_repeat_if_known_completed",
        notes=f"{bp['id']}：A/B 仅人物是否获知他人完成不同；客观完成状态两版相同。未获知者的重复动作不计作恢复（研究方案 3.4）。",
        design={"manipulated_factor": "人物是否获知他人已完成", "paired_variable": None, "undefined_target": False},
    )


def mech_resource_availability(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1][0]
    a = base_events(bp, gid, f_support=False) + [
        ev(
            24,
            "system",
            "resource_available",
            gid,
            s1,
            "ACCESSED",
            f"{bp['tool']} 已恢复可用，提示直接显示在人物面前。",
            world=f"{bp['tool']} 可用",
            obs="设备状态面板",
            acc_ev="面板提示可见，人物当场确认",
            comp="UNDERSTOOD",
            sem={"kind": "resource_available", "value": "工具可用", "interpretation": "accurate"},
            supports=("F", "A"),
        )
    ] + closing_events(bp, gid)
    b = base_events(bp, gid, f_support=False) + [
        ev(
            24,
            "system",
            "resource_missing",
            gid,
            s1,
            "ACCESSED",
            f"{bp['tool']} 暂时不可用，缺件提示直接显示在人物面前。",
            world=f"{bp['tool']} 缺失",
            obs="设备状态面板",
            acc_ev="面板提示可见，人物当场确认",
            comp="UNDERSTOOD",
            sem={"kind": "resource_missing", "value": "工具缺失", "interpretation": "accurate"},
            supports=("F", "A"),
        )
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        state_b={"V": "VALID", "F": "BLOCKED", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        exp_a={"action": f"resume_{s1}", "resume": True, "first_step": s1,
               "note": "必要条件可用，按脚本策略执行。"},
        exp_b={"action": "wait_for_tool", "resume": False, "first_step": None,
               "note": "必要条件缺失但人物仍承诺，按脚本策略等待，不记为放弃。"},
        policy="execute_if_ready_else_wait",
        notes=f"{bp['id']}：A/B 仅「{bp['tool']}」是否可用不同；两版人物都知情，V/C/Q 相同。",
        design={"manipulated_factor": "必要条件是否可用", "paired_variable": None, "undefined_target": False},
    )


def mech_nested_interruption(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    nid = f"{gid}_nested"
    s1 = bp["steps"][1][0]
    nested_desc = f"{bp['tool']} 出故障，经理要求先修好再回原任务。"

    def nested(idx: int, step: tuple[str, str], kind: str) -> dict[str, Any]:
        types = {"done": "step_completed", "attempt": "step_attempted"}
        return ev(
            20 + 2 * idx,
            "person",
            types[kind],
            nid,
            step[0],
            "ACCESSED",
            f"（嵌套任务）{step[1]}" + ("已完成。" if kind == "done" else "只做到一半，暂未完成。"),
            world=f"{step[0]} " + ("已完成" if kind == "done" else "未完成"),
            obs="现场观察",
            acc_ev="人物本人操作",
            sem={"kind": "nested_task_state", "value": step[0]},
            supports=("A",),
        )

    a_extra = [
        ev(
            19,
            "manager",
            "person_action",
            nid,
            None,
            "ACCESSED",
            nested_desc,
            obs="现场可闻",
            acc_ev="人物当场接到要求",
            supports=("A", "C"),
        ),
        nested(0, NESTED_STEPS[0], "done"),
        nested(1, NESTED_STEPS[1], "done"),
        nested(2, NESTED_STEPS[2], "done"),
    ]
    b_extra = [
        ev(
            19,
            "manager",
            "person_action",
            nid,
            None,
            "ACCESSED",
            nested_desc,
            obs="现场可闻",
            acc_ev="人物当场接到要求",
            supports=("A", "C"),
        ),
        nested(0, NESTED_STEPS[0], "done"),
        nested(1, NESTED_STEPS[1], "attempt"),
        ev(
            24,
            "person",
            "person_statement",
            nid,
            None,
            "ACCESSED",
            "（嵌套任务）人物说：还没弄好，等会儿再试一次。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("C",),
        ),
    ]
    return spec(
        base_events(bp, gid) + a_extra + closing_events(bp, gid),
        base_events(bp, gid) + b_extra + closing_events(bp, gid),
        state_a={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        state_b={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        exp_a={"action": f"resume_{s1}", "resume": True, "first_step": s1,
               "note": "嵌套任务已完成，按脚本优先级回到原目标。"},
        exp_b={"action": "resume_replace_part", "resume": False, "first_step": "replace_part",
               "note": "嵌套任务未完成，先做完嵌套任务；H 内原目标未恢复，故 resume_within_horizon=false。"},
        policy="finish_nested_task_before_parent",
        notes=f"{bp['id']}：A/B 仅嵌套任务是否完成不同；父目标六因子完全相同，差异只在 interrupting_task。",
        design={"manipulated_factor": "嵌套任务在截断时是否完成", "paired_variable": None, "undefined_target": False},
        interrupting=True,
    )


def mech_future_leak(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1][0]
    events = base_events(bp, gid) + closing_events(bp, gid)
    design = {
        "manipulated_factor": "截断前输入完全相同，仅截断后的设计结果不同",
        "paired_variable": None,
        "undefined_target": True,
        "future_outcome": {"A": f"截断后恢复「{s1}」并完成原目标", "B": "截断后未恢复原目标"},
    }
    return spec(
        [dict(e) for e in events],
        [dict(e) for e in events],
        state_a={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        state_b={"V": "VALID", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        exp_a={"action": "indeterminate", "resume": None, "first_step": None,
               "note": "两版截断前输入完全相同，截断点不存在可判别的点标签；评测应按相同分布处理。"},
        exp_b={"action": "indeterminate", "resume": None, "first_step": None,
               "note": "两版截断前输入完全相同，截断点不存在可判别的点标签；评测应按相同分布处理。"},
        policy="resume_if_committed_and_unfinished",
        notes=f"{bp['id']}：未来泄漏负对照。A/B 截断前输入逐字段相同，仅 p0_design.future_outcome 记录截断后设计结果；notes 与 p0_design 均不得进入模型输入。",
        design=design,
    )


def mech_comprehension(bp: dict[str, Any], gid: str) -> dict[str, Any]:
    s1 = bp["steps"][1][0]
    a = base_events(bp, gid) + [
        ev(
            24,
            "system",
            "task_cancelled",
            gid,
            None,
            "ACCESSED",
            f"{bp['doc']} 的取消通知显示在人物屏幕上，人物读完并确认。",
            world=f"{bp['doc']} 已取消",
            obs="后台取消记录与屏幕日志",
            acc_ev="通知已显示，人物点击确认",
            source="notification",
            comp="UNDERSTOOD",
            sem={"kind": "cancellation", "value": "任务已取消", "interpretation": "accurate"},
            supports=("V", "A", "Q"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            "人物说：通知写了取消，那这单就不做了。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("B", "C"),
        ),
    ] + closing_events(bp, gid)
    b = base_events(bp, gid) + [
        ev(
            24,
            "system",
            "task_cancelled",
            gid,
            None,
            "ACCESSED",
            f"{bp['doc']} 的取消通知显示在人物屏幕上，人物也点了确认。",
            world=f"{bp['doc']} 已取消",
            obs="后台取消记录与屏幕日志",
            acc_ev="通知已显示，人物点击确认",
            source="notification",
            comp="MISUNDERSTOOD",
            sem={"kind": "cancellation", "value": "任务已取消", "interpretation": "defer"},
            supports=("V", "A"),
        ),
        ev(
            26,
            "person",
            "person_statement",
            gid,
            None,
            "ACCESSED",
            "人物说：通知说先暂缓，东西先放一边等进一步通知。",
            obs="现场可闻",
            acc_ev="人物自述",
            source="person_report",
            supports=("B", "C"),
        ),
    ] + closing_events(bp, gid)
    return spec(
        a,
        b,
        state_a={"V": "CANCELLED", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_INVALID", "C": "ABANDONED", "Q": "NOT_APPLICABLE"},
        state_b={"V": "CANCELLED", "F": "READY", "A": "ACCESSED", "B": "BELIEVES_VALID", "C": "SUSPENDED", "Q": s1},
        exp_a={"action": "do_not_resume", "resume": False, "first_step": None,
               "note": "接触并正确理解取消，按脚本策略停止。"},
        exp_b={"action": "suspend_or_wait", "resume": False, "first_step": None,
               "note": "同样接触到取消通知但误读为暂缓，保持目标并等待，不记为恢复。"},
        policy="act_on_believed_status",
        notes=f"{bp['id']}：A/B 都接触到取消通知，差异只在人物理解；接触不等于理解。",
        design={"manipulated_factor": "接触到取消信息后的理解", "paired_variable": None, "undefined_target": False},
    )


BUILDERS = {
    "contact_cancellation": mech_contact_cancellation,
    "long_term_commitment": mech_long_term_commitment,
    "resume_position": mech_resume_position,
    "other_completion": mech_other_completion,
    "resource_availability": mech_resource_availability,
    "nested_interruption": mech_nested_interruption,
    "future_leak": mech_future_leak,
    "comprehension": mech_comprehension,
}


def assign_splits(family_ids: list[str]) -> dict[str, str]:
    """60/20/20 by base_story_id, stratified by mechanism (9/3/3 per mechanism)."""
    by_mech: dict[str, list[str]] = {name: [] for name in MECHANISMS}
    for family in family_ids:
        mech = SEED_MECHANISM.get(family, None)
        if mech is None:
            mech = MECHANISMS[int(family[1:3]) - 1]
        by_mech[mech].append(family)
    splits: dict[str, str] = {}
    for mech, families in by_mech.items():
        families = sorted(families)
        for index, family in enumerate(families):
            splits[family] = "train" if index < 9 else ("dev" if index < 12 else "test")
    return splits


def materialise(
    family: str,
    variant: str,
    bp: dict[str, Any],
    mech: str,
    split: str,
    raw: dict[str, Any],
) -> dict[str, Any]:
    gid = f"goal_{family.lower().replace('-', '_')}"
    nid = f"{gid}_nested"
    events = [dict(event) for event in raw["events_" + variant.lower()]]
    events.sort(key=lambda event: event["_off"])
    for index, event in enumerate(events, start=1):
        event["event_id"] = f"e{index:02d}"
        event["time"] = f"{9 + event['_off'] // 60:02d}:{event['_off'] % 60:02d}"

    evidence: dict[str, list[str]] = {factor: [] for factor in ("V", "F", "A", "B", "C", "Q")}
    for event in events:
        for factor in evidence:
            if factor in event["_supports"]:
                evidence[factor].append(event["event_id"])

    # Normalise the evidence chain: UNKNOWN never carries positive evidence, and
    # a non-unknown label must cite at least one event the person could access.
    state = raw["state_" + variant.lower()]
    fallback = next(
        (
            event["event_id"]
            for event in reversed(events)
            if event["actor"] == "person" and event["person_access"] == "ACCESSED"
        ),
        None,
    )
    for factor, value in state.items():
        if value == "UNKNOWN":
            evidence[factor] = []
        elif not evidence[factor] and fallback is not None:
            evidence[factor] = [fallback]

    completed: list[str] = []
    if any(
        event["event_type"] == "task_completed_by_other" and event["goal_id"] == gid
        for event in events
    ):
        completed = [step[0] for step in bp["steps"]]
    else:
        done = {
            event["step_id"]
            for event in events
            if event["event_type"] == "step_completed" and event["goal_id"] == gid
        }
        completed = [step for step in (item[0] for item in bp["steps"]) if step in done]

    roles = {event["_role"]: event["event_id"] for event in events if event["_role"]}
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": f"{family}-{variant}",
        "base_story_id": family,
        "variant": variant,
        "split": split,
        "domain": bp["domain"],
        "mechanism": mech,
        "goal_id": gid,
        "goal_description": bp["goal"],
        "cutoff_event_id": roles["cutoff"],
        "horizon": {"type": "decision_opportunities", "value": 3},
        "task_steps": [step[0] for step in bp["steps"]],
        "task_dependencies": [
            {"before": bp["steps"][index][0], "after": bp["steps"][index + 1][0]}
            for index in range(len(bp["steps"]) - 1)
        ],
        "completed_steps_at_cutoff": completed,
        "observed_events": [],
        "state_at_cutoff": raw["state_" + variant.lower()],
        "state_evidence_event_ids": [],
        "state_evidence_by_factor": evidence,
        "p0_scripted_policy": raw["policy"],
        "p0_expected_action": raw["exp_" + variant.lower()]["action"],
        "p0_expected": {
            "resume_within_horizon": raw["exp_" + variant.lower()]["resume"],
            "first_step": raw["exp_" + variant.lower()]["first_step"],
            "behavior_note": raw["exp_" + variant.lower()]["note"],
        },
        "p0_design": dict(raw["design"]),
        "p1_observed_resume": None,
        "p1_censoring_status": "not_collected",
        "annotation": {
            "annotator_id": "B",
            "status": "reviewed",
            "source_confidence": "high",
            "annotated_at": BUILD_DATE,
            "reviewed_at": BUILD_DATE,
            "second_reviewer_id": None,
        },
        "notes": raw["notes"],
    }
    if raw["exp_" + variant.lower()]["resume"] is None:
        record["p0_expected"]["undefined_reason"] = "indistinguishable_inputs"

    if raw["interrupting"]:
        nested_done = [
            event["step_id"]
            for event in events
            if event["goal_id"] == nid and event["event_type"] == "step_completed"
        ]
        changed = any(event["goal_id"] == nid for event in events)
        record["interrupting_task"] = {
            "task_id": "nested_repair",
            "goal_id": nid,
            "parent_goal_id": gid,
            "steps": [step[0] for step in NESTED_STEPS],
            "status_at_cutoff": "COMPLETED" if len(nested_done) == len(NESTED_STEPS) else "IN_PROGRESS",
            "completed_steps_at_cutoff": nested_done,
        }
        record["interruption"] = {
            "start_event_id": roles["interrupt_start"],
            "end_event_id": roles.get("interrupt_end"),
            "duration_minutes": 12,
            "interrupting_task": "nested_repair",
            "demand_level": "high",
            "goal_priority": "high",
        }
        if not changed:
            del record["interrupting_task"]
            record["interruption"].pop("interrupting_task", None)
    elif roles.get("interrupt_start"):
        start = next(event for event in events if event["event_id"] == roles["interrupt_start"])
        end = next(event for event in events if event["event_id"] == roles["interrupt_end"])
        record["interruption"] = {
            "start_event_id": start["event_id"],
            "end_event_id": end["event_id"],
            "duration_minutes": end["_off"] - start["_off"],
            "interrupting_task": None,
            "demand_level": "medium",
            "goal_priority": "high",
        }

    for event in events:
        record["observed_events"].append(
            {
                key: value
                for key, value in event.items()
                if not key.startswith("_") and key != "event_id"
            }
            | {"event_id": event["event_id"]}
        )
    ordered = [event["event_id"] for event in record["observed_events"]]
    record["state_evidence_event_ids"] = [
        event_id
        for event_id in ordered
        if any(event_id in ids for ids in evidence.values())
    ]
    return record


def upgrade_seed(record: dict[str, Any], split: str, mech: str) -> dict[str, Any]:
    """Upgrade a v0.1 seed record to v0.2 without rewriting its story."""
    upgraded = json.loads(json.dumps(record))
    upgraded["schema_version"] = SCHEMA_VERSION
    upgraded["split"] = split
    upgraded["mechanism"] = mech
    upgraded["annotation"] = {
        "annotator_id": "B",
        "status": "reviewed",
        "source_confidence": "high",
        "annotated_at": "2026-10-20",
        "reviewed_at": BUILD_DATE,
        "second_reviewer_id": None,
    }
    for event in upgraded["observed_events"]:
        kind = "none"
        value = None
        interpretation = "none"
        comprehension = "NOT_APPLICABLE"
        if event["event_type"] == "task_cancelled":
            kind, value = "cancellation", "任务已取消"
            comprehension = "UNDERSTOOD" if event["person_access"] == "ACCESSED" else "NOT_APPLICABLE"
        elif event["event_type"] == "task_completed_by_other":
            kind, value = "completion_by_other", "同事已完成"
            comprehension = "UNDERSTOOD" if event["person_access"] == "ACCESSED" else "NOT_APPLICABLE"
        elif event["event_type"] == "notification_sent":
            kind, value = "cancellation", "任务已取消"
            comprehension = "UNDERSTOOD" if event["person_access"] == "ACCESSED" else "NOT_APPLICABLE"
        elif event["event_type"] == "resource_available":
            kind, value = "resource_available", "工具可用"
            comprehension = "UNDERSTOOD"
        elif event["event_type"] == "resource_missing":
            kind, value = "resource_missing", "工具缺失"
            comprehension = "UNDERSTOOD"
        elif event["event_type"] == "commitment_expressed":
            kind, value = "commitment", "继续完成"
        elif event["event_type"] == "goal_abandoned":
            kind, value = "abandonment", "不再推进"
        elif event["event_type"] in ("interruption_started", "interruption_ended"):
            kind = "interruption"
        if kind == "cancellation" and comprehension == "UNDERSTOOD":
            interpretation = "accurate"
        event["person_comprehension"] = comprehension
        event["person_available_semantics"] = {"kind": kind, "value": value, "interpretation": interpretation}

    if upgraded["base_story_id"] == "P08":
        for event in upgraded["observed_events"]:
            if (
                event["event_type"] in ("task_cancelled", "notification_sent")
                and event["person_access"] == "ACCESSED"
            ):
                misunderstood = upgraded["state_at_cutoff"]["B"] == "BELIEVES_VALID"
                event["person_comprehension"] = "MISUNDERSTOOD" if misunderstood else "UNDERSTOOD"
                event["person_available_semantics"]["interpretation"] = "defer" if misunderstood else "accurate"

    if upgraded["base_story_id"] == "P04" and upgraded["variant"] == "B":
        upgraded["p0_expected"]["resume_within_horizon"] = False
        upgraded["p0_expected"]["first_step"] = None
        upgraded["p0_expected"]["behavior_note"] = (
            "按研究方案 3.4，重复已完成步骤不计作 T1 恢复；人物主观进度滞后只体现在 Q。"
        )
        upgraded["p0_expected_action"] = "do_not_resume"

    if upgraded["base_story_id"] == "P07":
        upgraded["p0_expected"] = {
            "resume_within_horizon": None,
            "first_step": None,
            "undefined_reason": "indistinguishable_inputs",
            "behavior_note": "两版截断前输入完全相同，截断点不存在可判别的点标签；评测应按相同分布处理。",
        }
        upgraded["p0_expected_action"] = "indeterminate"
        upgraded["p0_design"] = {
            "manipulated_factor": "截断前输入完全相同，仅截断后的设计结果不同",
            "paired_variable": None,
            "undefined_target": True,
            "future_outcome": {"A": "截断后恢复原任务", "B": "截断后未恢复原任务"},
        }
    else:
        upgraded["p0_design"] = {
            "manipulated_factor": MECHANISM_LABEL[mech],
            "paired_variable": None,
            "undefined_target": False,
        }
    return upgraded


def build() -> list[dict[str, Any]]:
    seeds = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    seed_families = {record["base_story_id"] for record in seeds}

    generated: list[dict[str, Any]] = []
    for index, mech in enumerate(MECHANISMS, start=1):
        reserved = ((index - 1) * 2) % len(BLUEPRINTS)
        for offset, bp in enumerate(BLUEPRINTS):
            if offset == reserved:
                continue
            family = f"P{index:02d}-{bp['id']}"
            if family in seed_families:
                continue
            gid = f"goal_{family.lower().replace('-', '_')}"
            raw = BUILDERS[mech](bp, gid)
            generated.append((family, bp, mech, raw))

    all_families = sorted(seed_families | {family for family, *_ in generated})
    splits = assign_splits(all_families)

    records: list[dict[str, Any]] = []
    for record in seeds:
        family = record["base_story_id"]
        records.append(upgrade_seed(record, splits[family], SEED_MECHANISM[family]))
    for family, bp, mech, raw in generated:
        for variant in ("A", "B"):
            records.append(materialise(family, variant, bp, mech, splits[family], raw))

    records.sort(key=lambda record: (record["base_story_id"], record["variant"]))
    return records


def main() -> int:
    records = build()
    check = "--check" in sys.argv
    if not check:
        # Force LF so the committed blob and the on-disk file hash identically
        # (the repo pins eol=lf; CRLF would change the published SHA256).
        with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {len(records)} records to {OUT_PATH.relative_to(ROOT)}")
    families = {record["base_story_id"] for record in records}
    events = sum(len(record["observed_events"]) for record in records)
    print(f"families={len(families)} records={len(records)} events={events}")
    from collections import Counter

    print("domains:", dict(Counter(record["domain"] for record in records)))
    print("splits(families):", dict(Counter(
        next(r["split"] for r in records if r["base_story_id"] == family) for family in families
    )))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
