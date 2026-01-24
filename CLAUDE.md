# CLAUDE.md - LG2Jiuwen 项目开发规则

> 版本：V2.0.0
> 更新日期：2026-01-24

## 项目概述

这是一个 LangGraph 到 openJiuwen 的代码迁移工具，**使用 openJiuwen 框架自身实现**。

核心设计原则：**规则优先，AI 兜底**
- 规则能处理的用规则（快速、确定、低成本）
- 规则无法处理的用 AI（语义理解、灵活）

## 架构

```
源代码 → AST → RuleExtractor(转换) → [AISemantic(转换剩余)] → IR(已转换代码) → CodeGenerator(代码生成)
```

**关键点**：
- 所有代码转换在 IR 构建之前完成
- IR 存储已转换的代码
- CodeGenerator 只做代码拼接，不需要 AI

## 目录结构

```
src/lg2jiuwen_tool/
├── __init__.py              # 模块入口
├── __main__.py              # 命令行入口
├── cli.py                   # CLI 实现
├── service.py               # 服务接口（主入口）
├── workflow/                # openJiuwen 工作流定义
│   ├── migration_workflow.py   # 主工作流
│   └── state.py                # 状态和数据模型
├── components/              # openJiuwen 工作流组件
│   ├── project_detector.py     # 项目检测（单/多文件）
│   ├── file_loader.py          # 文件加载
│   ├── ast_parser.py           # AST 解析
│   ├── rule_extractor.py       # 规则提取+转换（核心）
│   ├── pending_check.py        # 待处理检查
│   ├── ai_semantic.py          # AI 语义理解
│   ├── ir_builder.py           # IR 构建
│   ├── code_generator.py       # 代码生成（核心）
│   └── report.py               # 报告生成
├── rules/                   # 转换规则
│   ├── base.py                 # 规则基类
│   ├── state_rules.py          # 状态访问规则
│   ├── llm_rules.py            # LLM 调用规则
│   ├── tool_rules.py           # 工具调用规则
│   └── edge_rules.py           # 边/路由规则
└── ir/                      # 中间表示
    └── models.py               # IR 数据模型
```

## 组件开发规范

### 组件基类

所有组件必须继承 `WorkflowComponent` 和 `ComponentExecutable`：

```python
from openjiuwen.core.component.base import WorkflowComponent
from openjiuwen.core.runtime.base import ComponentExecutable, Input, Output
from openjiuwen.core.runtime.runtime import Runtime
from openjiuwen.core.context_engine.base import Context

class MyComp(WorkflowComponent, ComponentExecutable):
    """组件描述"""

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        # 从 inputs 获取输入
        data = inputs["input_field"]

        # 处理逻辑
        result = self._process(data)

        # 返回字典作为输出
        return {"output_field": result}
```

### 组件命名

- 文件名：`snake_case.py`，如 `rule_extractor.py`
- 类名：`PascalCase` + `Comp` 后缀，如 `RuleExtractorComp`

## 数据模型规范

### ExtractionResult（核心数据结构）

```python
@dataclass
class ExtractionResult:
    """提取结果"""
    # 已完成转换的内容
    states: List[StateField] = field(default_factory=list)
    nodes: List[ConvertedNode] = field(default_factory=list)
    edges: List[EdgeInfo] = field(default_factory=list)
    tools: List[ToolInfo] = field(default_factory=list)
    llm_configs: List[LLMConfig] = field(default_factory=list)
    global_vars: List[str] = field(default_factory=list)
    tool_related_vars: List[str] = field(default_factory=list)
    tool_map_var_name: Optional[str] = None  # 工具映射变量名（动态提取）

    # 待处理项
    pending_items: List[PendingItem] = field(default_factory=list)

    # 其他提取信息
    entry_point: Optional[str] = None
    graph_name: Optional[str] = None
    state_class_name: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    initial_inputs: Dict[str, Any] = field(default_factory=dict)
    example_inputs: Dict[str, Any] = field(default_factory=dict)  # 从 main 函数提取

    # 统计
    rule_count: int = 0
    ai_count: int = 0
```

## 规则开发规范

### 规则基类

