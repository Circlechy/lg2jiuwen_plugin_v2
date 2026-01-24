# 待支持功能分析文档

> 基于 openJiuwen API 文档分析 LangGraph 待支持功能的实现方案

---

## 概述

README 中列出的待支持功能：

| 功能 | LangGraph | openJiuwen 对应能力 | 实现难度 |
|------|-----------|-------------------|---------|
| 子图 (Subgraph) | `CompiledGraph` 嵌套 | `SubWorkflowComponent` | ⭐⭐ 中等 |
| 并行节点 | 多边汇聚 | `wait_for_all=True` | ⭐⭐ 中等 |
| Checkpointer 持久化 | `MemorySaver`/`SqliteSaver` | `MemoryEngine` + `INPUT_REQUIRED` | ⭐⭐⭐ 较高 |
| 流式输出 (Streaming) | `stream()` | `stream()` + `add_stream_connection()` | ⭐⭐ 中等 |
| 动态节点添加 | 运行时 `add_node` | 暂不支持 | ⭐⭐⭐⭐ 高 |

---

## 1. 子图 (Subgraph) 支持

### 1.1 LangGraph 子图用法

```python
# LangGraph 子图定义
from langgraph.graph import StateGraph

# 子图
sub_workflow = StateGraph(SubState)
sub_workflow.add_node("sub_node", sub_func)
sub_workflow.set_entry_point("sub_node")
sub_graph = sub_workflow.compile()

# 主图嵌入子图
main_workflow = StateGraph(MainState)
main_workflow.add_node("sub", sub_graph)  # 子图作为节点
main_workflow.add_edge("entry", "sub")
```

### 1.2 openJiuwen 对应实现

openJiuwen 提供 `SubWorkflowComponent` 来实现子工作流：

```python
from openjiuwen.core.component.workflow_comp import SubWorkflowComponent
from openjiuwen.core.workflow.base import Workflow

# 子工作流
sub_workflow = Workflow()
sub_workflow.set_start_comp("sub_start", Start(), inputs_schema={"query": "${query}"})
sub_workflow.add_workflow_comp("sub_node", SubComponent(), inputs_schema={"query": "${sub_start.query}"})
sub_workflow.set_end_comp("sub_end", End(), inputs_schema={"result": "${sub_node.result}"})
sub_workflow.add_connection("sub_start", "sub_node")
sub_workflow.add_connection("sub_node", "sub_end")

# 主工作流嵌入子工作流
main_workflow = Workflow()
sub_workflow_comp = SubWorkflowComponent(sub_workflow)  # 包装为组件
main_workflow.add_workflow_comp("sub", sub_workflow_comp, inputs_schema={"query": "${start.query}"})
```

### 1.3 转换方案

**Parser 改动**：
- 识别 `workflow.add_node("name", compiled_graph)` 中 `compiled_graph` 是否为子图
- 递归解析子图的节点、边定义

**Generator 改动**：
- 生成 `Workflow()` 子工作流定义
- 用 `SubWorkflowComponent(sub_workflow)` 包装
- 处理子工作流的输入输出 schema 映射

**映射表**：

| LangGraph | openJiuwen |
|-----------|------------|
| `sub_graph = sub_workflow.compile()` | `sub_workflow = Workflow()` |
| `main.add_node("sub", sub_graph)` | `SubWorkflowComponent(sub_workflow)` |
| 子图状态透传 | `inputs_schema` + `${sub.output.field}` |

---

## 2. 并行节点支持

### 2.1 LangGraph 并行用法

```python
# LangGraph 并行：多个节点同时执行
workflow.add_node("node_a", func_a)
workflow.add_node("node_b", func_b)
workflow.add_node("merge", merge_func)

# 从同一源节点分叉
workflow.add_edge("start", "node_a")
workflow.add_edge("start", "node_b")

# 汇聚到同一目标
workflow.add_edge("node_a", "merge")
workflow.add_edge("node_b", "merge")
```

### 2.2 openJiuwen 对应实现

openJiuwen 使用 `wait_for_all=True` 实现汇聚等待：

```python
# 分叉
workflow.add_connection("start", "node_a")
workflow.add_connection("start", "node_b")

# 汇聚组件需要等待所有上游完成
workflow.add_workflow_comp(
    "merge",
    MergeComponent(),
    wait_for_all=True,  # 关键：等待所有前置节点
    inputs_schema={
        "result_a": "${node_a.output}",
        "result_b": "${node_b.output}"
    }
)
workflow.add_connection("node_a", "merge")
workflow.add_connection("node_b", "merge")
```

### 2.3 转换方案

**Parser 改动**：
- 分析边的拓扑结构，识别「分叉-汇聚」模式
- 记录每个节点的入边数量

