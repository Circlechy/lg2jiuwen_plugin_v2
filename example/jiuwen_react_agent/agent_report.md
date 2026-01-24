# LG2Jiuwen 迁移报告

**生成时间**: 2026-01-24 17:54:02

## 概览

- **Agent 名称**: Agent
- **节点数量**: 3
- **边数量**: 3
- **工具数量**: 2

## 转换统计

| 指标 | 数量 |
|------|------|
| 规则处理 | 3 |
| AI 处理 | 0 |
| 总节点数 | 3 |
| 总边数 | 3 |
| 总工具数 | 2 |

## 节点详情

| 节点名 | 类名 | 输入 | 输出 | 转换来源 |
|--------|------|------|------|----------|
| think | ThinkComp | input, loop_count | thought, loop_count, tool_input, selected_tool | rule |
| select_tool | SelectToolComp | tool_input, selected_tool | result | rule |
| judge | JudgeComp | input, result, selected_tool | reason, is_end | rule |

## 边详情

| 源节点 | 目标节点 | 类型 |
|--------|----------|------|
| think | select_tool | 普通 |
| select_tool | judge | 普通 |
| judge | (路由: judge_router) | 条件 |

## 工具详情

| 工具名 | 描述 |
|--------|------|
| calculator | 用于数学加减乘除计算 |
| weather | 按城市+自然语言日期查天气（使用心知天气API） |

## 生成的文件

- `../example/jiuwen_react_agent/agent/__init__.py`
- `../example/jiuwen_react_agent/agent/config.py`
- `../example/jiuwen_react_agent/agent/tools.py`
- `../example/jiuwen_react_agent/agent/components/__init__.py`
- `../example/jiuwen_react_agent/agent/components/think_comp.py`
- `../example/jiuwen_react_agent/agent/components/select_tool_comp.py`
- `../example/jiuwen_react_agent/agent/components/judge_comp.py`
- `../example/jiuwen_react_agent/agent/routers.py`
- `../example/jiuwen_react_agent/agent/workflow.py`
- `../example/jiuwen_react_agent/agent/main.py`
- `../example/jiuwen_react_agent/agent_ir.json`

---
*由 LG2Jiuwen 自动生成*