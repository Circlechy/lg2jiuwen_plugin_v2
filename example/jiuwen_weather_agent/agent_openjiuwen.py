"""
Agent - 由 LG2Jiuwen 自动迁移生成
"""

import httpx
import os
import asyncio
from typing import Any, Dict, List, Optional

from openjiuwen.core.workflow.base import Workflow
from openjiuwen.core.component.start_comp import Start
from openjiuwen.core.component.end_comp import End
from openjiuwen.core.component.base import WorkflowComponent
from openjiuwen.core.runtime.base import ComponentExecutable, Input, Output
from openjiuwen.core.runtime.runtime import Runtime
from openjiuwen.core.runtime.workflow import WorkflowRuntime
from openjiuwen.core.context_engine.base import Context
from openjiuwen.core.utils.llm.model_library.openai import OpenAIChatModel
from openjiuwen.core.utils.tool.param import Param
from openjiuwen.core.utils.tool.tool import tool
os.environ['LLM_SSL_VERIFY'] = 'false'

SENIVERSE_API_KEY = 'SBM-NCypTmfxznW6X'


@tool(
    name="get_weather",
    description="按城市+自然语言日期查天气（使用心知天气API）",
    params=[
        Param(name="city", description="city", type="string", required=True),
        Param(name="date", description="date", type="string", required=True)
    ]
)
def get_weather(city: str, date: str) -> str:
    """按城市+自然语言日期查天气（使用心知天气API）"""
    day_index = {'今天': 0, '明天': 1, '后天': 2}.get(date, 0)
    url = f'https://api.seniverse.com/v3/weather/daily.json?key={SENIVERSE_API_KEY}&location={city}&language=zh-Hans&unit=c&start={day_index}&days=1'
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        result = data['results'][0]
        location = result['location']['name']
        daily = result['daily'][0]
        return f'{location} {daily['date']}: {daily['low']}~{daily['high']}°C, 白天{daily['text_day']}, 夜间{daily['text_night']}'
    except httpx.HTTPStatusError as e:
        return f'天气服务异常：HTTP {e.response.status_code}'
    except (KeyError, IndexError) as e:
        return f'天气数据解析异常：{e}'
    except Exception as e:
        return f'天气服务异常：{e}'


class ExtractComp(WorkflowComponent, ComponentExecutable):
    """LLM 提取 city & date，缺一个就报错"""

    def __init__(self, llm=None):
        if llm:
            self._llm = llm
        else:
            self._llm = OpenAIChatModel(
                api_key="a2143076169049208e54a83c9900d084.xyq9uiIZxK9AwWx3",
                api_base="https://open.bigmodel.cn/api/paas/v4/"
            )
        self.model_name = "glm-4-flash"

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        # 初始化输出变量
        error = None
        date = None
        city = None
        # 组件逻辑（转换来源: rule）
        sys_prompt = '用户会输入一句话，请提取“城市”和“日期”。\n日期可以是：今天、明天、后天 等。\n如果城市或日期缺失，请只返回 ERROR: 缺失城市 或 ERROR: 缺失日期，不要多余文字。\n否则返回 JSON: {"city": "城市", "date": "日期"}'
        messages = [{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': runtime.get_global_state("sentence")}]
        ans = ((await self._llm.ainvoke(model_name=self.model_name, messages=messages)).content).strip()
        print('llm ans:', ans)
        try:
            import json
            obj = json.loads(ans)
            city = obj['city']
            date = obj['date']
        except Exception:
            error = ans
        return {"error": error, "date": date, "city": city}


class CallWeatherComp(WorkflowComponent, ComponentExecutable):
    """直接调用天气工具获取结果"""

    def __init__(self):
        pass

    async def invoke(
        self,
        inputs: Input,
        runtime: Runtime,
        context: Context
    ) -> Output:
        # 初始化输出变量
        error = None
        weather = None
        # 组件逻辑（转换来源: rule）
        city = inputs.get('city')
        date = inputs.get('date')
        if not city or not date:
            error = '缺少城市或日期参数'
            return {"error": error, "weather": weather}
        result = get_weather.invoke(inputs={"city": city, "date": date})
        print('weather result:', result)
        weather = result
        return {"error": error, "weather": weather}


def extract_router(runtime: WorkflowRuntime) -> str:
    """路由函数：根据 extract 的输出决定下一个节点"""
    return "end" if runtime.get_global_state("extract.error") else "call_weather"


def build_agent_workflow() -> Workflow:
    """构建 Agent 工作流"""

    workflow = Workflow()

    # 设置起点
    workflow.set_start_comp("start", Start(), inputs_schema={
        "sentence": "${sentence}",
    })

    # 添加组件
    workflow.add_workflow_comp(
        "extract",
        ExtractComp(),
        inputs_schema={"sentence": "${start.sentence}"}
    )

    workflow.add_workflow_comp(
        "call_weather",
        CallWeatherComp(),
        inputs_schema={"date": "${extract.date}", "city": "${extract.city}"}
    )

    # 设置终点
    workflow.set_end_comp("end", End(), inputs_schema={"error": "${extract.error}", "date": "${extract.date}", "city": "${extract.city}", "weather": "${call_weather.weather}"})

    # 添加连接
    workflow.add_connection("start", "extract")
    workflow.add_conditional_connection("extract", extract_router)
    workflow.add_connection("call_weather", "end")

    return workflow


async def main():
    """主函数"""
    workflow = build_agent_workflow()
    runtime = WorkflowRuntime()

    # 示例输入
    inputs = {
        "sentence": '明天天气'
    }

    result = await workflow.invoke(inputs, runtime)
    print("执行结果:", result)


if __name__ == "__main__":
    asyncio.run(main())