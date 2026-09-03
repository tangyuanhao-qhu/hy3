# 贡献指南

感谢你考虑为 Hy3 VerifyLab 做贡献。本仓库围绕「代码解题过程的可验证评估」展开，核心证据来自隐藏测试、静态规则与 Hy3 复核，因此提交前请先保证这些证据不被破坏。

## 本地开发

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # 默认 DEMO_MODE=1，无需 API 即可跑通
```

## 运行检查（提交前请全部通过）

```bash
# 零额外依赖自检：沙盒、策略、9 题参考解、V04 反例
PYTHONPATH=src python scripts/self_check.py

# 16 条人工金标样本：生成指标、明细、抽检 CSV
PYTHONPATH=src python scripts/run_validation.py

# 单元测试
pytest -q
```

也支持 `pre-commit` 之外的 GitHub Actions：推到 `main`/`master` 或开 PR 时，CI 会自动在 Python 3.10/3.11/3.12 上跑上述三步。

## 题集与评分规则

- `data/tasks.jsonl`：分层题集、参考实现、过程 rubric。**标准答案与隐藏测试属于评测基准，请勿修改**，否则会污染验证口径。
- `data/validation_samples.jsonl`：人工金标过程样本，用于计算定位准确率与误报率。
- 修改 `src/hy3_process_eval/` 下的评估逻辑后，务必重新跑 `self_check.py` 与 `run_validation.py`，确认 `localization_accuracy`、`false_positive_rate` 未退化。

## 正式评测

```bash
# 先在 .env 中设 DEMO_MODE=0 并填好 HY3_BASE_URL / HY3_API_KEY / HY3_MODEL
PYTHONPATH=src python scripts/run_benchmark.py
```

正式提交前应另建盲测集（两名标注者独立标记首错步骤与类型，冲突第三人裁决），不要直接用开发样本充当最终测试。

## 提交约定

- 保持 PR 聚焦单一改动；描述里说明「改了什么」与「为什么」。
- 复现性原则：正式结果需记录 Hy3 模型版本、服务参数、提示词版本、任务集哈希、运行时间与随机种子。
