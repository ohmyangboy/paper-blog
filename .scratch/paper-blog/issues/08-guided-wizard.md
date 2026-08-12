# 08 — 未配置：引导式 GitHub Pages 发布向导

**What to build:**
首次用户触发「GitHub 远程」（未配置）即进入 4 步引导：① 自动打开 `https://github.com/new` 并打印仓库命名规则（`用户名.github.io` → 根路径，其它名 → `/仓库名`）→ ② 粘贴仓库地址（SSH / HTTPS / `owner/repo` 简写）→ ③ 核对 owner/repo/预期 Pages URL 确认保存 + 绑定 origin（origin 失配需输入 YES）→ ④ 自动打开 GitHub Pages 设置页并提示先 `paper publish` 推送 gh-pages。已配置时暂回落到现有直接流程（由 09 替换）。`cmd_config` 菜单描述按状态分流（未配置 → 「未配置 · 引导创建仓库」）。core 给 `GitRemoteInfo` 加 `pages_settings_url` 属性。所有步骤可 Esc / EOF / 留空 / 非空取消，不留半截配置。

**Blocked by:** 07 — 远程配置核心预重构

**Status:** ready-for-agent

- [x] 向导 4 步端到端：浏览器依次打开 `github.com/new` 与 `settings/pages`，配置保存 + origin 绑定
- [x] git 缺失 → 提示安装，配置不变，浏览器不打开
- [x] 地址非法 → 错误提示并重输，最终保存成功
- [x] 菜单描述分流 + 旧端到端测试改走向导序列
