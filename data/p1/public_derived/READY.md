# 当前推荐训练入口

A/C 请使用 [ready-v1.0](../../training_ready/v1/README.md)（从本文件所在目录向上两级后进入 training_ready）。

准确仓库路径：`data/training_ready/v1/`。

该交付包含固定 train/dev/test、标准 messages SFT 文件、六变量掩码、离线校验与 CPU 训练基线。六变量主监督来自正式 P0；公开 IHBench 只用于中断后续答辅助训练。

本目录此前的 `processed/p1_combined.jsonl` 属于研究转换产物，**不要直接当作六变量金标训练**。ready-v1.0 不依赖那些推导出的信念/承诺标签。真人 P1 采集已于 2026-10-23 决策不再进行；P1 数据交付以公开数据集为准（本目录 + ready-v1.0）。
