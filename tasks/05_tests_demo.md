# Phase 05 — Tests + Demo

## 目标

不再扩功能。

把 MVP 收干净，形成第一版可展示项目。

## Test review

重点测试：

- workspace path safety
- file tools
- shell
- registry
- agent direct answer
- multi-step tool loop
- tool error recovery
- max_steps
- config

## Demo

准备独立 demo workspace。

至少展示：

```text
用户提出小 coding task
→ Agent 查看文件
→ 读代码
→ 修改
→ 运行验证
→ git diff
→ final answer
```

## README

至少包含：

- 项目是什么
- 为什么自己实现 Agent Core
- 当前架构
- 支持的 tools
- 安装
- 配置
- 使用
- demo
- 当前限制
- future work

不要吹嘘未实现功能。

## Architecture review

检查：

- Agent 是否强耦合 provider
- CLI 是否耦合 core
- Tools 是否可独立测试
- workspace state 是否清楚
- messages ownership 是否清楚
- 是否过度抽象

## Cleanup

检查：

- 未使用依赖
- `.env`
- cache
- trajectory 临时文件
- `.gitignore`

## MVP Freeze

Phase 05 完成后冻结基础功能。

后续增强另行讨论。

完成后停止。
