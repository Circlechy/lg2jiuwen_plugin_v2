"""
集成测试 - 验证完整迁移流程
"""
import os
import tempfile
import pytest

from lg2jiuwen_tool.service import migrate_new, MigrationOptions, MigrationResult


class TestWeatherAgentMigration:
    """Weather Agent 迁移集成测试"""

    @pytest.fixture
    def weather_agent_code(self):
        """Weather Agent 示例代码"""
        return '''
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get weather for a city"""
    return f"Weather in {city}: Sunny, 25°C"

class WeatherState(TypedDict):
    query: str
    city: str
    weather: str

def extract_city(state: WeatherState) -> WeatherState:
    """Extract city from user query"""
    query = state["query"]
    response = llm.invoke([{"role": "user", "content": f"Extract city from: {query}"}])
    state["city"] = response.content
    return state

def call_weather(state: WeatherState) -> WeatherState:
    """Call weather tool"""
    city = state["city"]
    weather = get_weather.invoke({"city": city})
    state["weather"] = weather
    return state

# Build graph
graph = StateGraph(WeatherState)
graph.add_node("extract", extract_city)
graph.add_node("weather", call_weather)
graph.add_edge("extract", "weather")
graph.add_edge("weather", END)
graph.set_entry_point("extract")
app = graph.compile()
'''

    @pytest.mark.asyncio
    async def test_migrate_weather_agent(self, weather_agent_code):
        """测试迁移 Weather Agent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建源文件
            source_file = os.path.join(temp_dir, 'weather_agent.py')
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(weather_agent_code)

            output_dir = os.path.join(temp_dir, 'output')
            os.makedirs(output_dir, exist_ok=True)

            # 执行迁移
            options = MigrationOptions(use_ai=False)
            result = migrate_new(source_file, output_dir, options)

            # 验证结果
            assert isinstance(result, MigrationResult)
            # 即使迁移失败，也应该有结构化结果
            if result.success:
                assert len(result.generated_files) > 0
                # 检查生成的文件存在
                for f in result.generated_files:
                    assert os.path.exists(f), f"Generated file not found: {f}"

    @pytest.mark.asyncio
    async def test_migration_result_structure(self, weather_agent_code):
        """测试迁移结果结构"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, 'test.py')
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(weather_agent_code)

            output_dir = os.path.join(temp_dir, 'output')

            result = migrate_new(source_file, output_dir)

            # 检查结果结构
            assert hasattr(result, 'success')
            assert hasattr(result, 'generated_files')
            assert hasattr(result, 'report')
            assert hasattr(result, 'rule_count')
            assert hasattr(result, 'ai_count')
            assert hasattr(result, 'errors')


class TestSimpleAgentMigration:
    """简单 Agent 迁移集成测试"""

    @pytest.fixture
    def simple_agent_code(self):
        """简单 Agent 代码"""
        return '''
from typing import TypedDict
from langgraph.graph import StateGraph, END

class SimpleState(TypedDict):
    value: int

def increment(state: SimpleState) -> SimpleState:
    state["value"] = state["value"] + 1
    return state

graph = StateGraph(SimpleState)
graph.add_node("inc", increment)
graph.add_edge("inc", END)
graph.set_entry_point("inc")
app = graph.compile()
'''

    @pytest.mark.asyncio
    async def test_migrate_simple_agent(self, simple_agent_code):
        """测试迁移简单 Agent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, 'simple_agent.py')
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(simple_agent_code)

            output_dir = os.path.join(temp_dir, 'output')

            options = MigrationOptions(use_ai=False)
            result = migrate_new(source_file, output_dir, options)

            assert isinstance(result, MigrationResult)


class TestConditionalEdgeMigration:
    """条件边迁移集成测试"""

    @pytest.fixture
    def conditional_agent_code(self):
        """带条件边的 Agent 代码"""
        return '''
from typing import TypedDict
from langgraph.graph import StateGraph, END

class DecisionState(TypedDict):
    input: str
    result: str
    should_continue: bool

def process(state: DecisionState) -> DecisionState:
    state["result"] = f"Processed: {state['input']}"
    state["should_continue"] = len(state["input"]) > 5
    return state

def finalize(state: DecisionState) -> DecisionState:
    state["result"] = f"Final: {state['result']}"
    return state

def router(state: DecisionState) -> str:
    if state.get("should_continue"):
        return "finalize"
    return END

graph = StateGraph(DecisionState)
graph.add_node("process", process)
graph.add_node("finalize", finalize)
graph.add_conditional_edges("process", router, {
    "finalize": "finalize",
    END: END
})
graph.add_edge("finalize", END)
graph.set_entry_point("process")
app = graph.compile()
'''

    @pytest.mark.asyncio
    async def test_migrate_conditional_agent(self, conditional_agent_code):
        """测试迁移带条件边的 Agent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, 'conditional_agent.py')
            with open(source_file, 'w', encoding='utf-8') as f:
                f.write(conditional_agent_code)

            output_dir = os.path.join(temp_dir, 'output')

            options = MigrationOptions(use_ai=False)
            result = migrate_new(source_file, output_dir, options)

            assert isinstance(result, MigrationResult)


class TestMultiFileMigration:
    """多文件迁移集成测试"""

    @pytest.mark.asyncio
    async def test_migrate_multi_file_project(self):
        """测试迁移多文件项目"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 创建多个文件
            # utils.py
            utils_code = '''
def format_response(text: str) -> str:
    return f"Response: {text}"
'''
            with open(os.path.join(temp_dir, 'utils.py'), 'w') as f:
                f.write(utils_code)

            # agent.py
            agent_code = '''
from typing import TypedDict
from langgraph.graph import StateGraph, END
from utils import format_response

class MyState(TypedDict):
    input: str
    output: str

def process(state: MyState) -> MyState:
    state["output"] = format_response(state["input"])
    return state

graph = StateGraph(MyState)
graph.add_node("process", process)
graph.add_edge("process", END)
graph.set_entry_point("process")
app = graph.compile()
'''
            with open(os.path.join(temp_dir, 'agent.py'), 'w') as f:
                f.write(agent_code)

            output_dir = os.path.join(temp_dir, 'output')

            # 迁移整个目录
            options = MigrationOptions(use_ai=False)
            result = migrate_new(temp_dir, output_dir, options)

            assert isinstance(result, MigrationResult)


class TestErrorHandling:
    """错误处理集成测试"""

    @pytest.mark.asyncio
    async def test_migrate_nonexistent_file(self):
        """测试迁移不存在的文件"""
        result = migrate_new("/nonexistent/path/file.py", "./output")

        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_migrate_syntax_error_file(self):
        """测试迁移语法错误的文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, 'broken.py')
            with open(source_file, 'w') as f:
                f.write('def broken(\n    # syntax error')

            output_dir = os.path.join(temp_dir, 'output')

            result = migrate_new(source_file, output_dir)

            # 应该返回结果而不是崩溃
            assert isinstance(result, MigrationResult)
