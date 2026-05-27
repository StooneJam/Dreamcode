# ReAct 工具开发协议

适用范围：所有用 `@tool` 装饰、注册给 `langgraph.prebuilt.create_react_agent` 的工具
（位于 `src/cca/tools/`）。

> 参考 ADR：[D-035](decisions.md#d-035--react-工具失败协议永不-raise-return-llm-friendly-错误字符串)

## 核心契约

### 1. 永不向 ToolNode raise

LangGraph 的 `ToolNode` 默认对工具异常**直接 raise** ——
跟 LangChain `AgentExecutor` 自动包成 `ToolMessage` 让 LLM 重试**不一样**。
任何 ReAct 工具内部 raise = 整条 ReAct loop 死亡，节点提前退出，下游产物全空。

```python
# ❌ 错误：会中断 ReAct
@tool
def finalize_profile(product_name: str, profile_json: str) -> str:
    profile = ProductProfile.model_validate_json(profile_json)  # 抛 ValidationError
    return json.dumps({"profile": profile.model_dump()})

# ❌ 也错：ToolException 也会中断
@tool
def finalize_profile(...) -> str:
    raise ToolException("校验失败")

# ✓ 正确：return 错误字符串
@tool
def finalize_profile(product_name: str, profile_json: str) -> str:
    profile, err = safe_load_validate(profile_json, ProductProfile, hint="...")
    if err:
        return err  # LLM 看到 ToolMessage 后自修参数重试
    return json.dumps({"profile": profile.model_dump()})
```

### 2. 错误字符串必须 LLM-friendly

LLM 看到的是 `ToolMessage(content=<你 return 的 string>)`，要能据此修参数。包含：

- **字段路径**（`dimensions.0.facts.1.evidence.0.source_url`），不是裸 Pydantic dump
- **错误类型**（`Field required` / `Input should be a valid number`）
- **修复 hint**（"Evidence 必填 source_url；Fact 必须含至少 1 条 evidence"）

参考 `src/cca/tools/_validation.py::safe_load_validate` 的输出格式：

```
ProductProfile 校验失败，请按以下错误修正后重试 finalize_profile：
  · dimensions.0.facts.1.evidence.0.source_url: Field required
  · pricing.tiers.0.source.source_url: Field required

字段规则提示：
- Dimension 必填：name, category, facts
- Fact 必填：statement, evidence（list 非空）
- Evidence 必填：source_url
```

### 3. 用 `safe_load_validate` 统一入参解析

凡是入参是 JSON 字符串 + 期望 Pydantic 校验的工具，统一走：

```python
from cca.tools._validation import safe_load_validate

@tool
def my_tool(payload_json: str) -> str:
    obj, err = safe_load_validate(
        payload_json, MySchema,
        pre_clean=my_cleaner,           # 可选：清洗 LLM 常见偏差
        hint="字段规则提示：...",         # LLM 自修向导
    )
    if err:
        return err
    # 正常处理...
```

`safe_load_validate` 一次性处理 JSON decode + Pydantic validate 两层错误。
列表场景用 `safe_load_list(json_str, item_schema)`。

### 4. 自动清洗常见 LLM schema 偏差

LLM 高频犯的同类错误，与其每次回滚让 LLM 自修，不如工具主动清洗：

| LLM 偏差 | 清洗策略 |
|---|---|
| Evidence 缺 `source_url`（只填 snippet） | 剔除该 Evidence |
| Fact 的 evidence 列表清空后无内容 | 剔除该 Fact |
| `pricing.tiers[].source` 是 dict 但缺 url | 置 None（字段 Optional） |
| `target_platforms` 写中文自由文本 | fallback 到 `"other"`（枚举允许） |

参考 `collector_tools._clean_profile` 和 `debate._repair_for_schema`。

### 5. 非 JSON / 子进程 / 网络错误一律 return error dict 或 str

所有外部资源访问（subprocess / httpx / requests / Tavily 等）失败时：

```python
# ❌ 错误
result = subprocess.run(...)
if result.returncode != 0:
    raise RuntimeError(...)

# ✓ 正确
try:
    result = subprocess.run(...)
except (FileNotFoundError, subprocess.TimeoutExpired) as e:
    return json.dumps({"error": f"...: {e}", ...}, ensure_ascii=False)
if result.returncode != 0:
    return json.dumps({"error": "进程异常: " + result.stderr[:300], ...})
```

参考 `tools/appstore.py::_run_scraper`、`tools/fetcher.py::fetch_url`。

## 模板

新工具的最小骨架：

```python
from langchain_core.tools import tool

from cca.tools._validation import safe_load_validate


@tool
def my_new_tool(arg1: str, payload_json: str) -> str:
    """一行 docstring：做什么 + 何时调。

    Args:
        arg1: ...
        payload_json: 符合 MySchema 的 JSON。字段：...
    """
    obj, err = safe_load_validate(
        payload_json, MySchema,
        hint="MySchema 字段规则：\n- field_a 必填\n- field_b 枚举 ['x','y']",
    )
    if err:
        return err
    # 业务逻辑...
    return json.dumps(result, ensure_ascii=False)
```

## 测试

每个新工具配 2 个核心测试：

1. **成功路径**：合法 JSON + 合规 schema → 返回结构化 JSON
2. **失败路径**：非法 JSON / 缺 required 字段 → 返回字符串且含「校验失败 / 字段规则提示 / 字段路径」关键字（**不 raise**）

参考 `tests/test_tools/test_collector_tools.py::test_finalize_profile_returns_error_string_on_invalid_schema`。

## 反模式速查

| 反模式 | 后果 | 替代 |
|---|---|---|
| `model.model_validate_json(s)` 不 try | ValidationError 中断 ReAct | `safe_load_validate(s, model)` |
| `json.loads(s)` 不 try | JSONDecodeError 中断 ReAct | `safe_load_validate` 内部已处理 |
| `raise ToolException(msg)` | LangGraph 仍中断 | `return msg` |
| `raise RuntimeError(...)` | 同上 | `return json.dumps({"error": ...})` |
| 错误字符串只含 `str(e)` | LLM 看不到字段路径 | 用 `e.errors()` 提取 `loc` |

## 例外情况

PM 阶段节点（`agents/pm.py`）**不**走 ReAct，是 `with_structured_output` 直接调用，
因此可以用 try/except 处理 ValidationError + 重试自修。本协议不适用。
