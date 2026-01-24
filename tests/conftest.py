"""
Pytest 配置和共享 fixtures
"""
import os
import sys
import tempfile
import pytest

# 添加 src 目录到 Python 路径
src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


@pytest.fixture
def temp_python_file():
    """创建临时 Python 文件的 fixture"""
    temp_files = []

    def _create_temp_file(content: str, suffix: str = '.py'):
        f = tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, mode='w', encoding='utf-8'
        )
        f.write(content)
        f.close()
        temp_files.append(f.name)
        return f.name

    yield _create_temp_file

    # 清理临时文件
    for f in temp_files:
        if os.path.exists(f):
            os.unlink(f)


@pytest.fixture
def temp_project_dir():
    """创建临时项目目录的 fixture"""
    temp_dirs = []

    def _create_temp_dir():
        d = tempfile.mkdtemp()
        temp_dirs.append(d)
        return d

    yield _create_temp_dir

    # 清理临时目录
    import shutil
    for d in temp_dirs:
        if os.path.exists(d):
            shutil.rmtree(d)


@pytest.fixture
def sample_langgraph_code():
    """示例 LangGraph 代码"""
    return '''
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    messages: list
    result: str

def process_node(state: AgentState) -> AgentState:
    messages = state["messages"]
    result = llm.invoke(messages)
    state["result"] = result.content
    return state

def should_continue(state: AgentState) -> str:
    if state.get("error"):
        return END
    return "next_node"

# 构建图
graph = StateGraph(AgentState)
graph.add_node("process", process_node)
graph.add_conditional_edges("process", should_continue, {
    END: END,
    "next_node": "next"
})
graph.set_entry_point("process")
app = graph.compile()
'''


@pytest.fixture
def sample_weather_agent_code():
    """示例 Weather Agent 代码"""
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
    query = state["query"]
    response = llm.invoke([{"role": "user", "content": f"Extract city from: {query}"}])
    state["city"] = response.content
    return state

def call_weather(state: WeatherState) -> WeatherState:
    city = state["city"]
    weather = get_weather.invoke({"city": city})
    state["weather"] = weather
    return state

graph = StateGraph(WeatherState)
graph.add_node("extract", extract_city)
graph.add_node("weather", call_weather)
graph.add_edge("extract", "weather")
graph.add_edge("weather", END)
graph.set_entry_point("extract")
app = graph.compile()
'''


@pytest.fixture
def mock_runtime():
    """模拟 WorkflowRuntime"""
    class MockRuntime:
        def __init__(self):
            self._state = {}

        def get_global_state(self, key: str):
            return self._state.get(key)

        def set_global_state(self, key: str, value):
            self._state[key] = value

    return MockRuntime()


@pytest.fixture
def mock_context():
    """模拟 ComponentContext"""
    class MockContext:
        def __init__(self):
            self.data = {}

    return MockContext()
