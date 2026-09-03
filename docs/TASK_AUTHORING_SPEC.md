# 题集出题规范

本文件说明 `data/tasks.jsonl` 的题目来源、构造方式、难度分层依据，以及每道题必须满足的机器可校验契约。新增题目必须遵守本规范，并通过 `scripts/verify_tasks.py`。

## 1. 场景与来源

- **场景**：代码功能类可验证场景。题目是可自动判定的纯函数实现任务，存在唯一可验证的标准答案（隐藏测试全通过）。
- **来源**：全部为**自构题**（self-authored）。`source` 字段格式为 `自构题：<考察的模板/算法族>`，例如 `自构题：滑动窗口模板`。
- **为什么自构而非爬取**：爬取题集存在（a）许可与再分发风险；（b）测试过拟合风险（公开题可能进入模型训练语料，导致"答案正确但过程不成立"的样本被低估）。自构题可保证隐藏测试从未公开，且许可干净。
- **构造方式**：先选定一个算法模板族（遍历 / 双指针 / 哈希 / 排序扫描 / 二分 / 滑动窗口 / 动态规划 / 前缀和 / 栈 / 模拟），再围绕该模板设计一道题面自洽、边界明确的题，最后分别写出**正确参考解**与**覆盖该模板典型失效模式的隐藏测试**。

## 2. 难度分层依据

分层由三个可观测维度决定，三者取交集，不凭主观感受：

| 难度 | 算法组件数 | 需处理的独立边界数 | 参考解规模（量级） |
|---|---|---|---|
| easy | 单一模板，直接套用 | 1–2（如空输入、单元素） | 1–8 行 |
| medium | 单一模板 + 1 个不变量或边界技巧 | 3–4（如重复元素、端点接触、开闭区间） | 8–20 行 |
| hard | 2 个模板组合，或需状态转移/复杂不变量 | ≥4（如重数、并列、空目标、最左性） | 20–40 行 |

`difficulty` 字段取值只能是 `easy` / `medium` / `hard`。

## 3. 字段契约

```jsonc
{
  "id": "E04",                       // E= easy, M = medium, H = hard；同层内递增且全局唯一
  "title": "中文题名",
  "difficulty": "easy",
  "source": "自构题：<模板族>",
  "prompt": "完整题面，含输入输出约定与边界要求",
  "signature": "def f(a: list[int]) -> int",
  "constraints": ["0 <= len(a) <= 10000", "..."],
  "visible_tests": ["f([1,2]) == 3"],              // >= 2 条，题面中可见，供模型自检
  "hidden_tests": ["f([]) == 0", "..."],           // >= 5 条，永不暴露给模型，用于最终判定
  "reference_solution": "def f(a):\n    ...",       // 必须通过全部可见+隐藏测试
  "rubric": {
    "required_concepts": ["概念A", "O(n)"],
    "forbidden_claims": [
      {"pattern": "正则", "error_type": "错误类型", "reason": "为什么这条主张不成立"}
    ]
  },
  "demo_solution": {
    "summary": "一句话方案",
    "steps": [{"id": "S1", "claim": "步骤主张", "evidence": "可验证依据"}]
  }
}
```

### 3.1 沙盒硬约束（最容易踩的坑）

沙盒执行器 `sandbox.py` 用 AST 白名单做安全检查，**参考解与测试代码都不得包含**：

- 任何 `import` / `from ... import`（`ast.Import`、`ast.ImportFrom` 一律拒绝）→ **不能用 `math` / `heapq` / `collections` / `bisect` / `itertools`**
- `eval` / `exec` / `compile` / `open` / `input` / `__import__` / `breakpoint`
- `globals` / `locals` / `vars` / `dir` / `help` / `memoryview`，以及任何 `__` 开头的名字或属性

可用内建函数仅：`abs all any bool dict divmod enumerate filter float frozenset int isinstance len list map max min next pow range reversed round set slice sorted str sum tuple zip` 及 `ValueError / TypeError / IndexError / KeyError / Exception`。

需要堆、队列、计数器、二分时**必须手写**（用 `list` 模拟堆、用 `dict` 计数、手写二分）。这是有意的约束：它让"实现逻辑"成为可被静态检视的对象。

### 3.2 测试表达式

`visible_tests` / `hidden_tests` 是**返回布尔值的表达式字符串**，会被 `eval` 求值，不是 `assert` 语句。例如写 `f([1,2]) == 3`，不要写 `assert f([1,2]) == 3`。

隐藏测试要覆盖：空输入、单元素、重复元素、端点/边界值、以及该题模板的典型失效模式（例如"两数之和"必须覆盖"同一元素不可重复使用"）。

### 3.3 Rubric 与错误定位机制

过程评估器的**确定性层**用 `rubric` 定位首错，逻辑是（`evaluator.deterministic_review`）：

1. 把每一步的 `claim + evidence` 拼成文本（小写）；
2. 用 `forbidden_claims[].pattern` 正则搜索；命中则该步标记 `invalid`，`error_type` 取规则的类型，**最早命中的步骤即 `first_error_step`**；
3. 若所有 `required_concepts` 未全部出现在步骤文本中，且前面没命中规则，则末步标记 `条件遗漏`。

由此产生两条硬性要求：

- **`demo_solution.steps` 必须包含全部 `required_concepts` 的字样**，否则演示模式会被自己判成"条件遗漏"；
- `forbidden_claims` 的 `pattern` 必须能被 `re.compile(..., re.I)` 编译，且应当**具体到该模板的典型错误说法**（如"排序后仍保留原下标"），不要写成会误伤正确解法的宽泛词。

错误类型只能取自这 10 类：
`题意误读` `概念错误` `条件遗漏` `计算错误` `跳步推导` `复杂度错误` `边界错误` `实现不一致` `格式不符` `幻觉`

## 4. 校验

```bash
PYTHONPATH=src python scripts/verify_tasks.py data/batch_XX.jsonl
```

校验器检查：字段完整性、参考解通过全部测试、隐藏测试数量、rubric 合法性、**演示步骤回灌到确定性评估器后 process_correct 必须为 True**、id 唯一性。输出 `TASK_BANK_OK` 才允许合入 `data/tasks.jsonl`。

## 5. 冻结与不可变性

`data/tasks.jsonl` 的 `reference_solution`、`hidden_tests`、`rubric` 以及 `data/validation_samples.jsonl` 的金标属于**评测基准**，合入后不得修改；若确需修正，必须新增版本号并在报告中说明，且不得在调参后回头改动。

编号为 `E01–E03 / M01–M03 / H01–H03` 的 9 道题是**冻结基线**（早于"隐藏测试 ≥ 5"规则），字节级保持不变，以保证历史结果可复现，仅豁免隐藏测试条数这一条规则。
