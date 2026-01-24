# LG2Jiuwen 迁移工具 - Agent 工作流架构设计 V3

> 基于 openJiuwen 框架最新 API 实现，采用"规则优先，AI 兜底"模式
>
> **V3 更新说明**：
> - 更新为最新 openJiuwen API（基于 agent-core 开发指南）
> - 明确 `inputs_schema` 与 `inputs_transformer` 的使用场景
> - 添加 `WorkflowConfig` 配置支持
> - 更新组件签名为标准 `Input`/`Output` 类型
> - 补充完整的组件设计和转换规则

---

## 1. 核心设计原则

### 1.1 规则优先，AI 兜底

```
规则能处理 → 规则处理（快速、确定、低成本）
规则无法处理 → AI 处理（语义理解、灵活）
```

### 1.2 转换前置

**所有代码转换在 IR 构建之前完成**，CodeGenerator 只做模板填充：

```
┌─────────────────────────────────────────────────────────────────┐
│                        转换前置策略                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  源代码 ──▶ AST ──▶ RuleExtractor ──▶ AISemantic ──▶ IR         │
│                     (转换函数体)      (转换剩余)    (已转换代码)  │
│                          │               │              │        │
│                          │               │              ▼        │
│                          │               │        CodeGenerator  │
│                          │               │        (模板填充)     │
│                          │               │         不需要AI      │
│                          ▼               ▼              │        │
│                    ┌─────────────────────────┐          │        │
│                    │  需要"理解"的阶段       │          │        │
│                    │  （可能用到AI）         │          │        │
│                    └─────────────────────────┘          │        │
│                                                         ▼        │
│                                                    输出代码      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 多文件支持

自动检测单文件/多文件项目，按依赖顺序处理。

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      迁移工作流架构                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  输入: source_path (文件或目录)                                       │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │ ProjectDetector │ 检测项目类型（单文件/多文件）                     │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │  FileLoader     │ 加载文件，分析依赖关系                           │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │   ASTParser     │ 解析所有文件的 AST                               │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐     ┌─────────────────┐                        │
│  │ RuleExtractor   │────▶│  ExtractionResult│                        │
│  │ (提取+转换)     │     │  - extracted     │                        │
│  └─────────────────┘     │  - pending_items │                        │
│         │                └─────────────────┘                        │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │  PendingCheck   │ pending_items 是否为空？                        │
│  └─────────────────┘                                                 │
│         │                                                            │
│    ┌────┴────┐                                                       │
│    ▼         ▼                                                       │
│  有pending  无pending                                                │
│    │         │                                                       │
│    ▼         │                                                       │
│  ┌─────────────────┐                                                 │
│  │  AISemantic     │ 只处理 pending_items                            │
│  │  (转换剩余)     │                                                 │
│  └─────────────────┘                                                 │
│    │         │                                                       │
│    └────┬────┘                                                       │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │   IRBuilder     │ 构建 IR（此时所有代码已转换）                    │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │ CodeGenerator   │ 模板填充（不需要AI）                             │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────┐                                                 │
│  │    Report       │ 生成迁移报告                                    │
│  └─────────────────┘                                                 │
│         │                                                            │
│         ▼                                                            │
│  输出: openJiuwen 代码 + 报告                                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 状态定义

```python
from typing import TypedDict, Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class PendingType(Enum):
    """待处理项类型"""
    NODE_BODY = "node_body"              # 节点函数体转换
    CONDITIONAL = "conditional"          # 条件路由逻辑
    TOOL_BODY = "tool_body"              # 工具函数体
    COMPLEX_EXPR = "complex_expr"        # 复杂表达式


@dataclass
class PendingItem:
    """待 AI 处理的项"""
    id: str                              # 唯一标识
    pending_type: PendingType
    source_code: str                     # 原始代码
    context: Dict[str, Any]              # 上下文（状态字段、可用工具等）
    question: str                        # 给 AI 的具体问题
    location: str                        # 位置信息 (file:line)


@dataclass
class ConvertedNode:
    """已转换的节点"""
    name: str
    original_code: str                   # 原始代码
    converted_body: str                  # 已转换的函数体
    inputs: List[str]                    # 输入字段
    outputs: List[str]                   # 输出字段
    conversion_source: str               # "rule" 或 "ai"


@dataclass
class ExtractionResult:
    """提取结果"""
    # 已完成转换的内容
    states: List[Dict] = field(default_factory=list)
    nodes: List[ConvertedNode] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)
    tools: List[Dict] = field(default_factory=list)
    llm_configs: List[Dict] = field(default_factory=list)

    # 待处理项
    pending_items: List[PendingItem] = field(default_factory=list)

    # 统计
    rule_count: int = 0                  # 规则处理数量
    ai_count: int = 0                    # AI处理数量


class MigrationState(TypedDict):
    """
    工作流状态定义

    说明：在 openJiuwen 中，简单数据通过 inputs_schema 传递，
    复杂对象通过 inputs_transformer 传递。
    """
    # ========== 输入 ==========
    source_path: str                     # 源路径（文件或目录）
    output_dir: str                      # 输出目录

    # ========== 项目检测阶段 (detector) ==========
    is_multi_file: bool                  # 是否为多文件项目
    file_list: List[str]                 # 所有待处理的文件列表（复杂对象）
    dependency_order: List[str]          # 按依赖排序的文件列表（复杂对象）

    # ========== 文件加载阶段 (loader) ==========
    file_contents: Dict[str, str]        # file_path -> 文件内容（复杂对象）

    # ========== AST 解析阶段 (parser) ==========
    ast_map: Dict[str, Any]              # file_path -> AST 对象（复杂对象）

    # ========== 规则提取阶段 (extractor) ==========
    extraction_result: Optional[ExtractionResult]  # 复杂对象

    # ========== 待处理检查阶段 (checker) ==========
    has_pending: bool                    # 是否有待 AI 处理的项（简单布尔值）

    # ========== IR 构建阶段 (ir_builder) ==========
    agent_ir: Optional[Dict]             # Agent IR 结构（复杂对象）
    workflow_ir: Optional[Dict]          # Workflow IR 结构（复杂对象）

    # ========== 代码生成阶段 (generator) ==========
    generated_code: str                  # 生成的代码内容
    generated_files: List[str]           # 生成的文件路径列表

    # ========== 报告生成阶段 (reporter) ==========
    report: str                          # 迁移报告内容
