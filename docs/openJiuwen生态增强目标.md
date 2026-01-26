# openJiuwen 生态增强目标

## 背景

基于 LangGraph 与 openJiuwen 的功能对比分析，识别出 openJiuwen 在以下方面存在差距。本文档制定相应的改进目标。

---

## 差异分析

| 功能 | LangGraph | openJiuwen | 差距说明 |
|------|-----------|------------|----------|
| 中断恢复 | ✅ | ✅ | 无差距 |
| 流式输出 | ✅ | ✅ | 无差距 |
| 多 Agent 协作 | ✅ | ✅ | 无差距 |
| Prompt 优化 | ✅ | ✅ | 无差距 |
| 工作流可视化 | ✅ | ✅ (静态) | 无差距 |
| **Time Travel 调试** | ✅ | ❌ | 缺少从任意检查点重启、回放、fork 分支 |
| **持久化 Checkpointer** | ✅ (多后端) | ❌ (内存) | 缺少工作流状态数据库持久化 |
| **可视化调试 IDE** | ✅ (Studio) | ❌ | 缺少交互式调试界面 |
| **托管云服务** | ✅ (Cloud) | ❌ | 缺少官方托管部署方案 |
| **LangChain 工具兼容** | ✅ | ❌ | 缺少 LangChain 工具适配层 |

---

## 改进目标

### 目标 1：持久化 Checkpointer 体系

**描述**：实现可插拔的工作流状态持久化机制，支持 Redis、PostgreSQL 等后端，使 Agent 状态可跨进程/服务恢复。

**核心能力**：
- 工作流每步执行后自动保存状态到数据库
- 服务重启后可从数据库恢复会话状态
- 支持多种存储后端（Redis、PostgreSQL、MySQL）

**价值**：生产环境必备，支持故障容错、服务重启后恢复会话。

---

### 目标 2：Time Travel 调试能力

**描述**：基于 Checkpointer，支持从任意历史检查点重启执行、回放步骤、fork 分支探索不同路径。

**核心能力**：
- 列出执行历史中的所有检查点
- 从指定检查点重启执行（不从头开始）
- Fork 分支：从某检查点创建新分支，探索不同路径
- 编辑中间状态后继续执行

**价值**：大幅提升复杂 Agent 的调试效率，快速定位问题节点。

**依赖**：目标 1（持久化 Checkpointer）

---

### 目标 3：可视化调试工具

**描述**：Web 界面实时展示执行轨迹、节点输入输出、支持断点和状态编辑等，并支持声明式 YAML/JSON 工作流定义。

**核心能力**：
- 支持用 YAML/JSON 配置文件定义工作流结构，实现"低代码"编排
- 查看每个节点的输入、输出、耗时、token 消耗
- 支持设置断点、暂停执行
- 支持编辑中间状态后继续
- 集成 Time Travel 功能

**价值**：降低调试门槛，让非开发人员也能理解 Agent 行为。

**依赖**：目标 2（Time Travel）

---

### 目标 4：LangChain 工具适配层

**描述**：提供适配器，让 LangChain 生态的 `@tool` 工具可直接在 openJiuwen 中使用。

**核心能力**：
- 自动识别 LangChain 的 `@tool` 装饰器
- 将 LangChain Tool 转换为 openJiuwen Tool
- 兼容 LangChain 的参数定义和返回格式

**价值**：复用 LangChain 丰富的工具生态（搜索、数据库、API 等），降低迁移成本。

---

### 目标 5：一键部署能力

**描述**：提供 Docker 镜像 + Helm Chart，支持快速部署到 K8s，包含 API 网关、监控、日志。

**核心能力**：
- 官方 Docker 镜像
- Kubernetes Helm Chart
- 集成 Prometheus 监控 + Grafana 面板
- 集成日志收集（ELK/Loki）
- API 网关配置模板

**价值**：缩短从开发到生产的路径，降低运维成本。

---

## 优先级规划

| 优先级 | 目标 | 理由 |
|--------|------|------|
| **P0** | 持久化 Checkpointer | 生产环境基础设施，其他目标的前置依赖 |
| **P1** | Time Travel 调试 | 依赖 Checkpointer，调试刚需 |
| **P1** | LangChain 工具适配 | 快速扩充工具生态，无依赖 |
| **P2** | 可视化调试工具 | 依赖 Time Travel，提升体验 |
| **P2** | 一键部署 | 运维便利，可后期补齐 |

---

## 目标依赖关系

```
                    ┌─────────────────────┐
                    │  持久化 Checkpointer │ (P0)
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Time Travel 调试   │ (P1)
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  可视化调试工具      │ (P2)
                    └─────────────────────┘

┌─────────────────────┐         ┌─────────────────────┐
│ LangChain 工具适配  │ (P1)    │    一键部署能力     │ (P2)
│   （无依赖）        │         │    （无依赖）       │
└─────────────────────┘         └─────────────────────┘
```

---

## 参考资料

- [LangGraph Cloud 发布公告](https://blog.langchain.com/langgraph-cloud/)
- [LangGraph v0.2 Checkpointer](https://www.blog.langchain.com/langgraph-v0-2/)
- [LangGraph Persistence 文档](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Time Travel 教程](https://www.marktechpost.com/2025/08/31/how-to-build-a-conversational-research-ai-agent-with-langgraph-step-replay-and-time-travel-checkpoints/)
