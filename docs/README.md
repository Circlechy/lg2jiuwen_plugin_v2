# LG2Jiuwen 迁移工具 - 技术方案文档

> 面向开发团队的完整技术方案说明

---

## 1. 项目概述

### 1.1 目标

将基于 LangGraph 框架开发的 Agent 代码自动迁移至 openJiuwen 框架。

### 1.2 核心特性

- 支持单文件和多文件项目，自动检测
- 采用"规则优先，AI 兜底"策略
- 使用 openJiuwen 框架自身实现（自举）
- 可插拔的规则系统，易于扩展

---

## 2. 特性支持清单

### 2.1 已支持特性

| 分类 | LangGraph 特性 | openJiuwen 映射 | 状态 |
|------|---------------|-----------------|------|
| **图定义** | `StateGraph(State)` | `Workflow()` | ✅ 已支持 |
| **状态** | `TypedDict` 状态类 | `inputs_schema` 传递 | ✅ 已支持 |
| **节点** | `add_node(name, func)` | `add_workflow_comp(name, Comp)` | ✅ 已支持 |
| **普通边** | `add_edge(a, b)` | `add_connection(a, b)` | ✅ 已支持 |
| **条件边** | `add_conditional_edges()` | `add_conditional_connection()` + router | ✅ 已支持 |
| **入口点** | `set_entry_point(node)` | `set_start_comp()` | ✅ 已支持 |
| **结束标识** | `END` | `"end"` | ✅ 已支持 |
| **工具** | `@tool` 装饰器 | `@tool()` + `Param` | ✅ 已支持 |
| **LLM** | `ChatOpenAI(...)` | `OpenAIChatModel(...)` | ✅ 已支持 |

### 2.2 待支持特性

| 分类 | LangGraph 特性 | openJiuwen 映射 | 实现难度 | 优先级 |
|------|---------------|-----------------|----------|--------|
| **子图** | `CompiledGraph` 嵌套 | `SubWorkflowComponent` | ⭐⭐ 中等 | P1 |
| **并行节点** | 多边汇聚 | `wait_for_all=True` | ⭐⭐ 中等 | P1 |
| **流式输出** | `graph.stream()` | `workflow.stream()` + `add_stream_connection()` | ⭐⭐ 中等 | P1 |
| **检查点** | `MemorySaver`/`SqliteSaver` | `MemoryEngine` + 辅助代码 | ⭐⭐⭐ 较高 | P2 |
| **动态节点** | 运行时 `add_node` | 暂不支持 | ⭐⭐⭐⭐ 高 | P3 |

### 2.3 代码转换规则支持

#### 已支持的代码模式

| 模式 | LangGraph 代码 | openJiuwen 代码 | 状态 |
|------|---------------|-----------------|------|
| 状态读取 | `state["key"]` | `inputs["key"]` | ✅ |
| 状态读取(safe) | `state.get("key")` | `inputs.get("key")` | ✅ |
| 状态读取(default) | `state.get("key", default)` | `inputs.get("key", default)` | ✅ |
| 状态写入 | `state["key"] = value` | 收集到返回字典 | ✅ |
| LLM 同步调用 | `llm.invoke(messages)` | `await self._llm.ainvoke(model_name, messages)` | ✅ |
| LLM 内容获取 | `llm.invoke(msgs).content` | `(await self._llm.ainvoke(...)).content` | ✅ |
| 工具调用 | `tool.invoke({"arg": val})` | `tool(arg=val)` | ✅ |
| 返回状态 | `return state` | `return {"key1": v1, "key2": v2}` | ✅ |
| 返回结束 | `return END` | `return "end"` | ✅ |
| 条件返回 | `return END if cond else "node"` | `return "end" if cond else "node"` | ✅ |

#### 待支持/需 AI 处理的代码模式

| 模式 | 示例 | 原因 | 处理方式 |
|------|------|------|----------|
| 复杂状态计算 | `state["x"] = process(state["a"], state["b"], ext)` | 需理解 process 语义 | AI |
| 非标准 LLM | `custom_chain.run(...)` | 非标准调用方式 | AI |
| 动态调用 | `getattr(obj, method)()` | 无法静态分析 | AI |
| 循环状态修改 | `for i in items: state["list"].append(...)` | 累积逻辑复杂 | AI |
| 闭包/高阶函数 | `map(lambda x: ..., items)` | 需理解语义 | AI |
| 异常处理 | `try: ... except CustomError: ...` | 需映射异常类型 | AI |