```

---

## 4. schema 与 transformer 使用规范（V3 重点）

openJiuwen 组件支持 **输入** 和 **输出** 两端的数据格式配置：

### 4.1 完整配置选项

| 配置项 | 方向 | 类型 | 适用场景 |
|--------|------|------|----------|
| `inputs_schema` | 输入 | 简单 | 引用上游组件的简单数据 |
| `inputs_transformer` | 输入 | 复杂 | 复杂数据处理、校验、逻辑判断 |
| `outputs_schema` | 输出 | 简单 | 格式化组件输出的字段名 |
| `outputs_transformer` | 输出 | 复杂 | 输出数据转换、字段提取、结果过滤 |
| `stream_inputs_schema` | 流式输入 | 简单 | 流式连接的输入 |
| `stream_outputs_schema` | 流式输出 | 简单 | 流式连接的输出 |

### 4.2 使用原则

**输入端（Input）**：

| 场景 | 使用方式 | 说明 |
|------|----------|------|
| 简单字符串/数字/布尔值 | `inputs_schema` | 数据结构简单、明确 |
| 复杂对象（Dict/List/dataclass/AST） | `inputs_transformer` | 需要传递复杂数据结构 |
| 需要数据校验 | `inputs_transformer` | 在传递前进行校验 |
| 需要字段拼接/重组 | `inputs_transformer` | 如合并多个字段 |
| 需要逻辑判断 | `inputs_transformer` | 如条件选择数据源 |

**输出端（Output）**：

| 场景 | 使用方式 | 说明 |
|------|----------|------|
| 重命名输出字段 | `outputs_schema` | 如 `{"result": "${value}"}` |
| 选择性输出部分字段 | `outputs_schema` | 只暴露需要的字段给下游 |
| 输出数据转换 | `outputs_transformer` | 类型转换、格式化 |
| 输出字段提取 | `outputs_transformer` | 从复杂对象中提取字段 |
| 输出结果过滤 | `outputs_transformer` | 条件过滤、默认值处理 |
| 输出结构重组 | `outputs_transformer` | 重新组织输出结构 |

### 4.3 使用示例

```python
from openjiuwen.core.runtime.state import ReadableStateLike

# ==================== 输入端示例 ====================

# ========== 简单数据：使用 inputs_schema ==========

# 传递简单字符串
inputs_schema={"source_path": "${start.source_path}"}

# 传递简单布尔值
inputs_schema={"verbose": "${start.verbose}"}


# ========== 复杂对象：使用 inputs_transformer ==========

def loader_inputs_transformer(state: ReadableStateLike):
    """传递 List 类型的复杂对象"""
    return {
        "file_list": state.get("detector.file_list"),           # List[str]
        "dependency_order": state.get("detector.dependency_order")  # List[str]
    }


def parser_inputs_transformer(state: ReadableStateLike):
    """传递 Dict 类型的复杂对象"""
    return {
        "file_contents": state.get("loader.file_contents"),     # Dict[str, str]
        "dependency_order": state.get("loader.dependency_order")
    }


def extractor_inputs_transformer(state: ReadableStateLike):
    """传递 AST 等复杂对象"""
    return {
        "ast_map": state.get("parser.ast_map"),                 # Dict[str, AST]
        "dependency_order": state.get("parser.dependency_order")
    }


# ========== 需要逻辑判断：使用 inputs_transformer ==========

def ir_builder_inputs_transformer(state: ReadableStateLike):
    """根据条件选择数据源"""
    # 优先从 AI 组件获取，否则从 checker 获取
    result = state.get("ai.extraction_result")
    if result is None:
        result = state.get("checker.extraction_result")
    return {"extraction_result": result}


# ========== 需要字段拼接：使用 inputs_transformer ==========

def report_inputs_transformer(state: ReadableStateLike):
    """合并多个来源的数据"""
    return {
        "extraction_result": state.get("extractor.extraction_result"),
        "generated_files": state.get("generator.generated_files"),
        "rule_count": state.get("extractor.extraction_result").rule_count,
        "ai_count": state.get("extractor.extraction_result").ai_count
    }


# ==================== 输出端示例 ====================

# ========== 重命名输出字段：使用 outputs_schema ==========

# 组件返回 {"value": "hello"}, 重命名为 invoke_output
outputs_schema={"invoke_output": "${value}"}

# 组件返回 {"code": "...", "files": [...]}, 只暴露部分字段
outputs_schema={
    "generated_code": "${code}",
    "file_list": "${files}"
}


# ========== 输出数据转换/过滤：使用 outputs_transformer ==========

def checker_outputs_transformer(results: dict):
    """
    PendingCheck 输出转换器
    - 将复杂的 extraction_result 简化为布尔值 has_pending
    - 同时保留原始 extraction_result 供下游使用
    """
    extraction_result = results.get("extraction_result")
    has_pending = len(extraction_result.pending_items) > 0 if extraction_result else False
    return {
        "has_pending": has_pending,
        "extraction_result": extraction_result
    }


def llm_outputs_transformer(results: dict):
    """
    LLM 输出转换器
    - 若输出为空，设置默认值
    """
    response = results.get("response")
    if response is None or response == "":
        return {"response": "无响应内容"}
    return {"response": response}


def generator_outputs_transformer(results: dict):
    """
    CodeGenerator 输出转换器
    - 提取文件数量统计
    - 格式化输出
    """
    files = results.get("generated_files", [])
    return {
        "generated_files": files,
        "file_count": len(files),
        "success": len(files) > 0
    }


