# 多文件支持优化设计文档

> 版本: v1.0
> 日期: 2026-01-21
> 目标: 让 lg2jiuwen_tool 自动支持单文件和多文件 LangGraph 项目的转换

---

## 1. 背景与问题

### 1.1 当前限制

当前工具只支持单个 `.py` 文件的转换：

```python
# service.py
def migrate(source_path: str, output_dir: str) -> str:
    if not source_path.endswith(".py"):
        raise ValueError(f"{source_path} must be a python file")
```

### 1.2 实际场景

典型的 LangGraph 项目通常会将代码分散到多个文件：

```
my_agent/
├── __init__.py
├── graph.py           # 主图定义 (StateGraph, add_node, add_edge)
├── state.py           # 状态定义 (TypedDict)
├── nodes/
│   ├── __init__.py
│   ├── extract.py     # 节点函数
│   └── process.py     # 节点函数
├── tools/
│   ├── __init__.py
│   └── weather.py     # 工具函数
└── routers/
    └── conditions.py  # 条件路由函数
```

### 1.3 设计目标

1. **向后兼容**: 单文件项目无需任何改动即可使用
2. **自动检测**: 程序自动判断使用单文件还是多文件模式
3. **用户透明**: 用户只需提供入口文件或目录，无需额外配置
4. **渐进增强**: 分阶段实现，优先保证核心功能

---

## 2. 整体架构

### 2.1 处理流程

```
用户输入（文件或目录）
        │
        ▼
┌─────────────────────┐
│   SmartDetector     │  ← 新增：智能检测器
│   检测项目类型       │
└─────────┬───────────┘
          │
          ▼
    ┌─────┴─────┐
    │           │
    ▼           ▼
[单文件]    [多文件]
    │           │
    ▼           ▼
原有Parser  ProjectParser  ← 新增：项目解析器
    │           │
    └─────┬─────┘
          │
          ▼
    ParseResult（统一格式）
          │
          ▼
    IRBuilder（无需修改）
          │
          ▼
    OpenJiuwenGenerator（无需修改）
          │
          ▼
    输出 openJiuwen 代码
```

### 2.2 模块职责

| 模块 | 状态 | 职责 |
|------|------|------|
| `smart_detector.py` | **新增** | 分析导入语句，判断项目类型 |
| `project_parser.py` | **新增** | 多文件解析与合并 |
| `parser.py` | 不变 | 单文件 AST 解析（被 ProjectParser 复用）|
| `ir_models.py` | 小改 | 新增 `MergedParseResult` 数据类 |
| `migrator.py` | 小改 | 新增 `smart_migrate()` 入口函数 |
| `service.py` | 小改 | 支持目录输入 |
| `generator.py` | 不变 | 代码生成逻辑无需改动 |

---

## 3. 核心模块设计

### 3.1 SmartDetector（智能检测器）

**文件**: `src/lg2jiuwen_tool/smart_detector.py`

**核心逻辑**:

```python
class SmartDetector:
    """智能项目类型检测器"""

    def detect(self, entry_path: str) -> DetectionResult:
        """
        检测流程:
        1. 确定入口文件（如果输入是目录，自动查找）
        2. 解析入口文件的所有 import 语句
        3. 将导入分类为「本地」和「外部」
        4. 检查本地模块是否包含 LangGraph 组件
        5. 返回检测结果
        """
```

**导入分类规则**:

| 导入类型 | 示例 | 分类 |
|---------|------|------|
| 相对导入 | `from .nodes import extract` | 本地 |
| 相对导入 | `from ..tools import weather` | 本地 |
| 标准库 | `import os, json, typing` | 外部 |
| 第三方库 | `from langchain_openai import ChatOpenAI` | 外部 |
| 项目内绝对导入 | `from nodes.extract import func` | 本地（需解析路径）|

**已知外部包列表**（部分）:

