# 06 — paper config 软件自动扫描与 paper uninstall 一键自灭卸载

**What to build:**
实现 `detect_installed_editors()` 扫描 Mac 上安装的 Markdown 编辑器（VS Code, Typora, Obsidian, Cursor, iA Writer, MacDown, Vim）并增加 `(已安装)` 标记；实现 `paper uninstall` 命令，自动擦除配置/缓存，并在内部触发 `brew uninstall paper` 自我抹除，保全用户 Markdown 笔记。

**Blocked by:** 05 — gh-pages 分支零配置自动部署流与 repoDir 隔离

**Status:** ready-for-agent

- [x] 实现 `paper config editor` 自动软体扫描与设置
- [x] 实现 `paper uninstall` 自灭擦除与 `brew uninstall` 触发
- [x] 更新 `Formula/paper.rb` caveats 双重提示
