# 10 — 引导向导代码审查延迟项（Follow-ups）

**What to build:**
08/09 代码审查（双轴：Standards + Spec）确认功能达标（US61/63、ID117/118 通过），但留下五项规模性/设计性发现未在本轮修复。本 ticket 记录这些延迟项，供后续独立排期 —— 每项都足够大，不该塞进向导功能的收尾提交。

**Blocked by:** None — can start immediately（各项彼此独立）

**Status:** ready-for-agent

- [ ] **PTY 测试缝（spec L131/L124/L123）**：`tests/test_paper_cli.py` 的 `GitHubRemoteConfigTests` 全用 `mock.patch("builtins.input")` + `mock.patch("paper_cli._terminal_menu")` 驱动，spec 要求主 CLI 缝是真实 PTY（launch `paper`、发方向键/Esc/Q/Ctrl+C、检查退出码与终端协议）。这是整套既有测试套件未追随的书面标准，非向导功能新引入 —— 排期需决定是补一个真实 PTY 用例，还是修订 spec L131 让 mock 缝成为文档标准。

- [ ] **US62 首发自动测可达性**：向导只在入口查 git 是否安装，不测远程可达性；「测试连接」仍是 config 面板独立菜单项。spec L86 要求"test Git availability and remote accessibility before the first publish"。需在发布路径（`cmd_deploy`/`cmd_publish`）加首次发布前的可达性探测，或明确裁剪 US62 的可达性部分。

- [ ] **L155 五态完整呈现**：`_deployment_readiness` 只返回 4 个粗态，"push failed" 与 "pushed awaiting Pages" 仅在 `cmd_status` 的 `_refine_pushed_state` 区分；config 面板「GitHub 远程」管理入口标签一律显示"已推送"。且当前 `_deployment_readiness` 仅凭本地 `refs/heads/gh-pages` 存在即标"已推送"，`git subtree push` 失败时会误标 —— 与 L155 要求区分 push failed 冲突。

- [ ] **SSH/HTTPS 归一化策略**：`normalize_git_remote` 把 HTTPS 输入也存成 `git@github.com:…`，测试连接与 origin 绑定均用 SSH 形式。US58 声称支持既有认证方式，但纯 HTTPS 凭据助手的用户会被引导到 SSH 认证。需决定是否保存 HTTPS 原文（保持 ssh_url 用于 Pages URL 推导），或文档声明以 SSH 为首选认证方式。

- [ ] **命名与 `GitRemoteInfo.full_name`**：`cmd_remote_wizard` 函数名与"🧭 向导"文案与 spec L154"not as a separate wizard"字面冲突（功能上仍是 config 面板内引导流程，属判断性轻微项）；CLI 内联 `f"{remote_info.owner}/{remote_info.repo}"` 可做成 `GitRemoteInfo.full_name` 属性，让 CLI 少碰内部字段。
