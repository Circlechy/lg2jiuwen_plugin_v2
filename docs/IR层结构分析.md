# IR 层结构分析

## 1. 从 ExtractionResult 到 IR 的转换

### 1.1 整体流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ExtractionResult                                  │
│  (RuleExtractorComp 输出，包含原始提取信息和转换后的代码)                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          IRBuilderComp                                   │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ 1. _build_nodes_ir()     → List[WorkflowNodeIR]                 │    │
│  │ 2. _build_edges_ir()     → List[WorkflowEdgeIR]                 │    │
│  │ 3. _build_tools_ir()     → List[ToolIR]                         │    │
│  │ 4. _build_llm_config_ir() → LLMConfigIR                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            MigrationIR                                   │
│  ├── AgentIR      (Agent 配置：LLM、工具、全局变量等)                      │
│  ├── WorkflowIR   (工作流结构：节点、边、入口点)                           │
│  └── stats        (统计信息)                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CodeGeneratorComp                                │
│  (使用 IR 生成最终代码，只做模板填充，不需要 AI)                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 转换映射关系

| ExtractionResult 字段 | → | IR 结构 |
|----------------------|---|---------|
| `nodes: List[ConvertedNode]` | → | `WorkflowIR.nodes: List[WorkflowNodeIR]` |
| `edges: List[EdgeInfo]` | → | `WorkflowIR.edges: List[WorkflowEdgeIR]` |
| `tools: List[ToolInfo]` | → | `AgentIR.tools: List[ToolIR]` |
| `llm_configs: List[LLMConfig]` | → | `AgentIR.llm_config: LLMConfigIR` |
| `states: List[StateField]` | → | `AgentIR.state_fields` |
| `global_vars` | → | `AgentIR.global_vars` |
| `tool_related_vars` | → | `AgentIR.tool_related_vars` |
| `initial_inputs` | → | `AgentIR.initial_inputs` |
| `entry_point` | → | `WorkflowIR.entry_node` |

---

## 2. IR 层结构详解

### 2.1 IR 类层次结构

```
MigrationIR (迁移结果)
│
├── AgentIR (Agent 配置)
│   ├── name: str                    # Agent 名称
│   ├── llm_config: LLMConfigIR      # LLM 配置
│   │   ├── model_name: str
│   │   ├── temperature: float
│   │   └── other_params: Dict
│   ├── tools: List[ToolIR]          # 工具列表
│   │   ├── name: str
│   │   ├── func_name: str
│   │   ├── description: str
│   │   ├── parameters: List[Dict]
│   │   └── converted_body: str
│   ├── state_fields: List[Dict]     # 状态字段
│   ├── global_vars: List[str]       # 全局变量
│   ├── tool_related_vars: List[str] # 工具相关变量
│   ├── tool_map_var_name: str       # 工具映射变量名
│   ├── initial_inputs: Dict         # 初始输入
│   └── example_inputs: Dict         # 示例输入
│
├── WorkflowIR (工作流结构)
│   ├── nodes: List[WorkflowNodeIR]  # 节点列表
│   │   ├── name: str                # 节点名
│   │   ├── class_name: str          # 类名
│   │   ├── converted_body: str      # 转换后代码
│   │   ├── inputs: List[str]        # 输入字段
│   │   ├── outputs: List[str]       # 输出字段
│   │   ├── has_llm: bool            # 是否使用 LLM
│   │   └── has_tools: bool          # 是否使用工具
│   ├── edges: List[WorkflowEdgeIR]  # 边列表
│   │   ├── source: str
│   │   ├── target: str
│   │   ├── is_conditional: bool
│   │   ├── condition_func: str      # 转换后的路由函数
│   │   ├── condition_map: Dict
│   │   └── router_name: str
│   ├── entry_node: str              # 入口节点
│   └── state_class_name: str        # 状态类名
│
└── conversion_stats: Dict           # 转换统计
    ├── rule_count: int
    ├── ai_count: int
    ├── total_nodes: int
    ├── total_edges: int
    └── total_tools: int
```

### 2.2 各 IR 类的职责

| IR 类 | 职责 | 用于生成 |
|-------|------|----------|
| `WorkflowNodeIR` | 存储节点转换结果 | 组件类文件 |
| `WorkflowEdgeIR` | 存储边和路由信息 | 工作流连接代码 |
| `ToolIR` | 存储工具转换结果 | 工具函数定义 |
| `LLMConfigIR` | 存储 LLM 配置 | LLM 初始化代码 |
| `AgentIR` | 汇总 Agent 所有配置 | 主文件、配置文件 |
| `WorkflowIR` | 汇总工作流结构 | workflow.py |
| `MigrationIR` | 完整迁移结果 | 整个输出目录 |

---

## 3. 转换细节

### 3.1 节点转换 (_build_nodes_ir)

**ConvertedNode → WorkflowNodeIR**