# ========== 组件注册时同时配置输入和输出 ==========

workflow.add_workflow_comp(
    "checker",
    PendingCheckComp(),
    inputs_transformer=checker_inputs_transformer,      # 输入：复杂对象
    outputs_transformer=checker_outputs_transformer     # 输出：添加 has_pending 字段
)

workflow.add_workflow_comp(
    "generator",
    CodeGeneratorComp(),
    inputs_transformer=generator_inputs_transformer,
    outputs_schema={                                    # 输出：简单重命名
        "code": "${generated_code}",
        "files": "${generated_files}"
    }
)
```

---

## 5. 组件详细设计

### 5.1 组件基类规范

根据最新 openJiuwen API，所有自定义组件必须：

1. 继承 `WorkflowComponent` 和 `ComponentExecutable`
2. 实现 `async invoke(self, inputs: Input, runtime: Runtime, context: Context) -> Output` 方法

```python
from openjiuwen.core.component.base import WorkflowComponent
from openjiuwen.core.runtime.base import ComponentExecutable, Input, Output
from openjiuwen.core.runtime.runtime import Runtime
from openjiuwen.core.context_engine.base import Context


class MyComponent(WorkflowComponent, ComponentExecutable):
    """自定义组件模板"""

    def __init__(self):
        super().__init__()

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        # 从 inputs 获取数据
        data = inputs.get("field_name")

        # 处理逻辑
        result = self._process(data)

        # 返回输出字典
        return {"output_field": result}
