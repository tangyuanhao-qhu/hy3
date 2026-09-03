# Hy3 VerifyLab

面向“代码功能”可验证场景的 Hy3 应用：让 Hy3 先输出**简洁、可审计的解题步骤和代码**，再联合隐藏测试、静态规则与 Hy3 复核，判断最终答案和过程是否分别成立，定位首个错误步骤并归类错误。

> 当前仓库已包含可运行的 Demo、9 道三级题目、16 条人工金标验证样本、沙盒执行器、过程评估器、指标脚本、人工抽检表生成器和 7.5 秒 Demo GIF。`results/` 中的默认结果是确定性规则的烟雾验证，不是尚未运行的 Hy3 正式成绩。

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

# 16 条人工金标样本：生成指标、明细和抽检 CSV
python scripts/run_validation.py

# 调用 Hy3 跑完整 9 题；先在 .env 中设置 DEMO_MODE=0
python scripts/run_benchmark.py

# 生成 7.5 秒演示 GIF
python scripts/make_demo_gif.py
```

输出：

- `results/validation_metrics.json`：定位准确率、误报率、难度分层与错误分布；
- `results/validation_details.json`：逐样本预测和金标；
- `results/human_audit.csv`：可直接继续人工抽检；
- `results/hy3_benchmark.json`：正式模型逐题原始结果；
- `assets/demo.gif`：2 分钟限制内的流程演示。

## 题集设计

`data/tasks.jsonl` 当前有 9 道自构题，每层 3 道：

| 难度 | 能力范围 | 代表题目 | 分层依据 |
|---|---|---|---|
| Easy | 单规则、一次遍历或单表 | 偶数求和、规范化回文、两数之和 | 状态少，边界局部 |
| Medium | 需维护循环不变量 | 区间合并、左边界二分、滑动窗口 | 边界与状态更新耦合 |
| Hard | 两种以上技术组合或二维状态 | 编辑距离、加权区间调度、最小覆盖 | 转移完整性和边界同时决定正确性 |

每题包含明确签名、约束、可见/隐藏测试、参考实现、过程必要概念及确定性错误规则。比赛正式版建议扩展到至少 90 题（每层 30 题），采用模板参数化、人工原创和开源基准许可题三种来源；按算法组件数、状态耦合度、边界数量和参考解复杂度复核分层。

## 有效性验证口径

- **定位准确率**：金标过程有错的样本中，预测 `first_error_step` 与人工金标完全一致的比例。
- **误报率**：最终答案正确且金标过程正确的样本中，被评估器判为过程错误的比例。
- **正确答案告警真实性**：最终答案正确且被评估器告警的样本中，人工金标确认确有过程问题的比例。

验证集不能使用题目规则的开发样本直接充当最终测试。正式提交前应另建盲测集，由两名标注者独立标记首错步骤和类型，冲突由第三人裁决，并报告一致性。

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
