# 09 — 已配置：内联管理入口

**What to build:**
回头客进「GitHub 远程」（已配置）不见向导，而是状态一行（`owner/repo` · 部署就绪 · Pages 地址）+ 内联提示：输入 `open` 打开 GitHub Pages 设置页 / 输入新地址修改远程 / 留空返回。删除被取代的 `cmd_remote_config`（由共享 `_confirm_and_save_remote` 承接保存逻辑）。

**Blocked by:** 08 — 未配置：引导式 GitHub Pages 发布向导

**Status:** ready-for-agent

- [x] 管理入口三条路径：open 开设置页 / 新地址修改 / 留空返回
- [x] 已配置进入只打开 `settings/pages`，不弹 `github.com/new`
- [x] 失配测试在管理入口下仍通过（输入序列不变：拒绝不暂停、成功才暂停）
