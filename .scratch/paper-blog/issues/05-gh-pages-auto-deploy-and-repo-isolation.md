# 05 — gh-pages 分支零配置自动部署流与 repoDir 隔离

**What to build:**
实现 `auto_git_deploy` 部署引擎，在 `paper publish` 重新生成静态 HTML 后自动执行 `git subtree push --prefix out origin gh-pages` 零配置部署上线，并隔离用户 Markdown 笔记库与系统默认托管在 `~/.paper/site` 的 Git 博客部署库。

**Blocked by:** 04 — Mole CLI 风格 TUI 终端多选与 paper list 工作台

**Status:** ready-for-agent

- [x] 实现隐藏托管部署库 `~/.paper/site` 与 `gitRemote` 绑定
- [x] 实现 `git subtree push` 自动化静默分发
- [x] 无 Git / 无 Remote 场景下的优雅平滑回退
