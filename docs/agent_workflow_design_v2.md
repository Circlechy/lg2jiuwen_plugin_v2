# LG2Jiuwen 迁移工具 - Agent 工作流架构设计 V2

> 基于 openJiuwen 框架实现，采用"规则优先，AI 兜底"模式

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
    states: List[Dict]
    nodes: List[ConvertedNode]           # 已转换的节点
    edges: List[Dict]
    tools: List[Dict]
    llm_configs: List[Dict]

    # 待处理项
    pending_items: List[PendingItem]

    # 统计
    rule_count: int = 0                  # 规则处理数量
    ai_count: int = 0                    # AI处理数量


class MigrationState(TypedDict):
    """工作流状态"""
    # 输入
    source_path: str                     # 源路径（文件或目录）
    output_dir: str

    # 项目检测
    is_multi_file: bool
    file_list: List[str]
    dependency_order: List[str]          # 按依赖排序的文件列表

    # AST
    ast_map: Dict[str, Any]              # file -> AST

    # 提取结果
    extraction_result: Optional[ExtractionResult]

    # IR（所有代码已转换）
    agent_ir: Optional[Dict]
    workflow_ir: Optional[Dict]

    # 输出
    generated_code: str
    generated_files: List[str]
    report: str
```

---

## 4. 组件详细设计

### 4.1 ProjectDetectorComp - 项目检测

```python
class ProjectDetectorComp(WorkflowComponent, ComponentExecutable):
    """
    检测项目类型

    规则：
    - 输入是 .py 文件 → 单文件模式
    - 输入是目录 → 多文件模式，扫描所有 .py 文件
    - 分析 import 语句确定依赖关系
    """

    async def invoke(self, inputs, runtime, context):
        source_path = inputs["source_path"]

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

    def _analyze_dependencies(self, files: List[str]) -> Dict[str, List[str]]:
        """分析文件间依赖"""
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
```

### 4.2 RuleExtractorComp - 规则提取器（核心）

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
        # 注册转换规则
        self.body_rules = [
            StateAccessRule(),      # state["x"] → inputs["x"]
            StateAssignRule(),      # state["x"] = v → outputs
            LLMInvokeRule(),        # llm.invoke() → await self._llm.ainvoke()
            ToolCallRule(),         # tool.invoke() → tool()
            SimpleReturnRule(),     # return state → return outputs
            EndReturnRule(),        # return END → return "end"
        ]

    async def invoke(self, inputs, runtime, context):
        ast_map = inputs["ast_map"]
        dependency_order = inputs["dependency_order"]

        result = ExtractionResult(
            states=[], nodes=[], edges=[],
            tools=[], llm_configs=[], pending_items=[]
        )

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

    def _try_convert_body(self, func: ast.FunctionDef, result: ExtractionResult):
        """尝试用规则转换函数体"""

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
1. 状态读取: state["x"] → inputs["x"]
2. 状态写入: 收集到返回字典
3. LLM调用: llm.invoke(msgs) → await self._llm.ainvoke(model_name, msgs)
4. 保持原有逻辑不变

请只输出转换后的代码行。
"""
```

### 4.3 转换规则示例

```python
class StateAccessRule:
    """状态访问规则: state["x"] → inputs["x"]"""

    def matches(self, node: ast.AST) -> bool:
        # 匹配 state["key"] 或 state.get("key")
        if isinstance(node, ast.Subscript):
            return self._is_state_var(node.value)
        if isinstance(node, ast.Call):
            return (isinstance(node.func, ast.Attribute) and
                    node.func.attr == "get" and
                    self._is_state_var(node.func.value))
        return False

    def convert(self, node) -> ConversionResult:
        key = self._extract_key(node)
        code = f'inputs["{key}"]' if isinstance(node, ast.Subscript) else f'inputs.get("{key}")'
        return ConversionResult(code=code, inputs=[key], outputs=[])


class LLMInvokeRule:
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

    def convert(self, node: ast.Assign) -> ConversionResult:
        target = node.targets[0].id if isinstance(node, ast.Assign) else None
        call = node.value if isinstance(node, ast.Assign) else node

        # 提取 messages 参数
        messages_arg = ast.unparse(call.args[0]) if call.args else "messages"

        code = f'await self._llm.ainvoke(model_name=self.model_name, messages={messages_arg})'
        if target:
            code = f'{target} = {code}'

        return ConversionResult(code=code, inputs=[], outputs=[])
```

