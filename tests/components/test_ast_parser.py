"""
AST 解析组件单元测试
"""
import ast
import pytest

from lg2jiuwen_tool.components.ast_parser import ASTParserComp


class TestASTParserComp:
    """AST 解析组件测试"""

    def setup_method(self):
        self.comp = ASTParserComp()

    @pytest.mark.asyncio
    async def test_parse_simple_code(self):
        """测试解析简单代码"""
        code = '''
def hello():
    print("Hello")
'''
        result = await self.comp.invoke(
            inputs={
                "file_contents": {"test.py": code},
                "dependency_order": ["test.py"]
            },
            runtime=None,
            context=None
        )
        assert "ast_map" in result
        assert "test.py" in result["ast_map"]
        # 应该能找到函数定义
        tree = result["ast_map"]["test.py"]
        assert isinstance(tree, ast.Module)
        func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert len(func_defs) == 1
        assert func_defs[0].name == "hello"

    @pytest.mark.asyncio
    async def test_parse_class_definition(self):
        """测试解析类定义"""
        code = '''
class MyClass:
    def __init__(self):
        self.value = 0

    def method(self):
        return self.value
'''
        result = await self.comp.invoke(
            inputs={
                "file_contents": {"test.py": code},
                "dependency_order": ["test.py"]
            },
            runtime=None,
            context=None
        )
        tree = result["ast_map"]["test.py"]
        class_defs = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert len(class_defs) == 1
        assert class_defs[0].name == "MyClass"

    @pytest.mark.asyncio
    async def test_parse_imports(self):
        """测试解析导入语句"""
        code = '''
import os
from typing import List, Dict
from langgraph.graph import StateGraph
'''
        result = await self.comp.invoke(
            inputs={
                "file_contents": {"test.py": code},
                "dependency_order": ["test.py"]
            },
            runtime=None,
            context=None
        )
        tree = result["ast_map"]["test.py"]
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert len(imports) == 3

    @pytest.mark.asyncio
    async def test_parse_multiple_files(self):
        """测试解析多个文件"""
        files = {
            "a.py": "def func_a(): pass",
            "b.py": "def func_b(): pass",
            "c.py": "class C: pass"
        }
        result = await self.comp.invoke(
            inputs={
                "file_contents": files,
                "dependency_order": list(files.keys())
            },
            runtime=None,
            context=None
        )
        assert len(result["ast_map"]) == 3
        for filename in files:
            assert filename in result["ast_map"]

    @pytest.mark.asyncio
    async def test_parse_syntax_error(self):
        """测试解析语法错误的代码"""
        code = '''
def broken(
    # 缺少闭合括号和函数体
'''
        result = await self.comp.invoke(
            inputs={
                "file_contents": {"broken.py": code},
                "dependency_order": ["broken.py"]
            },
            runtime=None,
            context=None
        )
        # 应该处理语法错误而不是崩溃
        assert "ast_map" in result
        # 可能为空或包含错误标记
        if "broken.py" in result["ast_map"]:
            # 如果有值，应该是 None 或错误标记
            pass

    @pytest.mark.asyncio
    async def test_parse_decorated_function(self):
        """测试解析带装饰器的函数"""
        code = '''
@tool
def my_tool(query: str) -> str:
    """Tool docstring"""
    return f"Result: {query}"
'''
        result = await self.comp.invoke(
            inputs={
                "file_contents": {"test.py": code},
                "dependency_order": ["test.py"]
            },
            runtime=None,
            context=None
        )
        tree = result["ast_map"]["test.py"]
        func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert len(func_defs) == 1
        assert len(func_defs[0].decorator_list) == 1

    @pytest.mark.asyncio
    async def test_preserve_dependency_order(self):
        """测试保持依赖顺序"""
        files = {"z.py": "# z", "a.py": "# a", "m.py": "# m"}
        order = ["a.py", "m.py", "z.py"]

        result = await self.comp.invoke(
            inputs={
                "file_contents": files,
                "dependency_order": order
            },
            runtime=None,
            context=None
        )
        assert result["dependency_order"] == order
