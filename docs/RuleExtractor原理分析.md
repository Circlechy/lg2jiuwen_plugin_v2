# RuleExtractorComp 原理分析

## 1. 核心原理

### 1.1 设计模式

RuleExtractorComp 运用了三种核心设计模式：

```
┌─────────────────────────────────────────────────────────────────┐
│                      RuleExtractorComp                          │
├─────────────────────────────────────────────────────────────────┤
│  ① 访问者模式 (Visitor Pattern)                                 │
│     ast.walk(tree) 遍历 AST 节点                                │
│                                                                 │
│  ② 责任链模式 (Chain of Responsibility)                         │
│     RuleChain 依次尝试多个规则                                   │
│                                                                 │
│  ③ 转换器模式 (Transformer Pattern)                             │
│     StateToInputsTransformer 递归转换 AST                       │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 规则链机制

```python
RuleChain([
    StateAccessRule(),    # state["x"] → inputs["x"]
    StateAssignRule(),    # state["x"] = v → x = v
    LLMInvokeRule(),      # llm.invoke() → await self._llm.ainvoke()
    ToolCallRule(),       # tool(arg) → tool.invoke(inputs={...})
    ToolMapCallRule(),    # tool_map[k].run() → tool_map[k].invoke()
    ReturnRule(),         # return {...} 处理
    PassthroughRule(),    # 兜底：保持原样但转换内部 state 访问
])
```

**规则匹配流程**：

```
源代码语句
    │
    ▼
┌─────────────┐  不匹配   ┌─────────────┐  不匹配   ┌─────────────┐
│ 规则1匹配?  │ ────────→ │ 规则2匹配?  │ ────────→ │ 规则N匹配?  │
└─────────────┘           └─────────────┘           └─────────────┘
    │ 匹配                     │ 匹配                     │ 匹配
    ▼                          ▼                          ▼
┌─────────────┐           ┌─────────────┐           ┌─────────────┐
│ 规则1转换   │           │ 规则2转换   │           │ 规则N转换   │
└─────────────┘           └─────────────┘           └─────────────┘
    │                          │                          │
    └──────────────────────────┴──────────────────────────┘
                               │
                               ▼
                        ConversionResult
```

### 1.3 AST 节点转换器

`StateToInputsTransformer` 使用 Python 的 `ast.NodeTransformer`：

```python
class StateToInputsTransformer(ast.NodeTransformer):
    """递归遍历并转换 AST 节点"""

    def visit_Subscript(self, node):   # state["x"] → inputs["x"]
    def visit_Call(self, node):        # state.get("x") → inputs.get("x")
    def visit_Assign(self, node):      # state["x"] = v → x = v
    def visit_Return(self, node):      # return state → return {...}
