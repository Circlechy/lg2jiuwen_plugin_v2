"""
工具调用规则单元测试
"""
import ast
import pytest

from lg2jiuwen_tool.rules.tool_rules import ToolCallRule


class TestToolCallRule:
    """工具调用规则测试"""

    def setup_method(self):
        self.rule = ToolCallRule()
        self.rule.set_context(known_tools={"get_weather", "search", "calculator"})

    def test_matches_tool_invoke_dict(self):
        """测试匹配 tool.invoke({"arg": value})"""
        code = 'result = get_weather.invoke({"city": "Beijing"})'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_tool_run(self):
        """测试匹配 tool.run(...)"""
        code = 'result = search.run("query")'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_not_matches_unknown_tool(self):
        """测试不匹配未知工具"""
        code = 'result = unknown_tool.invoke({})'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_not_matches_other_method(self):
        """测试不匹配其他方法"""
        code = 'result = get_weather.describe()'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_convert_tool_invoke_dict(self):
        """测试转换 tool.invoke({"arg": value}) -> tool(arg=value)"""
        code = 'result = get_weather.invoke({"city": "Beijing"})'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'get_weather(' in result.code
        assert 'city=' in result.code

    def test_convert_tool_invoke_variable(self):
        """测试转换 tool.invoke(params) -> tool(**params)"""
        code = 'result = search.invoke(params)'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'search(**params)' in result.code or 'search(params)' in result.code

    def test_convert_preserves_target(self):
        """测试转换保留赋值目标"""
        code = 'weather_data = get_weather.invoke({"city": "Shanghai"})'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'weather_data' in result.code


class TestToolCallRuleWithoutContext:
    """无上下文的工具调用规则测试"""

    def setup_method(self):
        self.rule = ToolCallRule()

    def test_matches_any_invoke(self):
        """无上下文时匹配任意 .invoke()"""
        code = 'result = any_tool.invoke({})'
        node = ast.parse(code).body[0]
        # 无 known_tools 时应该尝试匹配任何 .invoke() 调用
        assert self.rule.matches(node) is True

    def test_matches_any_run(self):
        """无上下文时匹配任意 .run()"""
        code = 'result = any_tool.run("arg")'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True