### 2.4 待支持特性详细说明

#### 子图 (Subgraph)

```python
# LangGraph
sub_workflow = StateGraph(SubState)
sub_workflow.add_node("sub_node", sub_func)
sub_graph = sub_workflow.compile()

main_workflow = StateGraph(MainState)
main_workflow.add_node("sub", sub_graph)  # 子图作为节点

# openJiuwen 映射
sub_workflow = Workflow()
# ... 子工作流定义
sub_comp = SubWorkflowComponent(sub_workflow)
main_workflow.add_workflow_comp("sub", sub_comp, inputs_schema={...})
```

#### 并行节点

```python
# LangGraph - 分叉汇聚
workflow.add_edge("start", "node_a")
workflow.add_edge("start", "node_b")
workflow.add_edge("node_a", "merge")
workflow.add_edge("node_b", "merge")

# openJiuwen 映射
workflow.add_connection("start", "node_a")
workflow.add_connection("start", "node_b")
workflow.add_workflow_comp("merge", MergeComp(), wait_for_all=True, ...)  # 关键
workflow.add_connection("node_a", "merge")
workflow.add_connection("node_b", "merge")
```

#### 流式输出

```python
# LangGraph
for event in graph.stream(inputs):
    print(event)

# openJiuwen 映射
async for chunk in workflow.stream(inputs, runtime, stream_modes=[BaseStreamMode.OUTPUT]):
    print(chunk)
```

#### Checkpointer (部分支持)

```python
# LangGraph
checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)
result = graph.invoke(inputs, {"configurable": {"thread_id": "123"}})

# openJiuwen 映射 (需生成辅助代码)
class StatefulWorkflow:
    def __init__(self, user_id, session_id):
        self.memory = MemoryEngine.get_mem_engine_instance()

    async def run(self, inputs):
        # 恢复状态
        saved = await self.memory.list_user_variables(...)
        merged = {**saved, **inputs}
        result = await self.workflow.invoke(merged, runtime)
        # 保存状态
        for k, v in result.items():
            await self.memory.update_user_variable(...)
        return result
```

---

## 3. 核心设计原则

### 3.1 规则优先，AI 兜底

```
输入代码 ──▶ 规则处理 ──▶ 成功 ──▶ 输出
                │
                失败
                │
                ▼
           AI 处理 ──▶ 输出
```

| 方式 | 优点 | 缺点 |
|------|------|------|
| 规则 | 快速、确定、低成本、可调试 | 覆盖有限 |
| AI | 灵活、语义理解强 | 成本高、不确定 |

### 3.2 转换前置

所有代码转换在 IR 构建之前完成：

```
AST ──▶ RuleExtractor ──▶ AISemantic ──▶ IR ──▶ CodeGenerator
         (转换代码)      (转换剩余)   (已转换)   (模板填充)
              │              │                      │
              └── 需要理解 ──┘                  不需要AI
```

**关键**：IR 存储已转换的代码，CodeGenerator 只做模板填充。

---

## 4. 整体架构

### 4.1 工作流架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         迁移工作流                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  输入: source_path, output_dir                                    │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │ ProjectDetector │ 检测单/多文件，分析依赖                       │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │   FileLoader    │ 加载文件内容                                  │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │   ASTParser     │ 解析 AST                                     │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │ RuleExtractor   │ 规则提取 + 转换（核心）                       │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐     ┌─────────────────┐                     │
│  │  PendingCheck   │──▶  │  AISemantic     │ (有待处理项时)       │
│  └─────────────────┘     └─────────────────┘                     │
│         │                        │                                │
│         └────────┬───────────────┘                                │
│                  ▼                                                │
│  ┌─────────────────┐                                              │
│  │   IRBuilder     │ 构建 IR（代码已转换）                         │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │ CodeGenerator   │ 模板填充（不需要 AI）                         │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────┐                                              │
│  │    Report       │ 生成迁移报告                                  │
│  └─────────────────┘                                              │
│         │                                                         │
│         ▼                                                         │
│  输出: openJiuwen 代码 + 报告                                      │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 组件职责