```

### 5.2 ProjectDetectorComp - 项目检测

```python
class ProjectDetectorComp(WorkflowComponent, ComponentExecutable):
    """
    检测项目类型

    规则：
    - 输入是 .py 文件 → 单文件模式
    - 输入是目录 → 多文件模式，扫描所有 .py 文件
    - 分析 import 语句确定依赖关系
    """

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        source_path = inputs.get("source_path")

        if source_path.endswith(".py"):
            # 单文件模式
            return {
                "is_multi_file": False,
                "file_list": [source_path],
                "dependency_order": [source_path]
            }

        # 多文件模式
        files = self._scan_python_files(source_path)
        deps = self._analyze_dependencies(files)
        order = self._topological_sort(deps)

        return {
            "is_multi_file": True,
            "file_list": files,
            "dependency_order": order
        }

    def _scan_python_files(self, directory: str) -> List[str]:
        """扫描目录下所有 Python 文件"""
        import glob
        return glob.glob(f"{directory}/**/*.py", recursive=True)

    def _analyze_dependencies(self, files: List[str]) -> Dict[str, List[str]]:
        """分析文件间依赖"""
        import ast

        deps = {}
        file_modules = {self._file_to_module(f): f for f in files}

        for file_path in files:
            deps[file_path] = []
            with open(file_path) as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = self._get_import_module(node)
                    if module in file_modules:
                        deps[file_path].append(file_modules[module])

        return deps

    def _topological_sort(self, deps: Dict[str, List[str]]) -> List[str]:
        """拓扑排序"""
        from collections import deque

        in_degree = {f: 0 for f in deps}
        for f, dependencies in deps.items():
            for dep in dependencies:
                if dep in in_degree:
                    in_degree[f] += 1

        queue = deque([f for f, d in in_degree.items() if d == 0])
        result = []

        while queue:
            f = queue.popleft()
            result.append(f)
            for other, dependencies in deps.items():
                if f in dependencies:
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        return result
```

### 5.3 RuleExtractorComp - 规则提取器（核心）

```python
class RuleExtractorComp(WorkflowComponent, ComponentExecutable):
    """
    规则提取器 - 核心组件

    职责：
    1. 提取 LangGraph 结构（状态、节点、边、工具）
    2. 尝试用规则转换函数体
    3. 无法处理的生成 pending_item
    """

    def __init__(self):
        super().__init__()
        # 注册转换规则
        self.body_rules = [
            StateAccessRule(),      # state["x"] → inputs["x"]
            StateAssignRule(),      # state["x"] = v → outputs
            LLMInvokeRule(),        # llm.invoke() → await self._llm.ainvoke()
            ToolCallRule(),         # tool.invoke() → tool()
            SimpleReturnRule(),     # return state → return outputs
            EndReturnRule(),        # return END → return "end"
        ]

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        ast_map = inputs.get("ast_map")
        dependency_order = inputs.get("dependency_order")

        result = ExtractionResult()

        # 按依赖顺序处理文件
        for file_path in dependency_order:
            tree = ast_map[file_path]

            # 1. 提取状态（通常规则可完全处理）
            self._extract_states(tree, result)

            # 2. 提取并转换节点
            self._extract_and_convert_nodes(tree, result, file_path)

            # 3. 提取边
            self._extract_edges(tree, result)

            # 4. 提取并转换工具
            self._extract_and_convert_tools(tree, result, file_path)

            # 5. 提取 LLM 配置
            self._extract_llm_configs(tree, result)

        return {"extraction_result": result}

    def _extract_and_convert_nodes(self, tree, result: ExtractionResult, file_path: str):
        """提取并转换节点函数"""
        import ast

        # 找出所有被 add_node 引用的函数
        node_names = self._find_node_references(tree)

        for func in self._find_functions(tree):
            if func.name not in node_names:
                continue

            # 尝试规则转换
            conversion = self._try_convert_body(func, result)

            if conversion.success:
                # 规则转换成功
                result.nodes.append(ConvertedNode(
                    name=func.name,
                    original_code=ast.unparse(func),
                    converted_body=conversion.code,
                    inputs=conversion.inputs,
                    outputs=conversion.outputs,
                    conversion_source="rule"
                ))
                result.rule_count += 1
            else:
                # 生成 pending_item，等待 AI 处理
                result.pending_items.append(PendingItem(
                    id=f"{file_path}:{func.name}",
                    pending_type=PendingType.NODE_BODY,
                    source_code=ast.unparse(func),
                    context={
                        "state_fields": [s["name"] for s in result.states],
                        "available_tools": [t["name"] for t in result.tools],
                        "failed_lines": conversion.failed_lines
                    },
                    question=self._build_question(func, conversion.failed_lines),
                    location=f"{file_path}:{func.lineno}"
                ))

    def _try_convert_body(self, func, result: ExtractionResult) -> ConversionResult:
        """尝试用规则转换函数体"""
        import ast

        converted_lines = []
        failed_lines = []
        inputs = set()
        outputs = set()

        for stmt in func.body:
            # 跳过 docstring
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue

            # 尝试每个规则
            matched = False
            for rule in self.body_rules:
                if rule.matches(stmt):
                    conv = rule.convert(stmt)
                    converted_lines.append(conv.code)
                    inputs.update(conv.inputs)
                    outputs.update(conv.outputs)
                    matched = True
                    break

            if not matched:
                failed_lines.append({
                    "line": stmt.lineno,
                    "code": ast.unparse(stmt)
                })

        if failed_lines:
            return ConversionResult(success=False, failed_lines=failed_lines)

        return ConversionResult(
            success=True,
            code="\n        ".join(converted_lines),
            inputs=list(inputs),
            outputs=list(outputs)
        )

    def _build_question(self, func, failed_lines) -> str:
        """为 AI 构建具体问题"""
        lines_desc = "\n".join([
            f"- 第{l['line']}行: `{l['code']}`"
            for l in failed_lines
        ])

        return f"""
函数 `{func.name}` 中以下代码无法用规则转换，请转换为 openJiuwen 格式：

{lines_desc}

转换要求：
1. 状态读取: state["x"] → inputs.get("x")
2. 状态写入: 收集到返回字典
3. LLM调用: llm.invoke(msgs) → await self._llm.ainvoke(model_name, msgs)
4. 保持原有逻辑不变

请只输出转换后的代码行。
"""
```

### 5.4 转换规则示例

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List
import ast


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool = True
    code: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    failed_lines: List[dict] = field(default_factory=list)


class BaseRule(ABC):
    """规则基类"""

    @abstractmethod
    def matches(self, node: ast.AST) -> bool:
        """判断是否匹配此规则"""
        pass

    @abstractmethod
    def convert(self, node: ast.AST) -> ConversionResult:
        """执行转换"""
        pass


class StateAccessRule(BaseRule):
    """状态访问规则: state["x"] → inputs.get("x")"""

    def matches(self, node: ast.AST) -> bool:
        # 匹配 state["key"] 或 state.get("key")
        if isinstance(node, ast.Subscript):
            return self._is_state_var(node.value)
        if isinstance(node, ast.Call):
            return (isinstance(node.func, ast.Attribute) and
                    node.func.attr == "get" and
                    self._is_state_var(node.func.value))
        return False

    def _is_state_var(self, node) -> bool:
        if isinstance(node, ast.Name):
            return node.id in ("state", "State")
        return False

    def convert(self, node) -> ConversionResult:
        key = self._extract_key(node)
        code = f'inputs.get("{key}")'
        return ConversionResult(success=True, code=code, inputs=[key])

    def _extract_key(self, node) -> str:
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant):
                return node.slice.value
        return "unknown"


class LLMInvokeRule(BaseRule):
    """LLM 调用规则: llm.invoke(msgs) → await self._llm.ainvoke(...)"""

    KNOWN_LLM_VARS = {"llm", "model", "chat", "chat_model"}

    def matches(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Assign):
            node = node.value
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                var_name = self._get_var_name(node.func.value)
                method = node.func.attr
                return var_name in self.KNOWN_LLM_VARS and method in ("invoke", "ainvoke")
        return False

    def _get_var_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        return ""

    def convert(self, node: ast.AST) -> ConversionResult:
        target = None
        call = node

        if isinstance(node, ast.Assign):
            target = ast.unparse(node.targets[0])
            call = node.value

        # 提取 messages 参数
        messages_arg = ast.unparse(call.args[0]) if call.args else "messages"

        code = f'await self._llm.ainvoke(model_name=self.model_name, messages={messages_arg})'
        if target:
            code = f'{target} = {code}'

        return ConversionResult(success=True, code=code)


class StateAssignRule(BaseRule):
    """状态赋值规则: state["x"] = v → 收集输出"""

    def matches(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Assign):
            target = node.targets[0]
            if isinstance(target, ast.Subscript):
                if isinstance(target.value, ast.Name):
                    return target.value.id in ("state", "State")
        return False

    def convert(self, node: ast.Assign) -> ConversionResult:
        target = node.targets[0]
        key = target.slice.value if isinstance(target.slice, ast.Constant) else "unknown"
        value = ast.unparse(node.value)

        code = f'{key} = {value}'
        return ConversionResult(success=True, code=code, outputs=[key])


class EndReturnRule(BaseRule):
    """END 返回规则: return END → return "end" """

    def matches(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Return):
            if isinstance(node.value, ast.Name):
                return node.value.id == "END"
        return False

    def convert(self, node: ast.Return) -> ConversionResult:
        return ConversionResult(success=True, code='return "end"')
```

### 5.5 AISemanticComp - AI 语义理解

