# AISemanticComp 设计说明

## 1. 组件定位

AISemanticComp 是迁移工作流中的"AI 兜底"组件，用于处理规则无法转换的代码。

```
RuleExtractorComp ──→ AISemanticComp ──→ IRBuilderComp
                          │
                    处理 pending_items
```

---

## 2. 输入输出

```
┌─────────────────────────────────────────────────────────────┐
│                      AISemanticComp                          │
├─────────────────────────────────────────────────────────────┤
│  输入:                                                       │
│    extraction_result: ExtractionResult                      │
│      ├── nodes: [...已转换的节点...]                         │
│      ├── pending_items: [PendingItem, PendingItem, ...]     │
│      └── ...其他字段...                                      │
│                                                              │
│  输出:                                                       │
│    extraction_result: ExtractionResult                      │
│      ├── nodes: [...已转换的节点 + AI转换的节点...]          │
│      ├── pending_items: []  ← 清空                          │
│      ├── ai_count: +n       ← 增加                          │
│      └── ...其他字段...                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. PendingItem 结构

PendingItem 是 RuleExtractor 生成的"待处理项"，作为 AI 的输入：

```python
@dataclass
class PendingItem:
    id: str                    # 唯一标识，如 "file.py:func_name"
    pending_type: PendingType  # 待处理类型
    source_code: str           # 原始代码
    context: Dict[str, Any]    # 上下文信息
    question: str              # 给 AI 的具体问题
    location: str              # 位置信息 "file.py:42"
```

### 3.1 pending_type 类型

| 类型 | 说明 | 示例场景 |
|------|------|----------|
| `NODE_BODY` | 节点函数体转换 | 复杂业务逻辑 |
| `CONDITIONAL` | 条件路由逻辑 | 复杂的路由判断 |
| `TOOL_BODY` | 工具函数体 | 特殊工具实现 |
| `COMPLEX_EXPR` | 复杂表达式 | 嵌套的状态访问 |

### 3.2 context 上下文

```python
context = {
    "state_fields": ["input", "thought", "result", ...],  # 状态字段列表
    "available_tools": ["calculator", "weather"],          # 可用工具
    "failed_lines": [                                      # 规则失败的具体行
        {"line": 5, "code": "result = custom_process(...)"},
        {"line": 8, "code": "state['output'] = transform(x, y)"}
    ]
}
```

---

## 4. 处理流程

```
pending_items 列表
       │
       ▼
┌──────────────────────────────────────────────────┐
│  遍历每个 PendingItem                             │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ 1. 构建 System Prompt                      │  │
│  │    - 基础转换规则                           │  │
│  │    - 根据 pending_type 添加特定规则         │  │
│  └────────────────────────────────────────────┘  │
│                    │                             │
│                    ▼                             │
│  ┌────────────────────────────────────────────┐  │
│  │ 2. 构建 User Prompt                        │  │
│  │    - 上下文: state_fields, available_tools │  │
│  │    - 原始代码: source_code                 │  │
│  │    - 具体问题: question                    │  │
│  └────────────────────────────────────────────┘  │
│                    │                             │
│                    ▼                             │
│  ┌────────────────────────────────────────────┐  │
│  │ 3. 调用 LLM                                │  │
│  │    await self._llm.ainvoke(...)            │  │
│  └────────────────────────────────────────────┘  │
│                    │                             │
│                    ▼                             │
│  ┌────────────────────────────────────────────┐  │
│  │ 4. 解析响应                                │  │
│  │    - 提取代码块 (```python ... ```)        │  │
│  │    - 分析 inputs/outputs                   │  │
│  └────────────────────────────────────────────┘  │
│                    │                             │
│                    ▼                             │
│  ┌────────────────────────────────────────────┐  │
│  │ 5. 生成 ConvertedNode                      │  │
│  │    conversion_source = "ai"                │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
       │
       ▼
extraction_result.nodes.append(...)
extraction_result.ai_count += 1
```

---

## 5. Prompt 设计

### 5.1 System Prompt

```
你是代码转换专家，将 LangGraph 代码转换为 openJiuwen 格式。

openJiuwen 组件规范：
- 异步方法: async def invoke(self, inputs, runtime, context)
- 输入访问: inputs["field_name"]
- 输出返回: return {"field": value}
- LLM调用: await self._llm.ainvoke(model_name=self.model_name, messages=[...])

只输出转换后的代码，不要解释。
```

**条件路由类型额外规则：**

```
条件路由函数规范：
- 函数签名: def router(runtime: WorkflowRuntime) -> str
- 状态访问: runtime.get_global_state('node_name.field_name')
- 返回值是目标节点名字符串
- END 转换为 "end"
```

### 5.2 User Prompt

```
## 上下文
- 状态字段: ['data', 'config', 'output']
- 可用工具: ['calculator', 'weather']

