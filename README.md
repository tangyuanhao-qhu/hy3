# Hy3 VerifyLab

面向“代码功能”可验证场景的 Hy3 应用：让 Hy3 先输出**简洁、可审计的解题步骤和代码**，再联合隐藏测试、静态规则与 Hy3 复核，判断最终答案和过程是否分别成立，定位首个错误步骤并归类错误。

> 当前仓库包含可运行的 Demo、**90 道分层题目**（每层 30 道，680 条隐藏断言）、**286 条金标**（16 条人工 + 270 条缺陷注入构造，10 类错误每类 ≥18 条）、沙盒执行器、过程评估器、指标与 bootstrap 置信区间、双人标注抽检表，以及 7.5 秒 Demo GIF。
>
> **一个重要区分**：`results/validation_*.json` 是**过程评估器自身**的有效性验证结果（确定性规则层在 286 条金标上的表现），详见 [`docs/REPORT.md`](docs/REPORT.md)；而 `results/demo_benchmark.json` 中的准确率 1.0 是内置参考解的自检输出（`demo_mode: true`），**不是 Hy3 的成绩**。Hy3 正式运行需配置 TokenHub 密钥后以 `DEMO_MODE=0` 执行，尚未完成。

## 为什么选代码任务

代码任务同时具备三类可核查证据：函数测试可判断输出，静态/动态检查可验证实现，结构化步骤可与代码和约束逐项对齐。它尤其适合识别“碰巧通过有限测试，但解释或实现逻辑不成立”的样本。

## 方法概览

1. **Hy3 解题**：输出 `S1...Sn` 的可审计步骤、关键不变量、边界、复杂度和 Python 函数。
2. **结果验证**：隔离子进程运行可见与隐藏测试；AST 安全策略拒绝导入、文件和动态执行。
3. **过程验证**：确定性规则检查已知矛盾；Hy3 依据题目、步骤、代码和测试摘要逐步复核。
4. **证据融合**：规则命中确定矛盾时拥有否决权；否则采用 Hy3 的逐步判断。隐藏测试只决定功能正确性，不能替代过程判断。
5. **错误输出**：给出 `first_error_step`、错误类型、逐步证据，并单独标记“答案正确但过程不成立”。

错误类型固定为：题意误读、概念错误、条件遗漏、计算错误、跳步推导、复杂度错误、边界错误、实现不一致、格式不符、幻觉。

## 快速运行

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
streamlit run app.py
```

默认 `.env.example` 中 `DEMO_MODE=1`，无需 GPU 或 API 即可跑通。连接已经部署的 Hy3：

```dotenv
HY3_BASE_URL=http://127.0.0.1:8000/v1
HY3_API_KEY=EMPTY
HY3_MODEL=hy3
HY3_REASONING_EFFORT=high
DEMO_MODE=0
```

官方仓库给出的 Hy3 服务兼容 OpenAI Chat Completions API；本项目因此只依赖一个可配置的兼容端点。正式部署模型本身请按官方 vLLM/SGLang 文档执行，本仓库不重复打包 295B 权重。

## 运行验证与批量评测

```bash
# 单元测试
pytest -q

# 未安装 pytest 时的零额外依赖自检
PYTHONPATH=src python scripts/self_check.py

# 校验题集：schema + 沙盒实跑参考解 + rubric + 演示步骤回灌
python scripts/verify_tasks.py

# 校验金标：标签是否与沙盒执行结果一致
python scripts/verify_gold.py

# 286 条金标上评估过程评估器：生成指标(含 bootstrap CI)、明细和抽检 CSV
python scripts/run_validation.py

# 标注一致性：两名标注者填完 ann1_*/ann2_* 列后计算 Cohen's kappa
python scripts/annotation_agreement.py

# 调用 Hy3 跑完整 90 题；先在 .env 中设置 DEMO_MODE=0
python scripts/run_benchmark.py