```python
KNOWN_EXTERNAL_PACKAGES = {
    # 标准库
    'os', 'sys', 'json', 're', 'typing', 'dataclasses', 'pathlib',
    'asyncio', 'datetime', 'logging', 'collections', 'functools',

    # LangGraph/LangChain 生态
    'langchain', 'langchain_core', 'langchain_openai', 'langgraph',

    # 常见第三方库
    'pydantic', 'httpx', 'requests', 'openai', 'anthropic',
}
```

**LangGraph 组件特征**:

```python
LANGGRAPH_INDICATORS = [
    'TypedDict',              # 状态定义
    'StateGraph',             # 图定义
    '@tool',                  # 工具装饰器
    'add_node',               # 添加节点
    'add_edge',               # 添加边
    'add_conditional_edges',  # 条件边
]
```

**检测结果数据结构**:

```python
@dataclass
class DetectionResult:
    project_type: ProjectType        # SINGLE_FILE 或 MULTI_FILE
    entry_file: str                  # 入口文件路径
    local_imports: List[ImportInfo]  # 本地导入列表
    external_imports: List[ImportInfo]  # 外部导入列表
    related_files: List[str]         # 需要一起解析的文件
    reason: str                      # 判断原因（用于日志/调试）
```

### 3.2 ProjectParser（项目解析器）

**文件**: `src/lg2jiuwen_tool/project_parser.py`

**核心逻辑**:

```python
class ProjectParser:
    """项目级解析器"""

    def parse(self, entry_path: str) -> ParseResult:
        """
        统一入口:
        1. 调用 SmartDetector 检测项目类型
        2. 单文件 → 调用原有 LangGraphParser
        3. 多文件 → 递归解析并合并结果
        4. 返回统一的 ParseResult
        """
```

**多文件合并策略**:

| 元素类型 | 合并规则 |
|---------|---------|
| `state_fields` | 去重合并（按字段名）|
| `node_functions` | 去重合并（按函数名）|
| `conditional_functions` | 去重合并（按函数名）|
| `tools` | 去重合并（按工具名）|
| `edges` | 以入口文件为准 |
| `conditional_edges` | 以入口文件为准 |
| `entry_point` | 以入口文件为准 |
| `graph_name` | 以入口文件为准 |
| `llm_config` | 优先入口文件，其次第一个发现的 |
| `import_statements` | 去重合并 |
| `global_variables` | 去重合并（按变量名）|

**解析顺序**:

```
被依赖的文件（nodes/, tools/）
        ↓
    入口文件（graph.py）
```

先解析被依赖的模块，确保函数定义在被引用时已存在。

### 3.3 数据结构扩展

**文件**: `src/lg2jiuwen_tool/ir_models.py`

新增数据类:

```python
@dataclass
class ImportInfo:
    """导入语句信息"""
    module: str                      # 模块名
    names: List[str]                 # 导入的名称
    is_relative: bool                # 是否相对导入
    level: int                       # 相对导入层级
    statement: str                   # 原始语句
    resolved_path: Optional[str]     # 解析后的文件路径


@dataclass
class MergedParseResult:
    """多文件合并后的解析结果"""
    # 继承 ParseResult 所有字段
    # ...

    # 新增字段
    source_files: List[str]          # 来源文件列表
    source_map: Dict[str, str]       # 元素 -> 来源文件映射

    def to_parse_result(self) -> ParseResult:
        """转换为标准 ParseResult"""
```

---

## 4. 检测流程详解

### 4.1 流程图