```python
from openjiuwen.core.utils.llm.model_library.openai import OpenAIChatModel


class AISemanticComp(WorkflowComponent, ComponentExecutable):
    """
    AI 语义理解组件

    职责：
    1. 只处理 pending_items（规则无法处理的部分）
    2. 为每个 pending_item 调用 AI
    3. 将结果合并回 extraction_result
    """

    def __init__(self, llm=None):
        super().__init__()
        self._llm = llm

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        extraction_result: ExtractionResult = inputs.get("extraction_result")
        pending_items = extraction_result.pending_items

        if not pending_items:
            return {"extraction_result": extraction_result}

        # 处理每个 pending_item
        for item in pending_items:
            converted = await self._convert_with_ai(item)

            # 将转换结果添加到 nodes
            extraction_result.nodes.append(ConvertedNode(
                name=self._extract_name(item.id),
                original_code=item.source_code,
                converted_body=converted.code,
                inputs=converted.inputs,
                outputs=converted.outputs,
                conversion_source="ai"
            ))
            extraction_result.ai_count += 1

        # 清空 pending_items
        extraction_result.pending_items = []

        return {"extraction_result": extraction_result}

    async def _convert_with_ai(self, item: PendingItem) -> ConversionResult:
        """调用 AI 转换代码"""
        if self._llm is None:
            return self._fallback_conversion(item)

        system_prompt = """你是代码转换专家，将 LangGraph 代码转换为 openJiuwen 格式。

openJiuwen 组件规范：
- 异步方法: async def invoke(self, inputs: Input, runtime: Runtime, context: Context) -> Output
- 输入访问: inputs.get("field_name")
- 输出返回: return {"field": value}
- LLM调用: await self._llm.ainvoke(model_name=self.model_name, messages=[...])

只输出转换后的代码，不要解释。"""

        user_prompt = f"""
## 上下文
- 状态字段: {item.context.get('state_fields', [])}
- 可用工具: {item.context.get('available_tools', [])}

## 原始代码
```python
{item.source_code}
```

## 问题
{item.question}
"""

        response = await self._llm.ainvoke(
            model_name="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        code = self._extract_code(response.content)
        inputs, outputs = self._analyze_io(code)

        return ConversionResult(
            success=True,
            code=code,
            inputs=inputs,
            outputs=outputs
        )

    def _fallback_conversion(self, item: PendingItem) -> ConversionResult:
        """无 LLM 时的降级处理"""
        return ConversionResult(
            success=True,
            code=f"# TODO: 需要手动转换\n# {item.source_code}",
            inputs=[],
            outputs=[]
        )

    def _extract_name(self, item_id: str) -> str:
        """从 item_id 提取函数名"""
        return item_id.split(":")[-1]
```

### 5.6 IRBuilderComp - IR 构建器

```python
@dataclass
class WorkflowNodeIR:
    """节点 IR"""
    name: str
    class_name: str
    converted_body: str
    inputs: List[str]
    outputs: List[str]
    conversion_source: str


@dataclass
class WorkflowEdgeIR:
    """边 IR"""
    source: str
    target: str
    is_conditional: bool = False
    condition_func: str = ""
    condition_map: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolIR:
    """工具 IR"""
    name: str
    description: str
    params: List[Dict]
    body: str


@dataclass
class AgentIR:
    """Agent IR"""
    name: str
    llm_config: Optional[Dict]
    tools: List[ToolIR]
    state_fields: List[Dict]


@dataclass
class WorkflowIR:
    """工作流 IR"""
    nodes: List[WorkflowNodeIR]
    edges: List[WorkflowEdgeIR]
    entry_node: str


class IRBuilderComp(WorkflowComponent, ComponentExecutable):
    """
    IR 构建器

    此时所有代码已经转换完成，只需组装 IR 结构
    不需要 AI
    """

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        result: ExtractionResult = inputs.get("extraction_result")

        # 构建节点 IR
        nodes_ir = []
        for node in result.nodes:
            nodes_ir.append(WorkflowNodeIR(
                name=node.name,
                class_name=self._to_class_name(node.name),
                converted_body=node.converted_body,
                inputs=node.inputs,
                outputs=node.outputs,
                conversion_source=node.conversion_source
            ))

        # 构建边 IR
        edges_ir = []
        for edge in result.edges:
            edges_ir.append(WorkflowEdgeIR(
                source=edge["source"],
                target=edge["target"],
                is_conditional=edge.get("is_conditional", False),
                condition_func=edge.get("condition_func", ""),
                condition_map=edge.get("condition_map", {})
            ))

        # 构建工具 IR
        tools_ir = [ToolIR(**t) for t in result.tools]

        # 构建 Agent IR
        agent_ir = AgentIR(
            name=self._infer_name(result),
            llm_config=result.llm_configs[0] if result.llm_configs else None,
            tools=tools_ir,
            state_fields=result.states
        )

        workflow_ir = WorkflowIR(
            nodes=nodes_ir,
            edges=edges_ir,
            entry_node=self._find_entry(result.edges)
        )

        return {
            "agent_ir": agent_ir,
            "workflow_ir": workflow_ir,
            "extraction_result": result  # 传递给报告组件
        }

    def _to_class_name(self, name: str) -> str:
        """转换为类名"""
        return "".join(word.capitalize() for word in name.split("_")) + "Component"

    def _infer_name(self, result: ExtractionResult) -> str:
        """推断 Agent 名称"""
        return "MigratedAgent"

    def _find_entry(self, edges: List[Dict]) -> str:
        """找到入口节点"""
        sources = {e["source"] for e in edges}
        targets = {e["target"] for e in edges}
        entries = sources - targets
        return list(entries)[0] if entries else "start"
```

### 5.7 CodeGeneratorComp - 代码生成器