| 组件 | 职责 | 需要 AI |
|------|------|---------|
| ProjectDetector | 检测项目类型，分析文件依赖 | 否 |
| FileLoader | 读取文件内容 | 否 |
| ASTParser | 解析 Python AST | 否 |
| **RuleExtractor** | 规则提取结构 + 转换代码 | 否 |
| PendingCheck | 检查是否有待处理项 | 否 |
| **AISemantic** | AI 转换规则失败的代码 | **是** |
| IRBuilder | 组装 IR 结构 | 否 |
| CodeGenerator | 模板填充生成代码 | 否 |
| Report | 生成迁移报告 | 否 |

---

## 5. 核心数据模型

### 5.1 待处理项

```python
@dataclass
class PendingItem:
    id: str                      # "file.py:func_name"
    pending_type: PendingType    # NODE_BODY / CONDITIONAL / TOOL_BODY
    source_code: str             # 原始代码
    context: Dict[str, Any]      # 状态字段、可用工具、失败行
    question: str                # 给 AI 的具体问题
    location: str                # "file:line"
```

### 5.2 已转换节点

```python
@dataclass
class ConvertedNode:
    name: str                    # 节点名
    original_code: str           # 原始代码
    converted_body: str          # 已转换的函数体
    inputs: List[str]            # 输入字段
    outputs: List[str]           # 输出字段
    conversion_source: str       # "rule" 或 "ai"
```

### 5.3 提取结果

```python
@dataclass
class ExtractionResult:
    states: List[Dict]
    nodes: List[ConvertedNode]
    edges: List[Dict]
    tools: List[Dict]
    llm_configs: List[Dict]
    pending_items: List[PendingItem]
    rule_count: int = 0
    ai_count: int = 0
```

---

## 6. 转换规则系统

### 6.1 规则基类

```python
class BaseRule(ABC):
    @abstractmethod
    def matches(self, node: ast.AST) -> bool:
        pass

    @abstractmethod
    def convert(self, node: ast.AST) -> ConversionResult:
        pass
```

### 6.2 规则清单

| 规则类 | 文件 | 匹配模式 | 转换结果 |
|--------|------|----------|----------|
| StateAccessRule | state_rules.py | `state["key"]` | `inputs["key"]` |
| StateGetRule | state_rules.py | `state.get("key")` | `inputs.get("key")` |
| StateAssignRule | state_rules.py | `state["key"] = val` | 收集到 outputs |
| LLMInvokeRule | llm_rules.py | `llm.invoke(msgs)` | `await self._llm.ainvoke(...)` |
| LLMContentRule | llm_rules.py | `llm.invoke(msgs).content` | `(await ...).content` |
| ToolCallRule | tool_rules.py | `tool.invoke({...})` | `tool(...)` |
| EndReturnRule | edge_rules.py | `return END` | `return "end"` |
| ConditionalReturnRule | edge_rules.py | `return END if c else "n"` | `return "end" if c else "n"` |
| SimpleReturnRule | edge_rules.py | `return state` | `return {outputs}` |

### 6.3 规则匹配流程

```python
def try_convert_body(func_node) -> ConversionResult:
    converted_lines = []
    failed_lines = []

    for stmt in func_node.body:
        matched = False
        for rule in self.rules:
            if rule.matches(stmt):
                result = rule.convert(stmt)
                converted_lines.append(result.code)
                matched = True
                break

        if not matched:
            failed_lines.append({"line": stmt.lineno, "code": ast.unparse(stmt)})

    if failed_lines:
        return ConversionResult(success=False, failed_lines=failed_lines)

    return ConversionResult(success=True, code="\n".join(converted_lines))
```

---

## 7. 目录结构

```
src/lg2jiuwen_tool/
├── workflow/
│   ├── migration_workflow.py    # 主工作流
│   └── state.py                 # 状态和数据模型
├── components/
│   ├── project_detector.py      # 项目检测
│   ├── file_loader.py           # 文件加载
│   ├── ast_parser.py            # AST 解析
│   ├── rule_extractor.py        # 规则提取+转换
│   ├── pending_check.py         # 待处理检查
│   ├── ai_semantic.py           # AI 语义理解
│   ├── ir_builder.py            # IR 构建
│   ├── code_generator.py        # 代码生成
│   └── report.py                # 报告生成
├── rules/
│   ├── base.py                  # 规则基类
│   ├── state_rules.py           # 状态规则
│   ├── llm_rules.py             # LLM 规则
│   ├── tool_rules.py            # 工具规则
│   └── edge_rules.py            # 边规则
├── ir/
│   └── models.py                # IR 模型
├── templates/
│   ├── component.py.jinja       # 组件模板
│   ├── workflow.py.jinja        # 工作流模板
│   └── router.py.jinja          # 路由模板
├── service.py
└── cli.py
```