**Generator 改动**：
- 入边数量 > 1 的节点，生成 `wait_for_all=True`
- 正确生成多上游的 `inputs_schema`

**检测逻辑**：
```python
def detect_merge_nodes(edges):
    """检测需要 wait_for_all 的节点"""
    incoming_count = defaultdict(int)
    for edge in edges:
        incoming_count[edge.target] += 1

    return {node for node, count in incoming_count.items() if count > 1}
```

---

## 3. Checkpointer 持久化支持

### 3.1 LangGraph Checkpointer 用法

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 内存检查点
checkpointer = MemorySaver()

# SQLite 持久化
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

# 编译时传入
graph = workflow.compile(checkpointer=checkpointer)

# 使用 thread_id 恢复会话
config = {"configurable": {"thread_id": "user_123"}}
result = graph.invoke(inputs, config)

# 获取历史状态
history = graph.get_state_history(config)
```

### 3.2 openJiuwen 对应能力分析

openJiuwen 的持久化通过 **MemoryEngine** 实现，但设计理念不同：

| 维度 | LangGraph Checkpointer | openJiuwen MemoryEngine |
|------|----------------------|------------------------|
| 目的 | 保存图执行状态，支持恢复和回放 | 保存用户记忆/变量，支持语义检索 |
| 粒度 | 每个节点执行后自动保存 | 按 user_id/group_id/session_id 组织 |
| 恢复 | 从任意检查点恢复执行 | 恢复用户变量，重新执行工作流 |
| 存储 | 内存/SQLite/Postgres | KV/语义向量/SQL 多存储 |

**openJiuwen 的相关能力**：

1. **WorkflowExecutionState.INPUT_REQUIRED**：工作流中断等待用户输入
2. **MemoryEngine**：用户记忆持久化
3. **WorkflowRuntime**：维护 `global_state`

### 3.3 转换方案（部分支持）

由于设计理念差异，建议分两个层次实现：

#### 层次 1：会话状态恢复（可实现）

```python
# 生成的代码示例
from openjiuwen.core.memory.engine import MemoryEngine

class StatefulWorkflow:
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self.memory = MemoryEngine.get_mem_engine_instance()

    async def run(self, inputs: dict) -> dict:
        # 恢复上次状态
        saved_vars = await self.memory.list_user_variables(
            user_id=self.user_id,
            group_id="workflow_state"
        )

        # 合并输入
        merged_inputs = {**saved_vars, **inputs}

        # 执行工作流
        result = await self.workflow.invoke(merged_inputs, self.runtime)

        # 保存新状态
        for key, value in result.items():
            await self.memory.update_user_variable(
                user_id=self.user_id,
                group_id="workflow_state",
                name=key,
                value=str(value)
            )

        return result
```

#### 层次 2：节点级检查点（需要扩展）

完整的检查点功能需要 openJiuwen 框架层面支持，当前建议：
- 在迁移报告中标注「需要手动实现检查点逻辑」
- 生成注释代码提供实现模板

**Parser 改动**：
- 识别 `compile(checkpointer=...)` 调用
- 提取 `thread_id` 配置

**Generator 改动**：
- 生成 `MemoryEngine` 初始化代码（可选）
- 生成状态恢复/保存的辅助代码
- 在报告中标注手动处理项

---

## 4. 流式输出 (Streaming) 支持

### 4.1 LangGraph 流式用法

```python
# LangGraph 流式输出
for event in graph.stream(inputs):
    print(event)

# 指定流模式
for event in graph.stream(inputs, stream_mode="values"):
    print(event)

for event in graph.stream(inputs, stream_mode="updates"):
    print(event)
```

### 4.2 openJiuwen 流式 API

openJiuwen 提供丰富的流式能力：

```python
from openjiuwen.core.stream.base import BaseStreamMode

# 流式执行
async for chunk in workflow.stream(inputs, runtime, stream_modes=[BaseStreamMode.OUTPUT]):
    print(chunk)

# 流式连接（组件间）
workflow.add_stream_connection("llm", "end")

# 组件内部写流式输出
async def invoke(self, inputs, runtime, context):
    # 写入自定义流
    await runtime.write_custom_stream(custom_output="partial result")
```

**流模式对比**：

| LangGraph | openJiuwen | 说明 |
|-----------|------------|------|
| `stream_mode="values"` | `BaseStreamMode.OUTPUT` | 标准输出流 |
| `stream_mode="updates"` | `BaseStreamMode.TRACE` | 每个节点的更新（调试信息）|
| `stream_mode="messages"` | `BaseStreamMode.CUSTOM` | 自定义消息流 |

### 4.3 转换方案

**Parser 改动**：
- 识别 `graph.stream()` 调用
- 提取 `stream_mode` 参数

**Generator 改动**：
- 生成 `async for chunk in workflow.stream(...)` 代码
- 需要流式的组件间连接使用 `add_stream_connection()`
- LLM 组件默认支持流式，生成相应配置

**代码生成示例**：

```python
# LangGraph
for event in graph.stream({"input": "hello"}):
    print(event)