```python
from abc import ABC, abstractmethod
import ast
from dataclasses import dataclass, field
from typing import List

@dataclass
class ConversionResult:
    """转换结果"""
    success: bool = True
    code: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    failed_lines: List[dict] = field(default_factory=list)

class StatementRule(ABC):
    """语句级规则基类"""

    @abstractmethod
    def matches(self, node: ast.AST) -> bool:
        """判断是否匹配此规则"""
        pass

    @abstractmethod
    def convert(self, node: ast.AST) -> ConversionResult:
        """执行转换"""
        pass
```

## LangGraph 到 openJiuwen 转换映射

### 结构映射

| LangGraph | openJiuwen |
|-----------|------------|
| `StateGraph` | `Workflow` |
| `TypedDict` State | `inputs_schema` 传递 |
| Node Function | `WorkflowComponent` |
| `add_edge()` | `add_connection()` |
| `add_conditional_edges()` | `add_conditional_connection()` + router |
| `@tool` | `@tool()` + `Param` |
| `END` | `"end"` |

### 代码转换映射

| LangGraph | openJiuwen |
|-----------|------------|
| `state["key"]` | `inputs["key"]` 或 `runtime.get_global_state("key")` |
| `state.get("key", default)` | `inputs.get("key", default)` |
| `state["key"] = val` | 收集到 `return {"key": val}` |
| `llm.invoke(msgs)` | `await self._llm.ainvoke(model_name=self.model_name, messages=msgs)` |
| `tool.invoke({"arg": val})` | `tool.invoke(inputs={"arg": val})` |
| `tool_map[key].run(arg)` | `invoke_tool(key, arg)` |
| `return state` | `return {"key1": val1, ...}` |
| `return END` | `return "end"` |

### 数据访问规则

| 场景 | 访问方式 |
|------|---------|
| 工作流初始输入 | `runtime.get_global_state("input")` |
| 上游组件通过 `inputs_schema` 传递 | `inputs.get("field")` |
| 更新全局状态 | `runtime.update_global_state({"key": val})` |

### 路由函数转换规则

| 场景 | 转换方式 |
|------|---------|
| 访问上游组件 return 的字段 | `runtime.get_global_state("node.field")` 带前缀 |
| 访问全局状态（非上游输出） | `runtime.get_global_state("field")` 不带前缀 |

```python
# 示例：judge 组件输出 {"is_end": is_end}
# judge_router 中：
def judge_router(runtime) -> str:
    # 上游组件输出 → 带节点前缀
    if runtime.get_global_state("judge.is_end"):
        return "end"
    # 全局状态 → 不带前缀
    if (runtime.get_global_state("loop_count") or 0) >= 3:
        return "end"
    return "think"
```

## 生成的文件结构

```
{agent_name}/
├── __init__.py           # 模块入口
├── config.py             # 配置（LLM、全局变量）
├── tools.py              # 工具函数 + invoke_tool 辅助函数
├── components/
│   ├── __init__.py
│   └── {node}_comp.py    # 每个节点一个组件
├── routers.py            # 路由函数
├── workflow.py           # 工作流构建
└── main.py               # 主入口（含示例输入）
```

## 常用命令

```bash
# 运行迁移
python -m lg2jiuwen_tool source.py -o output/

# 带 AI 处理
python -m lg2jiuwen_tool source.py -o output/ --use-ai

# 运行测试
pytest tests/

# 类型检查
mypy src/lg2jiuwen_tool/
```

## 注意事项

1. **转换前置**：所有代码转换必须在 IRBuilder 之前完成
2. **规则优先**：先尝试规则，失败才用 AI
3. **动态提取**：变量名（如 `tool_map`）从源代码动态提取，不硬编码
4. **示例迁移**：源代码中的示例值自动迁移到生成的代码中
5. **保持幂等**：相同输入应产生相同输出
6. **错误处理**：规则失败时生成 PendingItem，不要抛异常

## 数据流示意图

```
┌─────────────────────────────────────────────────────────────────┐
│                          组件内部                                │
│                                                                 │
│  1. 读取初始输入:  runtime.get_global_state("input")             │
│  2. 读取上游传递:  inputs.get("selected_tool")                   │
│  3. 更新全局状态:  runtime.update_global_state({"is_end": True}) │
│  4. 输出给下游:    return {"is_end": True, "result": ...}        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    自动存储为 "judge.is_end"
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                         路由函数                                 │
│                                                                 │
│  上游组件输出:  runtime.get_global_state("judge.is_end")  带前缀  │
│  全局状态:      runtime.get_global_state("loop_count")    不带前缀│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```