```

---

## 2. 实现内容

### 2.1 提取功能一览

| 提取项 | 方法 | 源码模式 | 提取结果 |
|--------|------|----------|----------|
| 状态类 | `_extract_states()` | `class AgentState(TypedDict)` | `StateField` 列表 |
| 节点函数 | `_extract_and_convert_nodes()` | `graph.add_node("name", func)` | `ConvertedNode` 列表 |
| 边连接 | `_extract_edges()` | `graph.add_edge()` / `add_conditional_edges()` | `EdgeInfo` 列表 |
| 工具 | `_extract_tools()` | `@tool` 装饰器 / `Tool()` 实例 | `ToolInfo` 列表 |
| LLM 配置 | `_extract_llm_configs()` | `ChatOpenAI(model=...)` | `LLMConfig` 列表 |
| 初始输入 | `_extract_initial_inputs()` | `app.invoke({...})` | `initial_inputs` 字典 |
| 全局变量 | `_extract_imports_and_globals()` | 顶层赋值语句 | `global_vars` 列表 |

### 2.2 代码转换规则

| 规则类 | LangGraph 代码 | openJiuwen 代码 |
|--------|---------------|-----------------|
| `StateAccessRule` | `state["key"]` | `inputs["key"]` |
| `StateAccessRule` | `state.get("key", 0)` | `inputs.get("key", 0)` |
| `StateAssignRule` | `state["key"] = value` | `key = value` |
| `LLMInvokeRule` | `llm.invoke(msgs)` | `await self._llm.ainvoke(model_name, msgs)` |
| `ToolCallRule` | `calculator(expr)` | `calculator.invoke(inputs={"expression": expr})` |
| `ToolMapCallRule` | `tool_map[k].run(arg)` | `tool_map[k].invoke(inputs={...})` |
| `ReturnRule` | `return state` | `return {"key1": val1, ...}` |
| `PassthroughRule` | 其他代码 | 保持原样（内部 state 访问会转换） |

---

## 3. 处理流程

```
┌────────────────────────────────────────────────────────────────────────┐
│                         RuleExtractorComp.invoke()                      │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  第一遍扫描：收集全局信息                                                │
│  ├─ 收集 add_node() 调用 → func_to_node 映射                            │
│  └─ 收集所有函数定义 → global_func_defs                                  │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  第二遍处理：按依赖顺序处理每个文件                                       │
│  ├─ 1. _extract_imports_and_globals() → imports, global_vars           │
│  ├─ 2. _extract_states()              → states (StateField)            │
│  ├─ 3. _extract_llm_configs()         → llm_configs                    │
│  ├─ 4. _extract_tools()               → tools (ToolInfo)               │
│  ├─ 5. _update_tool_names()           → 更新规则链中的工具名列表          │
│  ├─ 6. _extract_and_convert_nodes()   → nodes (ConvertedNode)          │
│  ├─ 7. _extract_edges()               → edges (EdgeInfo)               │
│  └─ 8. _extract_initial_inputs()      → initial_inputs, example_inputs │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  后处理：分类全局变量                                                    │
│  └─ _classify_global_vars() → tool_related_vars, tool_map_var_name     │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          ExtractionResult
```

---

## 4. 结果可视化

以 `example/langgraph/react_agent` 为例：

### 4.1 ExtractionResult 结构

```
ExtractionResult
│
├── states: List[StateField]
│   ├── StateField(name="input", type_hint="str")
│   ├── StateField(name="thought", type_hint="str")
│   ├── StateField(name="selected_tool", type_hint="Optional[str]")
│   ├── StateField(name="tool_input", type_hint="str")
│   ├── StateField(name="result", type_hint="str")
│   ├── StateField(name="is_end", type_hint="bool")
│   └── StateField(name="loop_count", type_hint="int")
│
├── nodes: List[ConvertedNode]
│   ├── ConvertedNode
│   │   ├── name: "think"
│   │   ├── original_code: "def think_node(state): ..."
│   │   ├── converted_body: "content = f'问题：{inputs[\"input\"]}'\n..."
│   │   ├── inputs: ["input", "loop_count"]
│   │   ├── outputs: ["thought", "selected_tool", "tool_input", "loop_count"]
│   │   └── conversion_source: "rule"
│   │
│   ├── ConvertedNode
│   │   ├── name: "select_tool"
│   │   └── ...
│   │
│   └── ConvertedNode
│       ├── name: "judge"
│       └── ...
│
├── edges: List[EdgeInfo]
│   ├── EdgeInfo(source="start", target="think")
│   ├── EdgeInfo(source="think", target="select_tool")
│   ├── EdgeInfo(source="select_tool", target="judge")
│   └── EdgeInfo(
│   │       source="judge",
│   │       is_conditional=True,
│   │       condition_func="judge_router",
│   │       condition_map={"end": "end", "think": "think"}
│   │   )
│
├── tools: List[ToolInfo]
│   ├── ToolInfo(name="calculator", params=[...])
│   └── ToolInfo(name="weather", params=[...])
│
├── llm_configs: List[LLMConfig]
│   └── LLMConfig(var_name="llm", model_name="glm-4-flash", ...)
│
├── initial_inputs: Dict[str, Any]
│   ├── "input": "${input_text}"
│   ├── "is_end": False
│   └── "loop_count": 0
│
├── example_inputs: Dict[str, Any]
│   └── "input": "100加200等于多少？"
│
├── tool_related_vars: List[str]
│   └── "tool_map = {'Calculator': calculator, 'Weather': weather}"
│
├── tool_map_var_name: str
│   └── "tool_map"
│
├── entry_point: str
│   └── "think"
│
├── rule_count: int → 3 (规则转换成功的节点数)
├── ai_count: int   → 0 (需要 AI 处理的节点数)
└── pending_items: List[PendingItem] → [] (待处理项)
```

### 4.2 节点转换示例

**原始代码 (LangGraph)**：
```python
def think_node(state: AgentState) -> dict:
    content = f"问题：{state['input']}"
    response = llm.invoke(messages).content
    loop_count = state.get("loop_count", 0) + 1
    return {
        "thought": thought,
        "loop_count": loop_count
    }
