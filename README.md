# Hy3 VerifyLab

面向“代码功能”可验证场景的 Hy3 应用：让 Hy3 先输出**简洁、可审计的解题步骤和代码**，再联合隐藏测试、静态规则与 Hy3 复核，判断最终答案和过程是否分别成立，定位首个错误步骤并归类错误。

> 当前仓库包含可运行的 Demo、**90 道分层题目**（每层 30 道，680 条隐藏断言）、**286 条金标**（16 条人工 + 270 条缺陷注入构造，10 类错误每类 ≥18 条）、沙盒执行器、过程评估器、指标与 bootstrap 置信区间、双人标注抽检表，以及 7.5 秒 Demo GIF。
>
> **两类结果，不要混淆**：
> - `results/validation_*.json` —— **过程评估器自身**的有效性验证（确定性规则层在 286 条金标上的表现）。
> - `results/hy3_benchmark.json` —— **Hy3 模型**在 90 题上的真实成绩（2026-09-04，`demo_mode: false`，90/90 完成）。
>
> **Hy3 主要结果**：答案准确率 **0.867**（78/90）；排除沙盒策略违规后的算法准确率 **0.967**（87/90）；过程告警率原始 **0.722**，剔除规则层关键词假象后估计 **0.133**。
>
> ⚠️ 上述过程指标受两个已量化的系统性偏差影响：**题目未告知模型沙盒禁止 `import`**（占答案错误的 75%），以及**规则层用关键词匹配判定"条件遗漏"**（占过程告警的 82%，其中 86.9% 经裁决为同义换词的误报）。引用前请务必阅读 [`docs/REPORT.md`](docs/REPORT.md) 第 7.3–7.5 节的口径说明。
>
> `results/demo_benchmark.json` 中的准确率 1.0 是内置参考解的自检输出（`demo_mode: true`），**不是模型成绩**。

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
# 每完成一题即落盘，中断后加 --resume 可只跑未完成的题
python scripts/run_benchmark.py --workers 4
python scripts/run_benchmark.py --workers 4 --resume   # 续跑

# 汇总模型结果（含 bootstrap CI、难度分层、校正后的过程指标）
python scripts/summarize_hy3.py

# 裁决规则层"缺少关键词"告警是真遗漏还是同义换词
python scripts/audit_weak_signals.py

# 生成 7.5 秒演示 GIF
python scripts/make_demo_gif.py
```

输出：

- `results/validation_metrics.json`：定位准确率、误报率、检出精确率/召回率、难度分层、错误分布与 95% CI；
- `results/validation_details.json`：逐样本预测和金标；
- `results/human_audit.csv`：含 `ann1_*` / `ann2_*` / `adjudicated_*` 空列的双人盲审表；
- `results/hy3_benchmark.json`：Hy3 逐题原始结果（步骤、代码、测试、复核全量留档）；
- `results/weak_signal_audit.json`：规则层弱信号告警的逐条裁决；
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

## Hy3 评测结果

2026-09-04 在 90 题上运行真实 Hy3（`demo_mode: false`，90/90 完成，0 失败），配置见报告第 1 节。

| 指标 | 原始 | 说明 |
|---|---:|---|
| 答案准确率 | **0.867**（78/90）[0.800, 0.933] | 隐藏测试全部通过 |
| 排除沙盒策略违规后 | **0.967**（87/90） | 12 道错题中有 9 道仅因 `import` 被沙盒拒绝 |
| 过程告警率 | 0.722 → 估计 **0.133** | 82% 告警来自关键词匹配，其中 86.9% 经裁决为误报 |

分层答案准确率：easy 0.967 / medium 0.833 / hard 0.800。在 n=30 下**只有 easy 与 hard 的差异显著**（+0.167, CI [0.033, 0.333]）。

两个偏差均已定位并量化，且修复方案已验证：把"禁止 import"写进求解提示词后，重叠的 52 题上 import 从 5 处降到 0，答案正确率从 0.885 升到 1.000。完整分析、典型案例与偏差处置见 [`docs/REPORT.md`](docs/REPORT.md) 第 7 节。

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
data/tasks.jsonl               90 道分层题集与标准答案
data/validation_samples.jsonl  286 条金标过程样本（16 人工 + 270 构造）
scripts/verify_tasks.py        题集校验：参考解须在沙盒中通过全部测试
scripts/verify_gold.py         金标校验：标签须与真实执行结果一致
scripts/run_validation.py      评估器有效性验证（金标对照）
scripts/run_benchmark.py       Hy3 批量评测（支持 --resume 断点续跑）
scripts/summarize_hy3.py       模型结果汇总、CI、难度分层与校正指标
scripts/audit_weak_signals.py  裁决规则层"缺少关键词"告警是否为误报
scripts/annotation_agreement.py 双人标注 Cohen's kappa 与待裁决清单
tests/                         自动测试
docs/                          计划、方法、出题规范、标注协议、正式报告
results/                       可复现输出（模型结果与金标结果分列）
```

## 复现原则

正式结果需记录 Hy3 模型版本、服务参数、提示词版本、任务集哈希、运行时间和随机种子。不要只展示汇总数字；保留每题步骤、代码、测试摘要、首错定位和人工裁决记录。