# 生成 7.5 秒演示 GIF
python scripts/make_demo_gif.py
```

输出：

- `results/validation_metrics.json`：定位准确率、误报率、检出精确率/召回率、难度分层、错误分布与 95% CI；
- `results/validation_details.json`：逐样本预测和金标；
- `results/human_audit.csv`：含 `ann1_*` / `ann2_*` / `adjudicated_*` 空列的双人盲审表；
- `results/hy3_benchmark.json`：正式模型逐题原始结果（需 `DEMO_MODE=0`）；
- `assets/demo.gif`：2 分钟限制内的流程演示。

## 题集设计

`data/tasks.jsonl` 现有 **90 道自构题**，每层 30 道，共 680 条隐藏断言，覆盖 87 个算法族。分层依据与出题契约见 [`docs/TASK_AUTHORING_SPEC.md`](docs/TASK_AUTHORING_SPEC.md)。

| 难度 | 题数 | 算法组件数 | 需处理的独立边界数 | 参考解规模 | 代表题目 |
|---|---:|---|---|---|---|
| Easy | 30 | 单一模板，直接套用 | 1–2 | 1–8 行 | 偶数求和、规范化回文、两数之和 |
| Medium | 30 | 单一模板 + 1 个不变量或边界技巧 | 3–4 | 8–20 行 | 区间合并、左边界二分、滑动窗口 |
| Hard | 30 | 2 个模板组合，或需状态转移/复杂不变量 | ≥4 | 20–40 行 | 编辑距离、加权区间调度、最小覆盖 |

每题包含明确签名、约束、可见/隐藏测试、参考实现、过程必要概念（`required_concepts`）及确定性错误规则（`forbidden_claims`）。

- **来源与构造**：全部为自构题。`source` 字段记录所考察的模板族。选择自构而非爬取，是为规避许可风险与测试过拟合——公开题可能已进入模型训练语料，会系统性低估"答案正确但过程不成立"的样本比例。
- **质量保证**：`scripts/verify_tasks.py` 在沙盒中**真实执行**每题的参考解，要求通过全部可见与隐藏测试，并回灌演示步骤确认其不被自身 rubric 误判。新题一律 ≥5 条隐藏测试；编号 `E01–E03 / M01–M03 / H01–H03` 的 9 道题是冻结基线（早于该规则），字节级保持不动以保证历史结果可复现，仅豁免隐藏测试条数这一条。
- **沙盒约束**：执行器禁用一切 `import`，仅开放白名单内建函数。因此堆、队列、并查集、计数器均需手写。这是有意的约束：它让"实现逻辑"成为可被静态检视的对象。

## 金标构造

`data/validation_samples.jsonl` 现有 286 条：16 条人工标注（`source="human"`）+ 270 条缺陷注入构造（`source="constructed"`）。构造方式为每个任务生成三个变体——A 原样复用（过程正确）、B 保留参考解但改写某一步主张（答案正确但过程不成立）、C 改写主张并植入真实代码缺陷（答案错误）。

**循环性控制是这里的要害**：构造时禁止读取该任务的 `forbidden_claims` 正则，禁止为让规则命中而回改措辞，否则定位准确率会沦为自我实现的预言。作为对照——早期 16 条手写金标因文本与 rubric 同源，定位准确率为 1.0；改用独立构造后降至 0.249。那个 1.0 不再具有参考价值。

构造式金标的定位结论来自注入意图，**不等于两人独立标注的一致意见**。盲审表与 Cohen's kappa 计算已就绪（见 [`docs/ANNOTATION_PROTOCOL.md`](docs/ANNOTATION_PROTOCOL.md)），但 `ann1_*` / `ann2_*` 列仍待真人填写。

## 有效性验证口径

- **定位准确率**：金标过程有错的样本中，预测 `first_error_step` 与金标完全一致的比例。
- **误报率**：最终答案正确且金标过程正确的样本中，被评估器判为过程错误的比例。
- **检出精确率 / 召回率 / F1**：以"评估器判定过程有问题"为阳性、"金标 `process_correct=false`"为真值计算的二分类指标。
- **正确答案告警真实性**：最终答案正确且被评估器告警的样本中，金标确认确有过程问题的比例。

⚠️ 命名提醒：`metrics.py` 中的 `process_accuracy` 是**过程告警率**（判定过程无问题的比例），**不是**与金标对比的准确率。与金标对比的准确率在 `detection.agreement_with_gold`。

当前结果（286 条金标，确定性规则层）：定位准确率 0.249 [0.190, 0.312]，误报率 0.000 [0.000, 0.000]，检出精确率 1.000 / 召回率 0.434 / F1 0.605。完整分析与能力边界见 [`docs/REPORT.md`](docs/REPORT.md)。

## 安全边界

内置执行器适合比赛 Demo：AST 拒绝导入、文件访问和动态执行，候选代码在 `python -I -S` 子进程中限时运行。它不是强安全多租户沙盒。若对公网开放，请把执行层替换为无网络、只读文件系统、非 root、CPU/内存/pid 限额的一次性容器或 microVM；不要把隐藏测试返回前端。

## 项目结构

```text
app.py                         Streamlit 应用
src/hy3_process_eval/          Hy3 客户端、沙盒、评估器、指标
data/tasks.jsonl               分层题集与标准答案
data/validation_samples.jsonl  人工金标过程样本
scripts/                       批量评测、有效性验证、GIF
tests/                         自动测试
docs/                          计划、方法和正式报告模板
results/                       可复现输出
```

## 复现原则

正式结果需记录 Hy3 模型版本、服务参数、提示词版本、任务集哈希、运行时间和随机种子。不要只展示汇总数字；保留每题步骤、代码、测试摘要、首错定位和人工裁决记录。