### 4.4 AISemanticComp - AI 语义理解

```python
class AISemanticComp(WorkflowComponent, ComponentExecutable):
    """
    AI 语义理解组件

    职责：
    1. 只处理 pending_items（规则无法处理的部分）
    2. 为每个 pending_item 调用 AI
    3. 将结果合并回 extraction_result
    """

    def __init__(self):
        self._llm = OpenAIChatModel(...)

    async def invoke(self, inputs, runtime, context):
        extraction_result: ExtractionResult = inputs["extraction_result"]
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

        system_prompt = """你是代码转换专家，将 LangGraph 代码转换为 openJiuwen 格式。

openJiuwen 组件规范：
- 异步方法: async def invoke(self, inputs, runtime, context)
- 输入访问: inputs["field_name"]
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
```

### 4.5 IRBuilderComp - IR 构建器

```python
class IRBuilderComp(WorkflowComponent, ComponentExecutable):
    """
    IR 构建器

    此时所有代码已经转换完成，只需组装 IR 结构
    不需要 AI
    """

    async def invoke(self, inputs, runtime, context):
        result: ExtractionResult = inputs["extraction_result"]

        # 构建节点 IR
        nodes_ir = []
        for node in result.nodes:
            nodes_ir.append(WorkflowNodeIR(
                name=node.name,
                class_name=self._to_class_name(node.name),
                converted_body=node.converted_body,  # 已转换的代码
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
                condition_func=edge.get("condition_func"),
                condition_map=edge.get("condition_map")
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
            "workflow_ir": workflow_ir
        }
```

### 4.6 CodeGeneratorComp - 代码生成器

```python
class CodeGeneratorComp(WorkflowComponent, ComponentExecutable):
    """
    代码生成器

    纯模板填充，不需要 AI
    IR 中已包含转换后的代码
    """

    async def invoke(self, inputs, runtime, context):
        agent_ir = inputs["agent_ir"]
        workflow_ir = inputs["workflow_ir"]
        output_dir = inputs["output_dir"]

        sections = []

        # 1. 导入语句（模板）
        sections.append(self._gen_imports(agent_ir))

        # 2. 工具函数（模板 + IR数据）
        for tool in agent_ir.tools:
            sections.append(self._gen_tool(tool))

        # 3. 组件类（模板 + 已转换的body）
        for node in workflow_ir.nodes:
            sections.append(self._gen_component(node))

        # 4. 路由函数（模板）
        for edge in workflow_ir.edges:
            if edge.is_conditional:
                sections.append(self._gen_router(edge))

        # 5. 工作流构建（模板）
        sections.append(self._gen_workflow(workflow_ir))

        # 6. 主函数（模板）
        sections.append(self._gen_main())

        code = "\n\n".join(sections)

        # 写入文件
        output_file = self._write_file(code, output_dir, agent_ir.name)

        return {
            "generated_code": code,
            "generated_files": [output_file]
        }

    def _gen_component(self, node: WorkflowNodeIR) -> str:
        """生成组件类 - 纯模板填充"""

        # node.converted_body 已经是转换好的代码
        template = '''class {class_name}(WorkflowComponent, ComponentExecutable):
    """{name} 组件"""

    def __init__(self, llm=None):
        self._llm = llm
        self.model_name = "default"

    async def invoke(self, inputs: dict, runtime: WorkflowRuntime, context: ComponentContext) -> dict:
        # 初始化输出
{output_init}

        # 组件逻辑（已转换）
{body}

        return {{{outputs}}}
'''
        return template.format(
            class_name=node.class_name,
            name=node.name,
            output_init=self._gen_output_init(node.outputs),
            body=self._indent(node.converted_body, 8),
            outputs=", ".join(f'"{o}": {o}' for o in node.outputs)
        )

    def _gen_router(self, edge: WorkflowEdgeIR) -> str:
        """生成路由函数 - 纯模板"""

        template = '''def {source}_router(runtime: WorkflowRuntime) -> str:
    """{source} 节点的路由函数"""
{body}
'''
        # edge.condition_func 已经是转换好的代码
        return template.format(
            source=edge.source,
            body=self._indent(edge.condition_func, 4)
        )
```

---

## 5. 工作流定义