```python
class CodeGeneratorComp(WorkflowComponent, ComponentExecutable):
    """
    代码生成器

    纯模板填充，不需要 AI
    IR 中已包含转换后的代码
    """

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        agent_ir = inputs.get("agent_ir")
        workflow_ir = inputs.get("workflow_ir")
        output_dir = inputs.get("output_dir")

        sections = []

        # 1. 导入语句
        sections.append(self._gen_imports(agent_ir))

        # 2. 工具函数
        for tool in agent_ir.tools:
            sections.append(self._gen_tool(tool))

        # 3. 组件类
        for node in workflow_ir.nodes:
            sections.append(self._gen_component(node))

        # 4. 路由函数
        for edge in workflow_ir.edges:
            if edge.is_conditional:
                sections.append(self._gen_router(edge))

        # 5. 工作流构建
        sections.append(self._gen_workflow(workflow_ir))

        # 6. 主函数
        sections.append(self._gen_main())

        code = "\n\n".join(sections)

        # 写入文件
        output_file = self._write_file(code, output_dir, agent_ir.name)

        return {
            "generated_code": code,
            "generated_files": [output_file]
        }

    def _gen_imports(self, agent_ir: AgentIR) -> str:
        """生成导入语句"""
        return '''"""
Migrated from LangGraph to openJiuwen
Auto-generated by lg2jiuwen tool
"""

import os
from typing import Dict, Any

from openjiuwen.core.workflow.base import Workflow
from openjiuwen.core.component.start_comp import Start
from openjiuwen.core.component.end_comp import End
from openjiuwen.core.component.base import WorkflowComponent
from openjiuwen.core.runtime.base import ComponentExecutable, Input, Output
from openjiuwen.core.runtime.runtime import Runtime
from openjiuwen.core.runtime.workflow import WorkflowRuntime
from openjiuwen.core.context_engine.base import Context
from openjiuwen.core.utils.llm.model_library.openai import OpenAIChatModel
from openjiuwen.core.utils.tool.param import Param
from openjiuwen.core.utils.tool.tool import tool
'''

    def _gen_component(self, node: WorkflowNodeIR) -> str:
        """生成组件类"""
        output_init = "\n".join(f"        {o} = None" for o in node.outputs)
        outputs_dict = ", ".join(f'"{o}": {o}' for o in node.outputs)

        return f'''class {node.class_name}(WorkflowComponent, ComponentExecutable):
    """{node.name} 组件"""

    def __init__(self, llm=None):
        super().__init__()
        self._llm = llm
        self.model_name = "default"

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        # 初始化输出
{output_init}

        # 组件逻辑（已转换）
        {node.converted_body}

        return {{{outputs_dict}}}
'''

    def _gen_router(self, edge: WorkflowEdgeIR) -> str:
        """生成路由函数"""
        return f'''def {edge.source}_router(runtime: Runtime) -> str:
    """{edge.source} 节点的路由函数"""
    {edge.condition_func}
'''

    def _gen_workflow(self, workflow_ir: WorkflowIR) -> str:
        """生成工作流构建函数"""
        # 生成组件注册代码
        comp_registrations = []
        for node in workflow_ir.nodes:
            comp_registrations.append(
                f'    flow.add_workflow_comp("{node.name}", {node.class_name}())'
            )

        # 生成连接代码
        connections = []
        for edge in workflow_ir.edges:
            if edge.is_conditional:
                connections.append(
                    f'    flow.add_conditional_connection("{edge.source}", router={edge.source}_router)'
                )
            else:
                connections.append(
                    f'    flow.add_connection("{edge.source}", "{edge.target}")'
                )

        return f'''def create_workflow() -> Workflow:
    """创建工作流"""
    flow = Workflow()

    # 设置起点
    flow.set_start_comp("start", Start())

    # 注册组件
{chr(10).join(comp_registrations)}

    # 设置终点
    flow.set_end_comp("end", End())

    # 添加连接
{chr(10).join(connections)}

    return flow
'''

    def _gen_main(self) -> str:
        """生成主函数"""
        return '''async def run_workflow(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """运行工作流"""
    flow = create_workflow()
    runtime = WorkflowRuntime()
    result = await flow.invoke(inputs, runtime)
    return result


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_workflow({"query": "test"}))
    print(result)
'''

    def _gen_tool(self, tool: ToolIR) -> str:
        """生成工具函数"""
        params_str = ", ".join(
            f'Param(name="{p["name"]}", description="{p["description"]}", type="{p["type"]}", required={p.get("required", True)})'
            for p in tool.params
        )
        return f'''@tool(
    name="{tool.name}",
    description="{tool.description}",
    params=[{params_str}]
)
def {tool.name}({", ".join(f'{p["name"]}: {p["type"]}' for p in tool.params)}) -> str:
    {tool.body}
'''

    def _write_file(self, code: str, output_dir: str, name: str) -> str:
        """写入文件"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{name.lower()}_openjiuwen.py")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(code)
        return output_file
```

---

## 6. 工作流定义

### 6.1 Transformer 定义（仅用于复杂对象）

```python
from openjiuwen.core.runtime.state import ReadableStateLike


def loader_inputs_transformer(state: ReadableStateLike):
    """FileLoader 输入转换器 - 传递 List 类型"""
    return {
        "file_list": state.get("detector.file_list"),
        "dependency_order": state.get("detector.dependency_order")
    }


def parser_inputs_transformer(state: ReadableStateLike):
    """ASTParser 输入转换器 - 传递 Dict 类型"""
    return {
        "file_contents": state.get("loader.file_contents"),
        "dependency_order": state.get("loader.dependency_order")
    }


def extractor_inputs_transformer(state: ReadableStateLike):
    """RuleExtractor 输入转换器 - 传递 AST 等复杂对象"""
    return {
        "ast_map": state.get("parser.ast_map"),
        "dependency_order": state.get("parser.dependency_order")
    }


def checker_inputs_transformer(state: ReadableStateLike):
    """PendingCheck 输入转换器 - 传递 dataclass"""
    return {
        "extraction_result": state.get("extractor.extraction_result")
    }


def checker_outputs_transformer(results: dict):
    """PendingCheck 输出转换器 - 添加 has_pending 布尔字段"""
    extraction_result = results.get("extraction_result")
    has_pending = len(extraction_result.pending_items) > 0 if extraction_result else False
    return {
        "has_pending": has_pending,
        "extraction_result": extraction_result
    }


def ai_inputs_transformer(state: ReadableStateLike):
    """AISemantic 输入转换器"""
    return {
        "extraction_result": state.get("checker.extraction_result")
    }


def ir_builder_inputs_transformer(state: ReadableStateLike):
    """IRBuilder 输入转换器 - 包含逻辑判断"""
    # 优先从 AI 组件获取，否则从 checker 获取
    result = state.get("ai.extraction_result")
    if result is None:
        result = state.get("checker.extraction_result")
    return {"extraction_result": result}


def generator_inputs_transformer(state: ReadableStateLike):
    """CodeGenerator 输入转换器 - 传递 IR 对象"""
    return {
        "agent_ir": state.get("ir_builder.agent_ir"),
        "workflow_ir": state.get("ir_builder.workflow_ir"),
        "output_dir": state.get("start.output_dir")
    }


def reporter_inputs_transformer(state: ReadableStateLike):
    """Report 输入转换器"""
    return {
        "extraction_result": state.get("ir_builder.extraction_result"),
        "generated_files": state.get("generator.generated_files")
    }
```

