"""
LLM 调用规则单元测试
"""
import ast
import pytest

from lg2jiuwen_tool.rules.llm_rules import LLMInvokeRule


class TestLLMInvokeRule:
    """LLM 调用规则测试"""

    def setup_method(self):
        self.rule = LLMInvokeRule()

    def test_matches_llm_invoke(self):
        """测试匹配 llm.invoke(msgs)"""
        code = 'response = llm.invoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_model_invoke(self):
        """测试匹配 model.invoke(msgs)"""
        code = 'response = model.invoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_chat_invoke(self):
        """测试匹配 chat.invoke(msgs)"""
        code = 'response = chat.invoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_chat_model_invoke(self):
        """测试匹配 chat_model.invoke(msgs)"""
        code = 'response = chat_model.invoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_matches_llm_ainvoke(self):
        """测试匹配 llm.ainvoke(msgs)"""
        code = 'response = llm.ainvoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is True

    def test_not_matches_other_method(self):
        """测试不匹配其他方法"""
        code = 'response = llm.generate(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_not_matches_other_object(self):
        """测试不匹配其他对象"""
        code = 'response = api.invoke(messages)'
        node = ast.parse(code).body[0]
        assert self.rule.matches(node) is False

    def test_convert_llm_invoke(self):
        """测试转换 llm.invoke(messages)"""
        code = 'response = llm.invoke(messages)'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'await self._llm.ainvoke' in result.code
        assert 'model_name=self.model_name' in result.code
        assert 'messages=messages' in result.code
        assert 'response' in result.code

    def test_convert_with_variable_messages(self):
        """测试转换带变量的消息列表"""
        code = 'result = model.invoke(chat_history)'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'messages=chat_history' in result.code

    def test_convert_with_inline_messages(self):
        """测试转换内联消息列表"""
        code = 'response = llm.invoke([{"role": "user", "content": "hello"}])'
        node = ast.parse(code).body[0]
        result = self.rule.convert(node)
        assert result.success is True
        assert 'await self._llm.ainvoke' in result.code
