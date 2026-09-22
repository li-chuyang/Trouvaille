# CLI_DESIGN.md

## 状态

当前处于 MVP 阶段。

CLI 视觉设计暂时不定稿。

## 当前规则

MVP 阶段只要求：

- CLI 能正常交互
- User / Agent / Tool / Error 信息可区分
- 输出清晰
- CLI presentation 与 Agent Core 分离

## 当前不要自行决定

Codex 不要自行决定最终：

- 项目 Logo
- ASCII banner
- FIGlet 字体
- 主色
- 辅助色
- prompt 符号
- tool status icon
- 分隔线风格
- spinner
- panel
- welcome screen

这些由我后续亲自指定。

## 临时表现

如果需要最小展示：

```text
User >
Agent >
Tool >
Result >
```

或使用非常简单的 Rich 样式即可。

不要做复杂 TUI。

## 后续我会在这里补充

未来可能包含：

```text
Project name:
Logo:
Banner:
Primary color:
Secondary color:
Muted color:
Success color:
Error color:
Warning color:
User prompt:
Tool rendering:
Final answer rendering:
Separator style:
Spinner:
Welcome screen:
```

只有当这些内容被我明确填写后，再按照本文件实现最终 CLI 视觉。