```
                      用户输入
                         │
                         ▼
              ┌──────────────────────┐
              │  是文件还是目录？      │
              └──────────┬───────────┘
                   ┌─────┴─────┐
                   ▼           ▼
               [文件]       [目录]
                   │           │
                   │           ▼
                   │     自动查找入口文件
                   │     优先级:
                   │     1. main.py
                   │     2. graph.py
                   │     3. app.py
                   │     4. agent.py
                   │     5. 含 StateGraph 的 .py
                   │           │
                   └─────┬─────┘
                         ▼
              ┌──────────────────────┐
              │  解析导入语句         │
              │  import X            │
              │  from Y import Z     │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │  分类导入             │
              │  ├─ 相对导入 → 本地   │
              │  ├─ 已知外部包 → 外部 │
              │  └─ 其他 → 尝试解析   │
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │  本地模块路径解析     │
              │  from .nodes import X│
              │  → ./nodes.py        │
              │  → ./nodes/__init__.py│
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │  检查本地模块内容     │
              │  是否包含:           │
              │  - TypedDict         │
              │  - @tool             │
              │  - StateGraph        │
              │  - add_node 等       │
              └──────────┬───────────┘
                   ┌─────┴─────┐
                   ▼           ▼
            [没有/不包含]  [有且包含]
                   │           │
                   ▼           ▼
             单文件模式    多文件模式
```

### 4.2 示例场景

**场景 1: 单文件项目**

输入: `weather_agent.py`

```python
# weather_agent.py
import os
from typing import TypedDict
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    ...

@tool
def get_weather(...):
    ...

workflow = StateGraph(AgentState)
...
```

检测结果:
- 所有导入都是外部包
- 无本地导入
- → **单文件模式**

**场景 2: 多文件项目**

输入: `my_agent/graph.py`

```python
# my_agent/graph.py
from langgraph.graph import StateGraph
from .state import AgentState          # ← 本地导入
from .nodes.extract import extract_node  # ← 本地导入
from .tools.weather import get_weather   # ← 本地导入

workflow = StateGraph(AgentState)
workflow.add_node("extract", extract_node)
...
```

```python
# my_agent/state.py
from typing import TypedDict  # ← 包含 LangGraph 组件

class AgentState(TypedDict):
    sentence: str
    ...
```

检测结果:
- 发现本地导入: `.state`, `.nodes.extract`, `.tools.weather`
- `state.py` 包含 `TypedDict` → LangGraph 组件
- → **多文件模式**
- related_files: `['state.py', 'nodes/extract.py', 'tools/weather.py']`

---

## 5. 接口变更

### 5.1 service.py

**Before**:
```python
def migrate(source_path: str, output_dir: str) -> str:
    if not source_path.endswith(".py"):
        raise ValueError(f"{source_path} must be a python file")
    ...
```

**After**:
```python
def migrate(source_path: str, output_dir: str) -> str:
    """
    智能迁移入口

    Args:
        source_path: 支持以下输入:
            - 单个 .py 文件路径
            - 项目目录路径
            - 多文件项目的入口文件路径
    """
    # 移除 .py 后缀检查
    if not os.path.exists(source_path):
        raise ValueError(f"{source_path} does not exist")
    ...
```

### 5.2 migrator.py

**新增函数**:
```python
def smart_migrate(
    source_path: str,
    output_dir: str,
    options: MigrationOptions = None
) -> MigrationResult:
    """
    智能迁移 - 自动检测并选择合适的解析策略
    """
```

**原 `migrate()` 函数**: 保持不变，作为单文件的直接入口（向后兼容）

---

## 6. 边界情况处理

### 6.1 循环导入

```python
# a.py
from .b import func_b

# b.py
from .a import func_a  # 循环！
```

**处理方案**:
- 使用 `_parsed_files: Set[str]` 记录已解析文件
- 遇到已解析文件直接跳过

### 6.2 动态导入

```python
module = importlib.import_module(f"nodes.{node_name}")
```

**处理方案**:
- 静态分析无法处理
- 在报告中给出警告，提示用户手动检查

### 6.3 条件导入

```python
if TYPE_CHECKING:
    from .types import SomeType
```

**处理方案**:
- 仅用于类型检查的导入，通常不包含运行时代码
- 正常解析，不影响结果

### 6.4 相对导入层级过深

```python
from ...shared.utils import helper  # level=3
```

**处理方案**:
- 正确计算路径: `parent.parent.parent / shared / utils.py`
- 超出项目根目录时返回解析失败

