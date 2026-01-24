"""
边/路由规则单元测试
"""
import ast
import pytest

from lg2jiuwen_tool.rules.edge_rules import EdgeRule, ReturnRule


class TestReturnRule:
    """返回语句规则测试"""

    def setup_method(self):
        self.rule = ReturnRule()

    def test_matches_return_state(self):
        """测试匹配 return state"""
        code = 'return state'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_return_END(self):
        """测试匹配 return END"""
        code = 'return END'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_return_dict(self):
        """测试匹配 return {"key": value}"""
        code = 'return {"key": value}'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_not_matches_return_string(self):
        """测试不匹配 return "string" (非特定模式)"""
        code = 'return "hello"'
        node = ast.parse(code).body[0]
        # 返回字符串字面量通常不需要转换
        assert self.rule.matches(node) is False

    def test_convert_return_state(self):
        """测试转换 return state -> return outputs"""
        self.rule.set_context(collected_outputs=["messages", "result"])
        code = 'return state'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'return' in result.code
        assert 'messages' in result.code or '"messages"' in result.code

    def test_convert_return_END(self):
        """测试转换 return END -> return "end" """
        code = 'return END'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert '"end"' in result.code or "'end'" in result.code

    def test_convert_return_dict(self):
        """测试转换 return {"key": value} 保持不变"""
        code = 'return {"key": value}'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'key' in result.code


class TestEdgeRule:
    """边提取规则测试"""

    def setup_method(self):
        self.rule = EdgeRule()

    def test_matches_add_edge(self):
        """测试匹配 graph.add_edge("a", "b")"""
        code = 'graph.add_edge("node1", "node2")'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_add_conditional_edges(self):
        """测试匹配 graph.add_conditional_edges(...)"""
        code = 'graph.add_conditional_edges("node1", router, {"a": "n1", "b": "n2"})'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_set_entry_point(self):
        """测试匹配 graph.set_entry_point("node")"""
        code = 'graph.set_entry_point("start_node")'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_not_matches_add_node(self):
        """测试不匹配 graph.add_node(...)"""
        code = 'graph.add_node("node1", func)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_extract_add_edge(self):
        """测试提取普通边"""
        code = 'graph.add_edge("node1", "node2")'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        edge_info = result.context.get("edge_info", {})
        assert edge_info.get("source") == "node1"
        assert edge_info.get("target") == "node2"
        assert edge_info.get("is_conditional") is False

    def test_extract_add_conditional_edges(self):
        """测试提取条件边"""
        code = 'graph.add_conditional_edges("node1", route_func, {"yes": "node2", "no": "node3"})'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        edge_info = result.context.get("edge_info", {})
        assert edge_info.get("source") == "node1"
        assert edge_info.get("is_conditional") is True
        condition_map = edge_info.get("condition_map", {})
        assert "yes" in condition_map or condition_map  # 检查有条件映射

    def test_extract_edge_to_END(self):
        """测试提取到 END 的边"""
        code = 'graph.add_edge("final", END)'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        edge_info = result.context.get("edge_info", {})
        assert edge_info.get("target") in ("END", "end")
