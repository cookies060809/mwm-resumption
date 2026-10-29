# P0 v0.4 盲审包（A/C 用）

> 这是 8 条**去掉标签**的样本，每机制 1 条。请不要查看 `blind_review_v0.4_key.json`，
> 也不要与 B 讨论答案。按 `blind_review_v0.4_protocol.md` 填写你名下的 CSV。

每条只给：目标、任务步骤与依赖、决策窗口、截断事件、截断前事件。
没有 `state_at_cutoff`、`p0_expected`、`p0_scripted_policy`、机制名、家族 ID 或 B 的备注。

## B01

**目标**：准备周六家庭聚餐（聚餐 DN-12）

**决策窗口**：decision_opportunities = 3

**任务步骤**：plan_menu, buy_groceries, prep_ingredients, cook_dishes

**依赖**：plan_menu → buy_groceries；buy_groceries → prep_ingredients；prep_ingredients → cook_dishes

**截断事件**：e08（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 09:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物开始处理「准备周六家庭聚餐（聚餐 DN-12）」，聚餐清单 DN-12 已建单。 |  |
| e02 | 09:06 | person | step_completed | plan_menu | ACCESSED | NOT_APPLICABLE | CERTAIN | 完成「定好菜单」。 |  |
| e03 | 09:12 | person | step_started | buy_groceries | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始「采购食材」，进度停在这一步。 |  |
| e04 | 09:18 | other | interruption_started |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 孩子放学回家敲门，正在进行的「采购食材」被迫中断。 | {"kind": "interruption"} |
| e05 | 09:24 | system | task_cancelled |  | ACCESSED | MISUNDERSTOOD | CERTAIN | 聚餐清单 DN-12 的取消通知显示在人物屏幕上，人物也点了确认。 | {"kind": "cancellation", "value": "任务已取消", "interpretation": "defer"} |
| e06 | 09:26 | person | person_statement |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物说：通知说先暂缓，东西先放一边等进一步通知。 |  |
| e07 | 09:30 | other | interruption_ended |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 打断结束，环境恢复安静。 | {"kind": "interruption"} |
| e08 | 09:32 | person | return_to_task |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到工作位，面对 聚餐清单 DN-12 的剩余步骤。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B02

**目标**：完成订单 O17 的地址核对、包装与运单打印。

**决策窗口**：decision_opportunities = 3

**任务步骤**：verify_address, pack_item, print_label

**依赖**：verify_address → pack_item；pack_item → print_label

**截断事件**：e08（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 10:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始处理订单 O17。 |  |
| e02 | 10:01 | person | step_completed | verify_address | ACCESSED | NOT_APPLICABLE | CERTAIN | 核对收货地址完成。 |  |
| e03 | 10:02 | person | step_started | pack_item | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始包装商品；包装台工具可用。 |  |
| e04 | 10:03 | person | interruption_started | pack_item | ACCESSED | NOT_APPLICABLE | CERTAIN | 接听客服电话，暂停包装。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e05 | 10:04 | customer | task_cancelled |  | NOT_ACCESSED | NOT_APPLICABLE | CERTAIN | 客户在后台取消订单 O17。 | {"kind": "cancellation", "value": "任务已取消", "interpretation": "none"} |
| e06 | 10:05 | system | notification_sent |  | NOT_ACCESSED | NOT_APPLICABLE | CERTAIN | 取消通知仅进入后台运营队列；工作台无可见或可听提示。 | {"kind": "cancellation", "value": "任务已取消", "interpretation": "none"} |
| e07 | 10:06 | person | interruption_ended | pack_item | ACCESSED | NOT_APPLICABLE | CERTAIN | 电话结束。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e08 | 10:07 | person | return_to_task | pack_item | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到同一工作台。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B03

**目标**：准备周六家庭聚餐（聚餐 DN-12）

**决策窗口**：decision_opportunities = 3

**任务步骤**：plan_menu, buy_groceries, prep_ingredients, cook_dishes

**依赖**：plan_menu → buy_groceries；buy_groceries → prep_ingredients；prep_ingredients → cook_dishes