```python
def _build_nodes_ir(self, result: ExtractionResult) -> List[WorkflowNodeIR]:
    nodes_ir = []
    for node in result.nodes:
        nodes_ir.append(WorkflowNodeIR(
            name=node.name,                           # 保持原名
            class_name=self._to_class_name(node.name), # think → ThinkComp
            converted_body=node.converted_body,       # 已转换的代码
            inputs=node.inputs,                       # ["input", "loop_count"]
            outputs=node.outputs,                     # ["thought", "selected_tool"]
            conversion_source=node.conversion_source, # "rule" 或 "ai"
            has_llm=self._has_llm_call(code),        # 检测 LLM 调用
            has_tools=self._has_tool_call(code)      # 检测工具调用
        ))
    return nodes_ir
```

**类名转换规则**：

```
节点名           →  类名
────────────────────────────
think           →  ThinkComp
select_tool     →  SelectToolComp
judge           →  JudgeComp
call_weather    →  CallWeatherComp
```

### 3.2 边转换 (_build_edges_ir)

**EdgeInfo → WorkflowEdgeIR**

```python
def _build_edges_ir(self, result: ExtractionResult) -> List[WorkflowEdgeIR]:
    edges_ir = []
    for edge in result.edges:
        router_name = None
        condition_func_code = None

        if edge.is_conditional:
            # 生成路由函数名: {source}_router
            router_name = f"{edge.source}_router"
            # 转换路由函数代码
            condition_func_code = self._convert_condition_func(
                router_name, edge.source, result,
                edge.condition_func_code, source_outputs
            )

        edges_ir.append(WorkflowEdgeIR(
            source=edge.source,
            target=edge.target,
            is_conditional=edge.is_conditional,
            condition_func=condition_func_code,  # 已转换的完整函数代码
            condition_map=edge.condition_map,
            router_name=router_name
        ))
    return edges_ir
```

**路由函数转换规则**：

```python
# LangGraph 原始代码
def judge_router(state: AgentState) -> str:
    if state.get("is_end"):
        return END
    if state.get("loop_count") >= 3:
        return END
    return "think"

# 转换后 (openJiuwen)
def judge_router(runtime: WorkflowRuntime) -> str:
    """路由函数：根据 judge 的输出决定下一个节点"""
    if runtime.get_global_state("judge.is_end"):    # 上游组件输出 → 带前缀
        return "end"
    if runtime.get_global_state("loop_count") >= 3: # 全局状态 → 不带前缀
        return "end"
    return "think"
```

**状态访问转换逻辑**：

```
如果 key 在上游组件的 outputs 中:
    state.get("key") → runtime.get_global_state("{source_node}.{key}")

否则（全局状态）:
    state.get("key") → runtime.get_global_state("{key}")
```

### 3.3 工具转换 (_build_tools_ir)

**ToolInfo → ToolIR**

```python
def _build_tools_ir(self, result: ExtractionResult) -> List[ToolIR]:
    tools_ir = []
    for tool in result.tools:
        # 提取函数体（去掉装饰器和 def 行）
        converted_body = self._convert_tool_body(tool.original_code)

        tools_ir.append(ToolIR(
            name=tool.name,
            func_name=tool.name,
            description=tool.description or f"{tool.name} 工具",
            parameters=tool.parameters,
            converted_body=converted_body
        ))
    return tools_ir
```

---

## 4. 示例：React Agent 的 IR 结构

以 `example/langgraph/react_agent` 为例：

### 4.1 MigrationIR 完整结构（对应 agent_ir.json）

```json
{
  "agent": {
    "name": "Agent",
    "llm_config": {
      "model_name": "gpt-4",
      "temperature": 0.7,
      "other_params": {
        "api_key": "a2143076...",
        "api_base": "https://open.bigmodel.cn/api/paas/v4/"
      }
    },
    "tools": [
      {
        "name": "calculator",
        "func_name": "calculator",
        "description": "用于数学加减乘除计算",
        "parameters": [{"name": "expression", "type": "str"}],
        "converted_body": "return str(eval(expression))"
      },
      {
        "name": "weather",
        "func_name": "weather",
        "description": "按城市+自然语言日期查天气",
        "parameters": [{"name": "params", "type": "str"}],
        "converted_body": "..."
      }
    ],
    "state_fields": [
      {"name": "input", "type": "str", "default": null},
      {"name": "thought", "type": "str", "default": null},
      {"name": "selected_tool", "type": "Optional[str]", "default": null},
      {"name": "tool_input", "type": "str", "default": null},
      {"name": "result", "type": "str", "default": null},
      {"name": "is_end", "type": "bool", "default": null},
      {"name": "loop_count", "type": "int", "default": null}
    ],
    "global_vars": ["MAX_LOOPS = 3"],
    "tool_related_vars": ["tool_map = {'Calculator': calculator, 'Weather': weather}"],
    "tool_map_var_name": "tool_map",
    "initial_inputs": {
      "input": "${input_text}",
      "is_end": false,
      "loop_count": 0
    },
    "example_inputs": {
      "input": "100加200等于多少？"
    },
    "entry_node": "think",
    "state_class_name": "AgentState",
    "nodes": [
      {
        "name": "think",
        "class_name": "ThinkComp",
        "inputs": ["input", "loop_count"],
        "outputs": ["thought", "selected_tool", "tool_input", "loop_count"],
        "conversion_source": "rule",
        "has_llm": true,
        "has_tools": false,
        "docstring": "思考节点：分析问题并选择合适的工具",
        "converted_body": "content = f'问题：{inputs[\"input\"]}'\\n..."
      },
      {
        "name": "select_tool",
        "class_name": "SelectToolComp",
        "inputs": ["selected_tool", "tool_input"],
        "outputs": ["result"],
        "conversion_source": "rule",
        "has_llm": false,
        "has_tools": true,
        "docstring": "工具执行节点",
        "converted_body": "result = invoke_tool(inputs['selected_tool'], ...)\\n..."
      },
      {
        "name": "judge",
        "class_name": "JudgeComp",
        "inputs": ["input", "result", "selected_tool"],
        "outputs": ["is_end", "reason"],
        "conversion_source": "rule",
        "has_llm": true,
        "has_tools": false,
        "docstring": "终止判断节点",
        "converted_body": "is_end = 'YES' in response.upper()\\n..."
      }
    ],
    "edges": [
      {
        "source": "think",
        "target": "select_tool",
        "is_conditional": false,
        "condition_func": null,
        "condition_map": null,
        "router_name": null
      },
      {
        "source": "select_tool",
        "target": "judge",
        "is_conditional": false,
        "condition_func": null,
        "condition_map": null,
        "router_name": null
      },
      {
        "source": "judge",
        "target": "",
        "is_conditional": true,
        "condition_func": "def judge_router(runtime: WorkflowRuntime) -> str:\\n    if runtime.get_global_state(\"judge.is_end\"):\\n        return \"end\"\\n    ...",
        "condition_map": {"end": "end", "think": "think"},
        "router_name": "judge_router"
      }
    ]
  },

  "stats": {
    "rule_count": 3,
    "ai_count": 0,
    "total_nodes": 3,
    "total_edges": 3,
    "total_tools": 2
  }
}
```