### 6.5 命名冲突

```python
# nodes/a.py
def process(state): ...

# nodes/b.py
def process(state): ...  # 同名！
```

**处理方案**:
- 以先解析的为准
- 在报告中给出警告
- 后续可考虑支持命名空间前缀

---

## 7. 实现计划

### Phase 1: 基础框架（优先）

1. 创建 `smart_detector.py`
   - 实现导入语句解析
   - 实现本地/外部分类
   - 实现 LangGraph 组件检测

2. 创建 `project_parser.py`
   - 实现单文件分支（调用原有 Parser）
   - 实现基础多文件合并

3. 修改 `migrator.py`
   - 添加 `smart_migrate()` 函数

4. 修改 `service.py`
   - 移除 `.py` 后缀限制
   - 调用 `smart_migrate()`

### Phase 2: 完善合并逻辑

1. 完善解析顺序（依赖拓扑排序）
2. 处理命名冲突
3. 完善导入语句去重（过滤本地导入）

### Phase 3: 增强功能

1. 支持目录输入（自动查找入口）
2. 递归解析嵌套导入
3. 迁移报告增加多文件信息

### Phase 4: 测试与文档

1. 单元测试
2. 集成测试（准备多文件示例项目）
3. 更新 README

---

## 8. 测试用例设计

### 8.1 单文件测试

```
test_cases/
└── single_file/
    └── weather_agent.py  # 现有示例
```

预期: 检测为单文件模式，输出与当前一致

### 8.2 多文件测试

```
test_cases/
└── multi_file/
    ├── graph.py          # 入口，导入下面的模块
    ├── state.py          # TypedDict 定义
    ├── nodes/
    │   ├── __init__.py
    │   └── extract.py    # 节点函数
    └── tools/
        ├── __init__.py
        └── weather.py    # @tool 装饰器
```

预期:
- 检测为多文件模式
- 合并 4 个文件的内容
- 正确生成 openJiuwen 代码

### 8.3 边界测试

- 循环导入项目
- 仅包含工具的独立模块
- 超深层级相对导入

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 路径解析错误 | 找不到本地模块 | 充分测试各种导入格式 |
| 合并冲突 | 代码生成错误 | 添加冲突检测和警告 |
| 性能问题 | 大项目解析慢 | 添加文件数量限制 |
| 误判项目类型 | 解析不完整 | 提供手动指定模式的选项 |

---

## 10. 开放问题

1. **是否需要配置文件支持?**
   - 对于复杂项目，用户可能需要手动指定哪些文件参与转换
   - 建议: Phase 1 不支持，后续根据反馈添加

2. **子图（Subgraph）如何处理?**
   - LangGraph 支持在一个图中嵌入另一个图
   - 建议: 当前标记为不支持，单独处理

3. **输出是单文件还是多文件?**
   - 当前设计: 无论输入是单文件还是多文件，输出都是单个 openJiuwen 文件
   - 后续可考虑: 保持源码结构的多文件输出

---

## 附录 A: 完整代码结构

```
src/lg2jiuwen_tool/
├── __init__.py
├── __main__.py
├── cli.py
├── smart_detector.py    # 新增
├── project_parser.py    # 新增
├── parser.py            # 无改动
├── ir_models.py         # 小改（新增数据类）
├── migrator.py          # 小改（新增 smart_migrate）
├── generator.py         # 无改动
└── service.py           # 小改（支持目录）
```

## 附录 B: 使用示例

```bash
# 单文件（与当前用法一致）
python -m lg2jiuwen_tool weather_agent.py -o output/

# 多文件项目 - 指定入口文件
python -m lg2jiuwen_tool my_agent/graph.py -o output/

# 多文件项目 - 指定目录（自动查找入口）
python -m lg2jiuwen_tool my_agent/ -o output/
```

```python
# API 调用
from lg2jiuwen_tool import migrate

# 自动检测模式
result = migrate("my_agent/graph.py", "output/")
```