**截断事件**：e06（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 09:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物开始处理「准备周六家庭聚餐（聚餐 DN-12）」，聚餐清单 DN-12 已建单。 |  |
| e02 | 09:06 | person | step_completed | plan_menu | ACCESSED | NOT_APPLICABLE | CERTAIN | 完成「定好菜单」。 |  |
| e03 | 09:12 | person | step_started | buy_groceries | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始「采购食材」，进度停在这一步。 |  |
| e04 | 09:18 | other | interruption_started |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 孩子放学回家敲门，正在进行的「采购食材」被迫中断。 | {"kind": "interruption"} |
| e05 | 09:30 | other | interruption_ended |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 打断结束，环境恢复安静。 | {"kind": "interruption"} |
| e06 | 09:32 | person | return_to_task |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到工作位，面对 聚餐清单 DN-12 的剩余步骤。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B04

**目标**：学完线上课程第三章（课程 PY-3）

**决策窗口**：decision_opportunities = 3

**任务步骤**：watch_lecture, do_exercise, take_quiz, write_notes

**依赖**：watch_lecture → do_exercise；do_exercise → take_quiz；take_quiz → write_notes

**截断事件**：e07（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 09:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物开始处理「学完线上课程第三章（课程 PY-3）」，课程笔记 PY-3 已建单。 |  |
| e02 | 09:06 | person | step_completed | watch_lecture | ACCESSED | NOT_APPLICABLE | CERTAIN | 完成「看完第三节视频」。 |  |
| e03 | 09:08 | person | commitment_expressed |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物早前表示：这周的 课程笔记 PY-3 我一定会做完。 | {"kind": "commitment", "value": "继续完成"} |
| e04 | 09:12 | person | step_started | do_exercise | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始「做完课后练习」，进度停在这一步。 |  |
| e05 | 09:18 | other | interruption_started |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 室友叫去取快递，正在进行的「做完课后练习」被迫中断。 | {"kind": "interruption"} |
| e06 | 09:30 | other | interruption_ended |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 打断结束，环境恢复安静。 | {"kind": "interruption"} |
| e07 | 09:32 | person | return_to_task |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到工作位，面对 课程笔记 PY-3 的剩余步骤。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B05

**目标**：完成客户投诉回访（投诉 CMP-77）

**决策窗口**：decision_opportunities = 3

**任务步骤**：read_case, call_customer, log_result, close_ticket

**依赖**：read_case → call_customer；call_customer → log_result；log_result → close_ticket

**截断事件**：e10（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 09:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物开始处理「完成客户投诉回访（投诉 CMP-77）」，投诉单 CMP-77 已建单。 |  |
| e02 | 09:06 | person | step_completed | read_case | ACCESSED | NOT_APPLICABLE | CERTAIN | 完成「阅读投诉记录」。 |  |
| e03 | 09:12 | person | step_started | call_customer | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始「电话回访客户」，进度停在这一步。 |  |
| e04 | 09:18 | colleague | interruption_started |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 质检员来抽听录音，正在进行的「电话回访客户」被迫中断。 | {"kind": "interruption"} |
| e05 | 09:19 | manager | person_action |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 外呼系统 出故障，经理要求先修好再回原任务。 |  |
| e06 | 09:20 | person | step_completed | clear_jam | ACCESSED | NOT_APPLICABLE | CERTAIN | （嵌套任务）清除卡纸已完成。 | {"kind": "nested_task_state", "value": "clear_jam"} |
| e07 | 09:22 | person | step_attempted | replace_part | ACCESSED | NOT_APPLICABLE | CERTAIN | （嵌套任务）更换耗材只做到一半，暂未完成。 | {"kind": "nested_task_state", "value": "replace_part"} |
| e08 | 09:24 | person | person_statement |  | ACCESSED | NOT_APPLICABLE | CERTAIN | （嵌套任务）人物说：还没弄好，等会儿再试一次。 |  |
| e09 | 09:30 | colleague | interruption_ended |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 打断结束，环境恢复安静。 | {"kind": "interruption"} |
| e10 | 09:32 | person | return_to_task |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到工作位，面对 投诉单 CMP-77 的剩余步骤。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B06