## 原始代码
```python
def complex_node(state: AgentState) -> dict:
    data = state["data"]
    result = custom_process(data, state.get("config"))
    state["output"] = result
    return state
```

## 问题
函数中 custom_process 调用无法用规则转换，请转换为 openJiuwen 格式
```

---

## 6. 示例

### 6.1 输入 PendingItem

```python
PendingItem(
    id="agent.py:complex_node",
    pending_type=PendingType.NODE_BODY,
    source_code="""
def complex_node(state: AgentState) -> dict:
    data = state["data"]
    # 复杂的自定义逻辑，规则无法处理
    result = custom_process(data, state.get("config"))
    state["output"] = result
    return state
""",
    context={
        "state_fields": ["data", "config", "output"],
        "available_tools": [],
        "failed_lines": [
            {"line": 4, "code": "result = custom_process(data, state.get('config'))"}
        ]
    },
    question="函数中 custom_process 调用无法用规则转换，请转换为 openJiuwen 格式",
    location="agent.py:10"
)
```

### 6.2 AI 输出（期望）

```python
data = inputs["data"]
result = custom_process(data, inputs.get("config"))
output = result
```

### 6.3 最终 ConvertedNode

```python
ConvertedNode(
    name="complex_node",
    original_code="def complex_node(state): ...",
    converted_body="data = inputs['data']\nresult = custom_process(data, inputs.get('config'))\noutput = result",
    inputs=["data", "config"],
    outputs=["output"],
    conversion_source="ai"  # 标记为 AI 转换
)
```

---

## 7. 降级处理

当 LLM 不可用或调用失败时，生成 TODO 占位符：

```python
def _fallback_conversion(self, item: PendingItem, error: Optional[str] = None):
    error_comment = f"# AI 转换失败: {error}\n" if error else ""
    code = f"""{error_comment}# TODO: 需要手动转换以下代码
# 原始代码:
# {item.source_code.replace('\n', '\n# ')}
pass"""
    return ConversionResult.success_result(code=code, inputs=[], outputs=[])
```

**输出示例：**

```python
# AI 转换失败: Connection timeout
# TODO: 需要手动转换以下代码
# 原始代码:
# def complex_node(state: AgentState) -> dict:
#     data = state["data"]
#     ...
pass
```

---

## 8. 响应解析

### 8.1 代码提取

从 AI 响应中提取代码块：

```python
def _extract_code(self, response: str) -> str:
    # 优先匹配 ```python ... ```
    pattern = r"```python\s*(.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        return matches[0].strip()

    # 其次匹配 ``` ... ```
    pattern = r"```\s*(.*?)\s*```"
    matches = re.findall(pattern, response, re.DOTALL)
    if matches:
        return matches[0].strip()

    # 最后直接返回响应
    return response.strip()
```

### 8.2 输入输出分析

从转换后的代码中自动分析 inputs 和 outputs：

```python
def _analyze_io(self, code: str) -> Tuple[List[str], List[str]]:
    inputs = []
    outputs = []

    # 查找 inputs["xxx"] 或 inputs.get("xxx")
    input_pattern = r'inputs\["(\w+)"\]|inputs\.get\("(\w+)"'
    for match in re.finditer(input_pattern, code):
        key = match.group(1) or match.group(2)
        if key and key not in inputs:
            inputs.append(key)

    # 查找 return {"xxx": ...} 中的 key
    output_pattern = r'"(\w+)":'
    for match in re.finditer(output_pattern, code):
        key = match.group(1)
        if key and key not in outputs:
            outputs.append(key)

    return inputs, outputs
```

---

## 9. 与其他组件的关系

```
┌─────────────────┐
│ RuleExtractorComp│
│                 │
│ 规则转换成功 ──→ nodes
│ 规则转换失败 ──→ pending_items
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PendingCheckComp │ ──→ 检查是否有 pending_items
└────────┬────────┘
         │
    has_pending?
    ┌────┴────┐
   Yes       No
    │         │
    ▼         │
┌─────────────────┐
│ AISemanticComp  │
│                 │
│ pending_items ──→ AI 转换 ──→ nodes
│ pending_items = []
└────────┬────────┘
         │         │
         └────┬────┘
              │
              ▼
