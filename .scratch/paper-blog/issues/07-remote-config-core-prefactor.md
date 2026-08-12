# 07 — 远程配置核心预重构

**What to build:**
无用户可见变化的公共地基。把 `cmd_remote_config` 中「预览 → 确认 → origin 失配 → 保存 → 绑定」段抽为共享 `_confirm_and_save_remote`（`_pause` 移到调用方统一收尾）；新增 `_prompt`（带 EOF/KeyboardInterrupt 守卫的输入）、`_open_browser`（通用浏览器打开，`_open_preview_browser` 改为委托它）、`_remote_configured`（已配置谓词，与菜单描述/分发共用）。为向导（08）与管理入口（09）提供公共部件。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] 抽出 `_confirm_and_save_remote`，`paper config` 远程流程行为不变
- [x] 新增 `_prompt` / `_open_browser` / `_remote_configured`
- [x] 现有 35 个测试全绿（无行为变化）