### 4.2 IR 到代码生成的映射

```
IR 结构                              →  生成的文件/代码
────────────────────────────────────────────────────────────────────
AgentIR.tools                        →  工具函数定义 (@tool 装饰器)
AgentIR.tool_related_vars            →  tool_map 变量定义
AgentIR.llm_config                   →  LLM 初始化代码
AgentIR.global_vars                  →  全局常量定义
AgentIR.initial_inputs               →  inputs_schema 和示例输入
│
WorkflowIR.nodes                     →  components/*.py (组件类文件)
  └─ WorkflowNodeIR.class_name       →    class ThinkComp(...)
  └─ WorkflowNodeIR.converted_body   →    async def invoke(...): ...
  └─ WorkflowNodeIR.inputs           →    inputs_schema 依赖
  └─ WorkflowNodeIR.outputs          →    return {...}
│
WorkflowIR.edges                     →  workflow.py 连接代码
  └─ 普通边                           →    add_connection("a", "b")
  └─ 条件边.condition_func           →    routers.py 路由函数
  └─ 条件边.router_name              →    add_conditional_connection("x", x_router)
│
WorkflowIR.entry_node                →  set_start_comp + add_connection
```

---

## 5. IR 设计原则

### 5.1 职责分离

```
┌─────────────────────────────────────────────────────────────────┐
│  RuleExtractorComp                                              │
│  职责：提取 + 转换                                               │
│  输出：ExtractionResult (包含原始信息 + 转换后代码)              │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  IRBuilderComp                                                  │
│  职责：结构化 + 增强                                             │
│  - 生成类名 (think → ThinkComp)                                 │
│  - 转换路由函数 (state → runtime)                               │
│  - 检测 LLM/工具依赖                                            │
│  输出：MigrationIR (结构化的代码生成输入)                        │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  CodeGeneratorComp                                              │
│  职责：模板填充                                                  │
│  - 只做字符串拼接，不需要 AI                                     │
│  - 根据 IR 字段决定生成逻辑                                      │
│  输出：生成的代码文件                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 IR 的优势

| 特性 | 说明 |
|------|------|
| **解耦** | 提取、转换、生成三阶段分离 |
| **可测试** | IR 是纯数据结构，易于单元测试 |
| **可扩展** | 新增输出格式只需新增 Generator |
| **可调试** | IR 可序列化为 JSON 便于检查 |
| **无 AI 依赖** | IR 到代码生成完全确定性 |

### 5.3 数据流完整性

```python
# IR 保证了数据流的完整性
class WorkflowNodeIR:
    inputs: List[str]   # 节点需要的输入字段
    outputs: List[str]  # 节点产生的输出字段

# CodeGenerator 可以据此生成 inputs_schema
inputs_schema = {
    field: f"${{{source_node}.{field}}}"
    for field in node_ir.inputs
}
```

---

## 6. 总结

| 层级 | 数据结构 | 职责 |
|------|----------|------|
| **提取层** | ExtractionResult | 原始提取 + 代码转换 |
| **IR 层** | MigrationIR | 结构化 + 增强 + 路由转换 |
| **生成层** | 代码文件 | 模板填充 |

IR 层是迁移工具的核心中间层，它将"提取转换"与"代码生成"解耦，使整个流程可测试、可扩展、无 AI 依赖。