┌─────────────────┐
│   IRBuilderComp │ ──→ 此时 pending_items 必须为空
└─────────────────┘
```

---

## 10. 输出到 IR 的完整数据流

### 10.1 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RuleExtractorComp                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  输出 ExtractionResult:                                                  │
│    nodes: [                                                              │
│      ConvertedNode(name="think", conversion_source="rule", ...),        │
│      ConvertedNode(name="judge", conversion_source="rule", ...),        │
│    ]                                                                     │
│    pending_items: [                                                      │
│      PendingItem(id="agent.py:complex_node", ...)  ← 规则转换失败        │
│    ]                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         AISemanticComp                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  处理 pending_items，生成新的 ConvertedNode                              │
│                                                                          │
│  输出 ExtractionResult:                                                  │
│    nodes: [                                                              │
│      ConvertedNode(name="think", conversion_source="rule", ...),        │
│      ConvertedNode(name="judge", conversion_source="rule", ...),        │
│      ConvertedNode(name="complex_node", conversion_source="ai", ...),   │
│                                                        ↑                 │
│                                                   AI 新增的              │
│    ]                                                                     │
│    pending_items: []  ← 清空                                             │
│    ai_count: 1        ← 增加                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          IRBuilderComp                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  统一处理所有 nodes（不区分来源）                                         │
│                                                                          │
│  for node in result.nodes:   # 遍历所有节点                              │
│      nodes_ir.append(WorkflowNodeIR(                                     │
│          name=node.name,                                                 │
│          class_name=self._to_class_name(node.name),  # 新增              │
│          converted_body=node.converted_body,         # 保持              │
│          inputs=node.inputs,                         # 保持              │
│          outputs=node.outputs,                       # 保持              │
│          conversion_source=node.conversion_source,   # 保持 "rule"/"ai" │
│          has_llm=...,                                # 新增：检测        │
│          has_tools=...,                              # 新增：检测        │
│      ))                                                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           MigrationIR                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  workflow_ir.nodes: [                                                    │
│    WorkflowNodeIR(name="think", class_name="ThinkComp",                  │
│                   conversion_source="rule", ...),                        │
│    WorkflowNodeIR(name="judge", class_name="JudgeComp",                  │
│                   conversion_source="rule", ...),                        │
│    WorkflowNodeIR(name="complex_node", class_name="ComplexNodeComp",     │
│                   conversion_source="ai", ...),                          │
│  ]                                                                       │
│                                                                          │
│  conversion_stats: {                                                     │
│    "rule_count": 2,                                                      │
│    "ai_count": 1,       ← 记录 AI 转换数量                               │
│    "total_nodes": 3,                                                     │
│  }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 字段转换对应

| ExtractionResult (ConvertedNode) | → | IR (WorkflowNodeIR) |
|----------------------------------|---|---------------------|
| `name` | → | `name` |
| - | → | `class_name` (新增：think → ThinkComp) |
| `converted_body` | → | `converted_body` |
| `inputs` | → | `inputs` |
| `outputs` | → | `outputs` |
| `conversion_source` ("rule"/"ai") | → | `conversion_source` (保留) |
| `docstring` | → | `docstring` |
| - | → | `has_llm` (新增：检测代码) |
| - | → | `has_tools` (新增：检测代码) |

### 10.3 IRBuilder 核心代码

```python
# IRBuilderComp._build_nodes_ir()
def _build_nodes_ir(self, result: ExtractionResult) -> List[WorkflowNodeIR]:
    nodes_ir = []
    for node in result.nodes:  # 遍历所有节点（包含 rule 和 ai 转换的）
        nodes_ir.append(WorkflowNodeIR(
            name=node.name,
            class_name=self._to_class_name(node.name),      # think → ThinkComp
            converted_body=node.converted_body,
            inputs=node.inputs,
            outputs=node.outputs,
            conversion_source=node.conversion_source,        # "rule" 或 "ai"
            docstring=node.docstring,
            has_llm=self._has_llm_call(node.converted_body),
            has_tools=self._has_tool_call(node.converted_body, result)
        ))
    return nodes_ir
```

### 10.4 各阶段数据状态

| 阶段 | 数据结构 | AI 转换节点的状态 |
|------|----------|-------------------|
| RuleExtractor 后 | `ExtractionResult.pending_items` | 待处理 (PendingItem) |
| AISemantic 后 | `ExtractionResult.nodes` | 已转换 (`conversion_source="ai"`) |
| IRBuilder 后 | `WorkflowNodeIR` | 已构建 (`conversion_source="ai"`) |
| 最终 IR | `MigrationIR.conversion_stats` | 统计 (`ai_count: n`) |

**关键点**：AI 转换的节点和规则转换的节点，在 IR 构建时是**统一处理**的，唯一的区别是 `conversion_source` 字段的值。

---

## 11. 总结

| 项目 | 说明 |
|------|------|
| **输入** | `ExtractionResult`（含 `pending_items`） |
| **输出** | `ExtractionResult`（`pending_items` 清空，`nodes` 增加） |
| **核心功能** | 调用 AI 转换规则无法处理的代码 |
| **降级策略** | 生成 TODO 占位符，标记需手动处理 |
| **标记方式** | `conversion_source = "ai"` |
| **IR 输出** | 与规则转换统一处理，通过 `conversion_source` 区分来源 |