```python
def build_migration_workflow() -> Workflow:
    """构建迁移工作流"""

    workflow = Workflow()

    # 起点
    workflow.set_start_comp("start", Start(), inputs_schema={
        "source_path": "${source_path}",
        "output_dir": "${output_dir}"
    })

    # 项目检测
    workflow.add_workflow_comp("detector", ProjectDetectorComp(),
        inputs_schema={"source_path": "${start.source_path}"})

    # 文件加载
    workflow.add_workflow_comp("loader", FileLoaderComp(),
        inputs_schema={
            "file_list": "${detector.file_list}",
            "dependency_order": "${detector.dependency_order}"
        })

    # AST 解析
    workflow.add_workflow_comp("parser", ASTParserComp(),
        inputs_schema={"file_contents": "${loader.file_contents}"})

    # 规则提取（含转换）
    workflow.add_workflow_comp("extractor", RuleExtractorComp(),
        inputs_schema={
            "ast_map": "${parser.ast_map}",
            "dependency_order": "${detector.dependency_order}"
        })

    # 待处理检查
    workflow.add_workflow_comp("checker", PendingCheckComp(),
        inputs_schema={"extraction_result": "${extractor.extraction_result}"})

    # AI 语义理解（条件触发）
    workflow.add_workflow_comp("ai", AISemanticComp(),
        inputs_schema={"extraction_result": "${extractor.extraction_result}"})

    # IR 构建
    workflow.add_workflow_comp("ir_builder", IRBuilderComp(),
        inputs_schema={"extraction_result": "${ai.extraction_result|extractor.extraction_result}"})

    # 代码生成（不需要AI）
    workflow.add_workflow_comp("generator", CodeGeneratorComp(),
        inputs_schema={
            "agent_ir": "${ir_builder.agent_ir}",
            "workflow_ir": "${ir_builder.workflow_ir}",
            "output_dir": "${start.output_dir}"
        })

    # 报告生成
    workflow.add_workflow_comp("reporter", ReportComp(),
        inputs_schema={
            "extraction_result": "${ir_builder.extraction_result}",
            "generated_files": "${generator.generated_files}"
        })

    # 终点
    workflow.set_end_comp("end", End(), inputs_schema={
        "generated_files": "${generator.generated_files}",
        "report": "${reporter.report}"
    })

    # 连接
    workflow.add_connection("start", "detector")
    workflow.add_connection("detector", "loader")
    workflow.add_connection("loader", "parser")
    workflow.add_connection("parser", "extractor")
    workflow.add_connection("extractor", "checker")

    # 条件路由
    workflow.add_conditional_connection("checker", pending_router, {
        "ai": "ai",
        "ir_builder": "ir_builder"
    })

    workflow.add_connection("ai", "ir_builder")
    workflow.add_connection("ir_builder", "generator")
    workflow.add_connection("generator", "reporter")
    workflow.add_connection("reporter", "end")

    return workflow


def pending_router(runtime) -> str:
    """路由函数：是否需要 AI 处理"""
    has_pending = runtime.get_global_state("checker.has_pending")
    return "ai" if has_pending else "ir_builder"
```

---

## 6. 各阶段职责总结

| 阶段 | 组件 | 职责 | 需要AI |
|------|------|------|--------|
| 检测 | ProjectDetector | 检测单/多文件，分析依赖 | 否 |
| 加载 | FileLoader | 读取文件内容 | 否 |
| 解析 | ASTParser | 生成 AST | 否 |
| **提取+转换** | **RuleExtractor** | **规则提取结构 + 转换函数体** | **否** |
| 检查 | PendingCheck | 检查是否有待处理项 | 否 |
| **转换剩余** | **AISemantic** | **AI转换规则失败的部分** | **是** |
| 构建 | IRBuilder | 组装 IR 结构 | 否 |
| 生成 | CodeGenerator | 模板填充生成代码 | **否** |
| 报告 | Report | 生成迁移报告 | 否 |

**关键点**：
- AI 只在 `AISemantic` 阶段使用
- `CodeGenerator` 只做模板填充，不需要 AI
- IR 中存储的是**已转换的代码**

---

## 7. 执行示例

### 7.1 标准代码（规则完全处理）

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

### 7.2 复杂代码（需要 AI）

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

### 7.3 多文件项目

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

## 8. 文件结构

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

## 9. 总结

### 设计要点

1. **转换前置**：所有代码转换在 RuleExtractor + AISemantic 阶段完成
2. **规则优先**：最大化规则处理，减少 AI 调用
3. **精确提问**：AI 只回答具体问题，不重新分析整个函数
4. **IR 存储已转换代码**：CodeGenerator 只做模板填充
5. **多文件支持**：自动检测，按依赖顺序处理

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