**目标**：提交报销单 E9。

**决策窗口**：decision_opportunities = 3

**任务步骤**：collect_receipts, fill_form, submit_portal

**依赖**：collect_receipts → fill_form；fill_form → submit_portal

**截断事件**：e07（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 10:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始处理报销单 E9。 |  |
| e02 | 10:01 | person | step_completed | collect_receipts | ACCESSED | NOT_APPLICABLE | CERTAIN | 收集并整理发票。 |  |
| e03 | 10:03 | person | step_started | fill_form | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始填写报销表单。 |  |
| e04 | 10:04 | person | interruption_started | fill_form | ACCESSED | NOT_APPLICABLE | CERTAIN | 接听电话，暂停报销单处理。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e05 | 10:06 | colleague | task_completed_by_other |  | ACCESSED | UNDERSTOOD | CERTAIN | 同事完成并提交报销单；同事发消息告知人物，人物在电话中看到并回复。 | {"kind": "completion_by_other", "value": "同事已完成", "interpretation": "none"} |
| e06 | 10:08 | person | interruption_ended | fill_form | ACCESSED | NOT_APPLICABLE | CERTAIN | 电话结束。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e07 | 10:09 | person | return_to_task | fill_form | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到工位。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B07

**目标**：洗完并烘干一筐衣物。

**决策窗口**：decision_opportunities = 3

**任务步骤**：load_washer, run_wash, run_dry, fold_clothes

**依赖**：load_washer → run_wash；run_wash → run_dry；run_dry → fold_clothes

**截断事件**：e06（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 08:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始洗一筐衣物。 |  |
| e02 | 08:05 | person | step_completed | load_washer | ACCESSED | NOT_APPLICABLE | CERTAIN | 装洗衣机完成。 |  |
| e03 | 08:50 | person | step_completed | run_wash | ACCESSED | NOT_APPLICABLE | CERTAIN | 洗涤程序结束。 |  |
| e04 | 08:55 | person | interruption_started | run_dry | ACCESSED | NOT_APPLICABLE | CERTAIN | 门铃响，去收快递。 |  |
| e05 | 09:00 | person | person_statement | run_dry | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物说“洗完了，等下拿去烘干。” |  |
| e06 | 09:05 | environment | resource_missing | run_dry | NOT_ACCESSED | NOT_APPLICABLE | CERTAIN | 烘干机报错 E21，暂时无法启动。 | {"kind": "resource_missing", "value": "烘干机故障 E21", "interpretation": "none"} |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。

## B08

**目标**：完成订单 O21 的运单打印与快递交接。

**决策窗口**：decision_opportunities = 3

**任务步骤**：verify_address, pack_item, print_label, handoff_courier

**依赖**：verify_address → pack_item；pack_item → print_label；print_label → handoff_courier

**截断事件**：e07（其后事件不在输入中）

| id | time | actor | type | step | access | comprehension | certainty | text | semantics |
|---|---|---|---|---|---|---|---|---|---|
| e01 | 10:00 | person | goal_start |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 开始处理订单 O21。 |  |
| e02 | 10:01 | person | step_completed | verify_address | ACCESSED | NOT_APPLICABLE | CERTAIN | 地址核对完成。 |  |
| e03 | 10:04 | person | step_completed | pack_item | ACCESSED | NOT_APPLICABLE | CERTAIN | 包装完成。 |  |
| e04 | 10:06 | person | step_completed | print_label | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物打印并核对运单，确认打印完成。 |  |
| e05 | 10:10 | person | interruption_started |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 接听客户电话，暂停订单处理。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e06 | 10:13 | person | interruption_ended |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 电话结束。 | {"kind": "interruption", "value": null, "interpretation": "none"} |
| e07 | 10:14 | person | return_to_task |  | ACCESSED | NOT_APPLICABLE | CERTAIN | 人物回到同一工作台。 |  |

**请填**：`V`、`F`、`A`、`B`、`C`、`Q`、`resume_label`、`resume_step`，
以及你依据的事件 ID（逐因子写在你名下的 CSV 的 `evidence_event_ids` 列）。