```

**转换后代码 (openJiuwen)**：
```python
content = f"问题：{inputs['input']}"
response = (await self._llm.ainvoke(model_name=self.model_name, messages=messages)).content
loop_count = inputs.get('loop_count', 0) + 1
thought = thought
loop_count = loop_count
```

**转换过程**：

```
┌─────────────────────────────────────┐
│ state["input"]                      │
│         │                           │
│         ▼ StateAccessRule           │
│ inputs["input"]                     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ llm.invoke(messages).content        │
│         │                           │
│         ▼ LLMInvokeRule             │
│ (await self._llm.ainvoke(...))      │
│         .content                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ state.get("loop_count", 0)          │
│         │                           │
│         ▼ StateAccessRule           │
│ inputs.get("loop_count", 0)         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ return {"thought": ..., ...}        │
│         │                           │
│         ▼ ReturnRule                │
│ thought = thought                   │
│ loop_count = loop_count             │
│ (outputs 收集到返回字典)              │
└─────────────────────────────────────┘
```

### 4.3 边转换示例

**原始代码 (LangGraph)**：
```python
graph.add_edge("think", "select_tool")
graph.add_conditional_edges("judge", judge_router, {"end": END, "think": "think"})
```

**提取结果**：
```
EdgeInfo(source="think", target="select_tool", is_conditional=False)

EdgeInfo(
    source="judge",
    target="",
    is_conditional=True,
    condition_func="judge_router",
    condition_func_code="def judge_router(state): ...",
    condition_map={"end": "end", "think": "think"}
)
```

---

## 5. 关键技术点

### 5.1 跨文件引用处理

```python
# 第一遍：收集所有文件的函数定义
global_func_defs: Dict[str, ast.FunctionDef] = {}
for file_path in dependency_order:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            global_func_defs[node.name] = node

# 第二遍：提取边时可以找到其他文件定义的路由函数
def _parse_conditional_edge(self, node, func_defs):
    condition_func = node.args[1].id  # 如 "judge_router"
    condition_func_code = ast.unparse(func_defs[condition_func])
```

### 5.2 工具名动态更新

```python
# 提取工具后，更新规则链中的工具名列表
tool_names = [t.name for t in result.tools]
self._update_tool_names(tool_names)

# ToolCallRule 使用工具名列表识别工具调用
class ToolCallRule:
    def set_tool_names(self, names):
        self._tool_names = names

    def matches(self, node):
        return func_name in self._tool_names
```

### 5.3 递归 AST 转换

```python
# 使用 ast.NodeTransformer 递归处理嵌套结构
class StateToInputsTransformer(ast.NodeTransformer):
    def visit_Subscript(self, node):
        # 先递归处理子节点
        self.generic_visit(node)
        # 再处理当前节点
        if self._is_state(node):
            node.value.id = "inputs"
        return node
```

---

## 6. 总结

| 原理 | 应用 |
|------|------|
| **访问者模式** | `ast.walk()` 遍历所有 AST 节点，分类提取 |
| **责任链模式** | `RuleChain` 按优先级尝试匹配规则 |
| **转换器模式** | `ast.NodeTransformer` 递归修改 AST |
| **两遍扫描** | 第一遍收集全局信息，第二遍处理转换 |
| **规则优先** | 规则能处理的用规则，失败的生成 `PendingItem` 给 AI |

RuleExtractorComp 是迁移工具的核心组件，将 LangGraph 代码结构化地提取并转换为 openJiuwen 可用的中间表示。