### 6.2 路由函数

```python
from openjiuwen.core.runtime.runtime import Runtime


def pending_router(runtime: Runtime) -> str:
    """路由函数：是否需要 AI 处理"""
    has_pending = runtime.get_global_state("checker.has_pending")
    return "ai" if has_pending else "ir_builder"
```

### 6.3 完整工作流构建

```python
from openjiuwen.core.workflow.base import Workflow
from openjiuwen.core.workflow.workflow_config import WorkflowConfig, WorkflowMetadata
from openjiuwen.core.component.start_comp import Start
from openjiuwen.core.component.end_comp import End


def build_migration_workflow(llm=None) -> Workflow:
    """构建迁移工作流"""

    # 创建工作流配置
    workflow_config = WorkflowConfig(
        metadata=WorkflowMetadata(
            name="lg2jiuwen_migration",
            id="lg2jiuwen_migration_workflow",
            version="3.0"
        )
    )

    workflow = Workflow(workflow_config=workflow_config)

    # ========== 起点（简单数据用 schema）==========
    start_config = {
        "inputs": [
            {"id": "source_path", "required": True},
            {"id": "output_dir", "default_value": "./output", "required": False}
        ]
    }
    workflow.set_start_comp(
        "start",
        Start(start_config),
        inputs_schema={
            "source_path": "${source_path}",
            "output_dir": "${output_dir}"
        }
    )

    # ========== 项目检测（简单字符串用 schema）==========
    workflow.add_workflow_comp(
        "detector",
        ProjectDetectorComp(),
        inputs_schema={"source_path": "${start.source_path}"}
    )

    # ========== 文件加载（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "loader",
        FileLoaderComp(),
        inputs_transformer=loader_inputs_transformer
    )

    # ========== AST 解析（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "parser",
        ASTParserComp(),
        inputs_transformer=parser_inputs_transformer
    )

    # ========== 规则提取（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "extractor",
        RuleExtractorComp(),
        inputs_transformer=extractor_inputs_transformer
    )

    # ========== 待处理检查（输入输出都用 transformer）==========
    workflow.add_workflow_comp(
        "checker",
        PendingCheckComp(),
        inputs_transformer=checker_inputs_transformer,
        outputs_transformer=checker_outputs_transformer  # 添加 has_pending 字段
    )

    # ========== AI 语义理解（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "ai",
        AISemanticComp(llm=llm),
        inputs_transformer=ai_inputs_transformer
    )

    # ========== IR 构建（有逻辑判断用 transformer）==========
    workflow.add_workflow_comp(
        "ir_builder",
        IRBuilderComp(),
        inputs_transformer=ir_builder_inputs_transformer
    )

    # ========== 代码生成（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "generator",
        CodeGeneratorComp(),
        inputs_transformer=generator_inputs_transformer
    )

    # ========== 报告生成（复杂对象用 transformer）==========
    workflow.add_workflow_comp(
        "reporter",
        ReportComp(),
        inputs_transformer=reporter_inputs_transformer
    )

    # ========== 终点（简单数据用 schema）==========
    end_config = {"responseTemplate": "{{report}}"}
    workflow.set_end_comp(
        "end",
        End(end_config),
        inputs_schema={
            "generated_files": "${reporter.generated_files}",
            "report": "${reporter.report}"
        }
    )

    # ========== 添加连接 ==========
    workflow.add_connection("start", "detector")
    workflow.add_connection("detector", "loader")
    workflow.add_connection("loader", "parser")
    workflow.add_connection("parser", "extractor")
    workflow.add_connection("extractor", "checker")

    # 条件路由
    workflow.add_conditional_connection("checker", router=pending_router)

    workflow.add_connection("ai", "ir_builder")
    workflow.add_connection("ir_builder", "generator")
    workflow.add_connection("generator", "reporter")
    workflow.add_connection("reporter", "end")

    return workflow
```

---

## 7. LangGraph 到 openJiuwen 转换映射

### 7.1 结构映射

| LangGraph | openJiuwen |
|-----------|------------|
| `StateGraph` | `Workflow` |
| `TypedDict` State | `inputs_schema` / `inputs_transformer` |
| Node Function | `WorkflowComponent` + `ComponentExecutable` |
| `add_edge()` | `add_connection()` |
| `add_conditional_edges()` | `add_conditional_connection()` + router |
| `@tool` | `@tool()` + `Param` |
| `END` | `"end"` |

### 7.2 代码转换映射

| LangGraph | openJiuwen |
|-----------|------------|
| `state["key"]` | `inputs.get("key")` |
| `state["key"] = val` | `return {"key": val}` |
| `state.get("key")` | `inputs.get("key")` |
| `llm.invoke(msgs)` | `await self._llm.ainvoke(model_name=MODEL_NAME, messages=msgs)` |
| `tool.invoke({...})` | `tool.invoke({...})` |
| `return state` | `return {"key1": val1, ...}` |
| `return END` | `return "end"` (在路由函数中) |

### 7.3 路由函数转换

```python
# LangGraph
def route_after_extract(state: AgentState) -> str:
    return END if state.get("error") else "call_weather"

# openJiuwen
def extract_router(runtime: Runtime) -> str:
    error = runtime.get_global_state("extract.error")
    return "end" if error else "call_weather"
```

---

## 8. 各阶段职责总结

