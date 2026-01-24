"""
工作流构建
"""

from openjiuwen.core.workflow.base import Workflow
from openjiuwen.core.component.start_comp import Start
from openjiuwen.core.component.end_comp import End

from .components.think_comp import ThinkComp
from .components.select_tool_comp import SelectToolComp
from .components.judge_comp import JudgeComp
from .routers import judge_router


def build_agent_workflow() -> Workflow:
    """构建 Agent 工作流"""

    workflow = Workflow()

    # 设置起点
    workflow.set_start_comp("start", Start(), inputs_schema={
        "input": "${input}",
        "is_end": "${is_end}",
        "loop_count": "${loop_count}",
    })

    # 添加组件
    workflow.add_workflow_comp(
        "think",
        ThinkComp(),
        inputs_schema={"input": "${start.input}", "loop_count": "${start.loop_count}"}
    )

    workflow.add_workflow_comp(
        "select_tool",
        SelectToolComp(),
        inputs_schema={"tool_input": "${think.tool_input}", "selected_tool": "${think.selected_tool}"}
    )

    workflow.add_workflow_comp(
        "judge",
        JudgeComp(),
        inputs_schema={"input": "${start.input}", "result": "${select_tool.result}", "selected_tool": "${think.selected_tool}"}
    )

    # 设置终点
    workflow.set_end_comp("end", End(), inputs_schema={"thought": "${think.thought}", "loop_count": "${think.loop_count}", "tool_input": "${think.tool_input}", "selected_tool": "${think.selected_tool}", "result": "${select_tool.result}", "reason": "${judge.reason}", "is_end": "${judge.is_end}"})

    # 添加连接
    workflow.add_connection("start", "think")
    workflow.add_connection("think", "select_tool")
    workflow.add_connection("select_tool", "judge")
    workflow.add_conditional_connection("judge", judge_router)

    return workflow