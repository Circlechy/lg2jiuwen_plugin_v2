# LG2Jiuwen 迁移报告

**生成时间**: 2026-01-24 18:05:13

## 概览

- **Agent 名称**: Agent
- **节点数量**: 2
- **边数量**: 2
- **工具数量**: 1

## 转换统计

| 指标 | 数量 |
|------|------|
| 规则处理 | 2 |
| AI 处理 | 0 |
| 总节点数 | 2 |
| 总边数 | 2 |
| 总工具数 | 1 |

## 节点详情

| 节点名 | 类名 | 输入 | 输出 | 转换来源 |
|--------|------|------|------|----------|
| extract | ExtractComp | sentence | error, date, city | rule |
| call_weather | CallWeatherComp | date, city | error, weather | rule |

## 边详情

| 源节点 | 目标节点 | 类型 |
|--------|----------|------|
| extract | (路由: extract_router) | 条件 |
| call_weather | end | 普通 |

## 工具详情

| 工具名 | 描述 |
|--------|------|
| get_weather | 按城市+自然语言日期查天气（使用心知天气API） |

## 生成的文件

- `../example/jiuwen_weather_agent/agent_openjiuwen.py`
- `../example/jiuwen_weather_agent/agent_ir.json`

---
*由 LG2Jiuwen 自动生成*