---

## 8. 开发任务

### Phase 1: 基础框架 (P0)

| 任务 | 文件 | 说明 |
|------|------|------|
| 数据模型 | `workflow/state.py` | PendingItem, ConvertedNode, ExtractionResult |
| IR 模型 | `ir/models.py` | WorkflowNodeIR, WorkflowEdgeIR, AgentIR |
| 规则基类 | `rules/base.py` | BaseRule, ConversionResult |
| 工作流骨架 | `workflow/migration_workflow.py` | 组件连接定义 |

### Phase 2: 核心组件 (P0)

| 任务 | 文件 | 依赖 |
|------|------|------|
| 项目检测 | `components/project_detector.py` | - |
| 文件加载 | `components/file_loader.py` | project_detector |
| AST 解析 | `components/ast_parser.py` | file_loader |
| 规则提取 | `components/rule_extractor.py` | ast_parser, rules/* |
| 待处理检查 | `components/pending_check.py` | rule_extractor |
| AI 语义 | `components/ai_semantic.py` | pending_check |
| IR 构建 | `components/ir_builder.py` | rule_extractor/ai_semantic |
| 代码生成 | `components/code_generator.py` | ir_builder |
| 报告生成 | `components/report.py` | code_generator |

### Phase 3: 转换规则 (P0)

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 状态访问规则 | `rules/state_rules.py` | 高 |
| LLM 调用规则 | `rules/llm_rules.py` | 高 |
| 工具调用规则 | `rules/tool_rules.py` | 中 |
| 边/路由规则 | `rules/edge_rules.py` | 高 |

### Phase 4: 待支持特性 (P1)

| 任务 | 说明 | 难度 |
|------|------|------|
| 子图支持 | 递归解析，SubWorkflowComponent | 中 |
| 并行节点 | 入边分析，wait_for_all | 中 |
| 流式输出 | stream() 映射 | 中 |

### Phase 5: 模板和测试 (P1)

| 任务 | 说明 |
|------|------|
| 代码模板 | `templates/*.jinja` |
| 单元测试 | 规则和组件测试 |
| 集成测试 | 完整流程测试 |

---

## 9. 使用方式

### 命令行

```bash
# 单文件
python -m lg2jiuwen_tool my_agent.py -o output/

# 多文件目录
python -m lg2jiuwen_tool my_project/ -o output/

# 详细输出
python -m lg2jiuwen_tool my_agent.py -o output/ --verbose
```

### 编程接口

```python
from lg2jiuwen_tool import migrate, MigrationOptions

options = MigrationOptions(
    preserve_comments=True,
    include_report=True
)

result = migrate(
    source_path="my_agent.py",
    output_dir="./output",
    options=options
)

print(f"生成文件: {result.generated_files}")
print(f"规则处理: {result.rule_count}, AI处理: {result.ai_count}")
```

---

## 10. 迁移报告示例

```
=== LangGraph to openJiuwen 迁移报告 ===

源文件: weather_agent.py
输出目录: ./output

## 转换统计

| 项目 | 规则处理 | AI 处理 | 总计 |
|------|---------|---------|------|
| 状态字段 | 5 | 0 | 5 |
| 节点函数 | 2 | 0 | 2 |
| 边定义 | 3 | 0 | 3 |
| 工具函数 | 1 | 0 | 1 |

## 特性支持

✅ 已支持:
  - StateGraph 状态图
  - TypedDict 状态类
  - add_node() 节点
  - add_edge() 普通边
  - add_conditional_edges() 条件边
  - @tool 工具装饰器

⚠️ 未使用的待支持特性:
  - 子图 (Subgraph)
  - 并行节点
  - 流式输出

## 生成文件

- output/weather_agent_openjiuwen.py
- output/weather_agent_openjiuwen_report.txt
- output/weather_agent_openjiuwen_ir.json

## 手动检查项

[ ] 验证 LLM 配置（API Key, API Base）
[ ] 测试条件路由逻辑
[ ] 确认异步运行环境
```

---

## 11. 参考文档

- [详细设计文档](./agent_workflow_design_v2.md)
- [待支持功能分析](./unsupported_features_analysis.md)
- [开发规则 CLAUDE.md](../CLAUDE.md)
