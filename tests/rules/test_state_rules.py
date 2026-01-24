"""
状态规则单元测试
"""
import ast
import pytest

from lg2jiuwen_tool.rules.state_rules import StateAccessRule, StateAssignRule


class TestStateAccessRule:
    """状态访问规则测试"""

    def setup_method(self):
        self.rule = StateAccessRule()

    def test_matches_state_subscript(self):
        """测试匹配 state["key"]"""
        code = 'state["key"]'
        node = ast.parse(code, mode='eval').body
        assert self.rule.matches(node) is True

    def test_matches_State_subscript(self):
        """测试匹配 State["key"]"""
        code = 'State["key"]'
        node = ast.parse(code, mode='eval').body
        assert self.rule.matches(node) is True

    def test_not_matches_other_subscript(self):
        """测试不匹配其他变量"""
        code = 'data["key"]'
        node = ast.parse(code, mode='eval').body
        assert self.rule.matches(node) is False

    def test_matches_state_get(self):
        """测试匹配 state.get("key")"""
        code = 'state.get("key")'
        node = ast.parse(code, mode='eval').body
        assert self.rule.matches(node) is True

    def test_matches_state_get_with_default(self):
        """测试匹配 state.get("key", default)"""
        code = 'state.get("key", None)'
        node = ast.parse(code, mode='eval').body
        assert self.rule.matches(node) is True

    def test_convert_state_subscript(self):
        """测试转换 state["key"] -> inputs["key"]"""
        code = 'state["key"]'
        node = ast.parse(code, mode='eval').body
        result = self.rule.convert(node)
        assert result.success is True
        assert result.code == 'inputs["key"]'
        assert "key" in result.inputs

    def test_convert_state_get(self):
        """测试转换 state.get("key") -> inputs.get("key")"""
        code = 'state.get("key")'
        node = ast.parse(code, mode='eval').body
        result = self.rule.convert(node)
        assert result.success is True
        assert result.code == 'inputs.get("key")'
        assert "key" in result.inputs

    def test_convert_state_get_with_default(self):
        """测试转换 state.get("key", []) -> inputs.get("key", [])"""
        code = 'state.get("key", [])'
        node = ast.parse(code, mode='eval').body
        result = self.rule.convert(node)
        assert result.success is True
        assert result.code == 'inputs.get("key", [])'
        assert "key" in result.inputs


class TestStateAssignRule:
    """状态赋值规则测试"""

    def setup_method(self):
        self.rule = StateAssignRule()

    def test_matches_state_subscript_assign(self):
        """测试匹配 state["key"] = value"""
        code = 'state["key"] = value'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_not_matches_regular_assign(self):
        """测试不匹配普通赋值"""
        code = 'x = value'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_not_matches_data_subscript_assign(self):
        """测试不匹配 data["key"] = value"""
        code = 'data["key"] = value'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_convert_state_assign(self):
        """测试转换 state["key"] = value -> key = value"""
        code = 'state["key"] = value'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert result.code == 'key = value'
        assert "key" in result.outputs

    def test_convert_state_assign_complex_value(self):
        """测试转换复杂值赋值"""
        code = 'state["result"] = func(a, b)'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert result.code == 'result = func(a, b)'
        assert "result" in result.outputs