# 生成的 openJiuwen
async def run_stream(inputs):
    runtime = WorkflowRuntime()
    async for chunk in workflow.stream(
        inputs,
        runtime,
        stream_modes=[BaseStreamMode.OUTPUT, BaseStreamMode.TRACE]
    ):
        if isinstance(chunk, OutputSchema):
            print(f"Output: {chunk.payload}")
        elif isinstance(chunk, TraceSchema):
            print(f"Node {chunk.payload['invokeId']}: {chunk.payload['status']}")
```

---

## 5. 实现优先级建议

### 第一优先级：流式输出

- **原因**：使用频率高，映射关系清晰
- **工作量**：Parser 改动小，Generator 需增加流式模板
- **风险**：低

### 第二优先级：并行节点

- **原因**：拓扑分析逻辑较清晰
- **工作量**：需要增加入边分析，生成 `wait_for_all`
- **风险**：中（需要测试边界情况）

### 第三优先级：子图

- **原因**：需要递归解析和嵌套生成
- **工作量**：Parser 和 Generator 都需要较大改动
- **风险**：中高（子图间数据传递复杂）

### 第四优先级：Checkpointer

- **原因**：设计理念差异大，只能部分支持
- **工作量**：需要生成辅助代码，用户需手动完善
- **风险**：高（功能受限，需明确告知用户）

### 暂不支持：动态节点添加

- **原因**：openJiuwen 工作流结构在运行前确定
- **建议**：在迁移报告中明确标注不支持

---

## 6. IR 模型扩展

为支持新功能，需要扩展 `ir_models.py`：

```python
@dataclass
class WorkflowNodeIR:
    # 现有字段...

    # 新增字段
    is_subgraph: bool = False              # 是否为子图节点
    subgraph_ir: Optional['WorkflowIR'] = None  # 子图的 IR
    wait_for_all: bool = False             # 是否等待所有上游
    supports_streaming: bool = False        # 是否支持流式输出


@dataclass
class WorkflowIR:
    # 现有字段...

    # 新增字段
    has_parallel: bool = False             # 是否包含并行结构
    merge_nodes: List[str] = field(default_factory=list)  # 汇聚节点列表
    stream_edges: List[WorkflowEdgeIR] = field(default_factory=list)  # 流式边


@dataclass
class CheckpointerIR:
    """检查点配置 IR"""
    enabled: bool = False
    storage_type: str = "memory"           # memory/sqlite/postgres
    thread_id_source: Optional[str] = None # thread_id 来源
```

---

## 7. 测试用例设计

### 子图测试

```python
# test_subgraph.py
def test_subgraph_conversion():
    """测试子图转换"""
    source = '''
    sub = StateGraph(SubState)
    sub.add_node("process", process_func)
    sub_graph = sub.compile()

    main = StateGraph(MainState)
    main.add_node("sub", sub_graph)
    '''
    # 验证生成 SubWorkflowComponent
```

### 并行测试

```python
# test_parallel.py
def test_parallel_merge():
    """测试并行汇聚"""
    source = '''
    workflow.add_edge("start", "a")
    workflow.add_edge("start", "b")
    workflow.add_edge("a", "merge")
    workflow.add_edge("b", "merge")
    '''
    # 验证 merge 节点有 wait_for_all=True
```

### 流式测试

```python
# test_streaming.py
def test_stream_conversion():
    """测试流式调用转换"""
    source = '''
    for event in graph.stream(inputs):
        print(event)
    '''
    # 验证生成 async for + stream()
```

---

## 8. 迁移报告模板更新

```
=== 迁移报告 ===

已支持特性:
  ✓ 节点函数 -> WorkflowComponent
  ✓ 条件边 -> conditional_connection
  ✓ 子图 -> SubWorkflowComponent (NEW)
  ✓ 并行节点 -> wait_for_all (NEW)
  ✓ 流式输出 -> stream() (NEW)

部分支持:
  △ Checkpointer -> 已生成 MemoryEngine 辅助代码，需手动完善

不支持:
  ✗ 动态节点添加 - openJiuwen 不支持运行时修改工作流结构

手动处理项:
  [ ] 检查子图输入输出映射是否正确
  [ ] 验证并行节点的数据汇聚逻辑
  [ ] 如需完整检查点功能，请参考生成的 StatefulWorkflow 模板
```
