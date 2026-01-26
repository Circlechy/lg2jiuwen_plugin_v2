# AST (抽象语法树) 原理

## 什么是 AST

AST 是源代码的树形结构表示，将代码从文本转换为可编程操作的数据结构。

```
源代码文本  →  词法分析  →  语法分析  →  AST 树
```

## 简单示例

```python
# 源代码
x = a + 1
```

```
# AST 树形结构
Assign
├── targets: [Name('x')]
└── value: BinOp
           ├── left: Name('a')
           ├── op: Add
           └── right: Constant(1)
```

## 核心节点类型

| 节点类型 | 对应代码 |
|---------|---------|
| `FunctionDef` | `def func():` |
| `ClassDef` | `class Foo:` |
| `Assign` | `x = value` |
| `Call` | `func(arg)` |
| `Attribute` | `obj.attr` |
| `Subscript` | `dict["key"]` |
| `Return` | `return value` |

## 在迁移工具中的应用

```python
# 1. 解析源代码
import ast
tree = ast.parse(source_code)

# 2. 遍历节点，匹配规则
for node in ast.walk(tree):
    if isinstance(node, ast.Subscript):      # 匹配 state["key"]
        # 转换为 inputs["key"]
    elif isinstance(node, ast.Call):          # 匹配 llm.invoke()
        # 转换为 await self._llm.ainvoke()
```

## 为什么用 AST

| 方式 | 缺点 |
|-----|------|
| 正则替换 | 无法理解代码结构，容易误替换字符串/注释 |
| **AST** | 精确识别语法元素，区分变量名/字符串/注释 |

AST 让代码迁移工具能够"理解"代码结构，而非简单的文本替换。