| 阶段 | 组件 | 职责 | 需要AI | 输入配置 | 输出配置 |
|------|------|------|--------|----------|----------|
| 起点 | Start | 接收输入 | 否 | schema | - |
| 检测 | ProjectDetector | 检测单/多文件，分析依赖 | 否 | schema | - (直接输出List) |
| 加载 | FileLoader | 读取文件内容 | 否 | transformer | - |
| 解析 | ASTParser | 生成 AST | 否 | transformer | - |
| **提取+转换** | **RuleExtractor** | **规则提取结构 + 转换函数体** | **否** | transformer | - |
| 检查 | PendingCheck | 检查是否有待处理项 | 否 | transformer | **outputs_transformer** (添加has_pending) |
| **转换剩余** | **AISemantic** | **AI转换规则失败的部分** | **是** | transformer | - |
| 构建 | IRBuilder | 组装 IR 结构 | 否 | transformer(有逻辑) | - |
| 生成 | CodeGenerator | 模板填充生成代码 | **否** | transformer | - |
| 报告 | Report | 生成迁移报告 | 否 | transformer | - |
| 终点 | End | 输出结果 | 否 | schema | schema |

### 8.1 输入输出配置说明

- **inputs_schema**：引用上游组件输出，使用 `${component.field}` 语法
- **inputs_transformer**：函数式处理，接收 `ReadableStateLike`，返回输入字典
- **outputs_schema**：重命名/选择输出字段，使用 `${field}` 引用组件返回值
- **outputs_transformer**：函数式处理，接收组件返回的 `dict`，返回格式化后的输出

---

## 9. 执行示例

### 9.1 标准代码（规则完全处理）

```
输入: weather_agent.py

ProjectDetector → 单文件
FileLoader → 读取内容
ASTParser → 生成 AST
RuleExtractor →
    - 状态: AgentState ✓
    - 节点: parse_input_llm ✓ (规则转换成功)
    - 节点: call_weather ✓ (规则转换成功)
    - 边: ✓
    - pending_items: [] (空)
PendingCheck → has_pending=False
→ 跳过 AISemantic
IRBuilder → 构建 IR
CodeGenerator → 模板填充
Report → 生成报告

输出: weather_agent_openjiuwen.py
统计: 规则处理 100%, AI 处理 0%
```

### 9.2 复杂代码（需要 AI）

```
输入: complex_agent.py

ProjectDetector → 单文件
FileLoader → 读取内容
ASTParser → 生成 AST
RuleExtractor →
    - 状态: ComplexState ✓
    - 节点: simple_node ✓ (规则转换成功)
    - 节点: complex_node → pending (有复杂逻辑)
    - pending_items: [complex_node 的函数体]
PendingCheck → has_pending=True
AISemantic →
    - 处理 complex_node
    - AI 返回转换后的代码
    - 添加到 nodes
IRBuilder → 构建 IR (所有代码已转换)
CodeGenerator → 模板填充
Report → 生成报告

输出: complex_agent_openjiuwen.py
统计: 规则处理 80%, AI 处理 20%
```

### 9.3 多文件项目

```
输入: my_agent_project/

ProjectDetector →
    - 多文件模式
    - 文件: [tools.py, nodes.py, workflow.py]
    - 依赖顺序: [tools.py, nodes.py, workflow.py]
FileLoader → 读取所有文件
ASTParser → 为每个文件生成 AST
RuleExtractor → 按依赖顺序处理
    - tools.py: 提取工具 ✓
    - nodes.py: 提取节点，可引用 tools ✓
    - workflow.py: 提取边和入口 ✓
...后续同上

输出:
    - my_agent_project_openjiuwen/
        - tools.py
        - components.py
        - workflow.py
```

---

## 10. 文件结构

```
src/lg2jiuwen_tool/
├── workflow/
│   ├── __init__.py
│   ├── migration_workflow.py    # 主工作流定义
│   └── state.py                 # 状态和数据模型
├── components/
│   ├── __init__.py
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
│   ├── __init__.py
│   ├── base.py                  # 规则基类
│   ├── state_rules.py           # 状态相关规则
│   ├── llm_rules.py             # LLM 调用规则
│   ├── tool_rules.py            # 工具调用规则
│   └── edge_rules.py            # 边/路由规则
├── ir/
│   ├── __init__.py
│   └── models.py                # IR 数据模型
├── templates/
│   ├── imports.py.jinja
│   ├── component.py.jinja
│   ├── workflow.py.jinja
│   └── router.py.jinja
├── service.py
└── cli.py
```

---

## 11. 总结

### V3 设计要点

1. **schema vs transformer 分工明确**：
   - **输入端**：
     - 简单数据（字符串/数字/布尔值）用 `inputs_schema`
     - 复杂对象（Dict/List/AST/dataclass）用 `inputs_transformer`
     - 需要逻辑判断时用 `inputs_transformer`
   - **输出端**：
     - 重命名/选择字段用 `outputs_schema`
     - 数据转换/过滤/默认值处理用 `outputs_transformer`

2. **转换前置**：所有代码转换在 RuleExtractor + AISemantic 阶段完成

3. **规则优先**：最大化规则处理，减少 AI 调用

4. **精确提问**：AI 只回答具体问题，不重新分析整个函数

5. **IR 存储已转换代码**：CodeGenerator 只做模板填充

6. **多文件支持**：自动检测，按依赖顺序处理

### AI 使用边界

| 需要 AI | 不需要 AI |
|---------|-----------|
| 复杂函数体转换 | 结构提取（状态、边、工具签名）|
| 非标准 LLM 调用 | 标准模式匹配转换 |
| 复杂条件逻辑 | IR 构建 |
| 动态调用分析 | 代码生成（模板填充）|

### 预期效果

- 标准代码：90%+ 规则处理，接近零 AI 调用
- 复杂代码：规则处理基础部分，AI 只处理难点
- 成本降低：相比全 AI 方案减少 70%+ 调用
