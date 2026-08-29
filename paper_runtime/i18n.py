"""Internationalization (i18n) module for Paper CLI and runtime."""

from __future__ import annotations

import locale
import os
from typing import Any

SUPPORTED_LANGUAGES = ["zh_CN", "en_US"]
DEFAULT_FALLBACK_LANGUAGE = "en_US"

LANGUAGE_LABELS = {
    "zh_CN": "简体中文",
    "en_US": "English",
}

_current_language: str = "zh_CN"


def normalize_locale(code: str | None) -> str:
    """Normalize locale string or alias into supported language code ('zh_CN' or 'en_US')."""
    if not code:
        return DEFAULT_FALLBACK_LANGUAGE

    clean = code.strip().lower().replace("-", "_")
    if clean in {"auto", "default", "system"}:
        return detect_system_language()

    if clean.startswith("zh"):
        return "zh_CN"
    if clean.startswith("en"):
        return "en_US"

    return DEFAULT_FALLBACK_LANGUAGE


def detect_system_language() -> str:
    """Detect language from environment variables or system locale."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            val_clean = val.strip().lower()
            if val_clean.startswith("zh"):
                return "zh_CN"
            if val_clean.startswith("en"):
                return "en_US"

    try:
        sys_loc, _ = locale.getlocale()
        if sys_loc:
            sys_clean = sys_loc.strip().lower()
            if sys_clean.startswith("zh"):
                return "zh_CN"
            if sys_clean.startswith("en"):
                return "en_US"
    except Exception:
        pass

    try:
        def_loc, _ = locale.getdefaultlocale()
        if def_loc:
            def_clean = def_loc.strip().lower()
            if def_clean.startswith("zh"):
                return "zh_CN"
            if def_clean.startswith("en"):
                return "en_US"
    except Exception:
        pass

    return DEFAULT_FALLBACK_LANGUAGE


def resolve_language(
    config_lang: str | None = None,
    cli_lang: str | None = None,
) -> str:
    """Resolve the effective language following priority:
    1. Explicit CLI argument (--lang)
    2. Environment variable PAPER_LANG
    3. Configuration file (language)
    4. Auto-detected system locale (LC_ALL / LANG / getlocale)
    5. Fallback to en_US
    """
    if cli_lang:
        return normalize_locale(cli_lang)

    env_lang = os.environ.get("PAPER_LANG")
    if env_lang:
        return normalize_locale(env_lang)

    if config_lang and config_lang.strip().lower() not in {"auto", "system", ""}:
        return normalize_locale(config_lang)

    return detect_system_language()


def set_current_language(lang: str) -> str:
    """Set the active language for the current process."""
    global _current_language
    _current_language = normalize_locale(lang)
    return _current_language


def get_current_language() -> str:
    """Get the active language code."""
    return _current_language


class override_language:
    """Context manager to temporarily override active language."""

    def __init__(self, lang: str):
        self.new_lang = lang
        self.old_lang = get_current_language()

    def __enter__(self):
        set_current_language(self.new_lang)
        return self.new_lang

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        set_current_language(self.old_lang)


TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── General / Navigation ──
    "yes": {
        "zh_CN": "是",
        "en_US": "Yes",
    },
    "no": {
        "zh_CN": "否",
        "en_US": "No",
    },
    "cancel": {
        "zh_CN": "取消",
        "en_US": "Cancel",
    },
    "back": {
        "zh_CN": "返回",
        "en_US": "Back",
    },
    "continue": {
        "zh_CN": "继续",
        "en_US": "Continue",
    },
    "skip": {
        "zh_CN": "跳过",
        "en_US": "Skip",
    },
    "press_enter_to_continue": {
        "zh_CN": "按回车键继续……",
        "en_US": "Press Enter to continue...",
    },
    "press_esc_to_return": {
        "zh_CN": "按 Esc 或 Q 返回上一级",
        "en_US": "Press Esc or Q to go back",
    },
    "press_esc_to_exit": {
        "zh_CN": "再按一次 Esc 或 Q 退出 Paper",
        "en_US": "Press Esc or Q again to exit Paper",
    },
    "exit_goodbye": {
        "zh_CN": "\n已退出 Paper。再见！\n",
        "en_US": "\nExited Paper. Goodbye!\n",
    },
    "menu_controls_hint": {
        "zh_CN": "↑↓ / kj  |  enter 选择  |  数字键直达  |  esc / q 返回",
        "en_US": "↑↓ / kj  |  Enter to select  |  Number keys  |  Esc / Q to return",
    },
    "menu_multiselect_controls": {
        "zh_CN": "空格勾选  |  ↑↓ / kj 移动  |  enter 提交  |  esc / q 取消",
        "en_US": "Space to toggle  |  ↑↓ / kj to move  |  Enter to submit  |  Esc / Q to cancel",
    },
    "menu_more_above": {
        "zh_CN": "  ↑ 还有 {count} 项",
        "en_US": "  ↑ {count} more items",
    },
    "menu_more_below": {
        "zh_CN": "  ↓ 还有 {count} 项",
        "en_US": "  ↓ {count} more items",
    },
    "pause_prompt": {
        "zh_CN": "\n按 Enter 返回菜单……",
        "en_US": "\nPress Enter to return to menu...",
    },
    "error_not_linked": {
        "zh_CN": "尚未关联 Markdown 目录。请先执行 paper link，或使用 paper init 创建标准目录。",
        "en_US": "No Markdown posts directory linked. Run `paper link` or `paper init` first.",
    },
    "update_notice_banner": {
        "zh_CN": "🆕 Paper {latest} 新版本可用，请使用 `paper update` 命令升级。",
        "en_US": "🆕 Paper {latest} is available, run `paper update` to upgrade.",
    },

    # ── Dashboard ──
    "dashboard_mode_prefix": {
        "zh_CN": "【当前目录模式：{dir_name}】\n",
        "en_US": "[Directory Mode: {dir_name}]\n",
    },
    "dashboard_prompt": {
        "zh_CN": "请使用方向键导航，Enter 或数字键选择对应的功能：",
        "en_US": "Use arrow keys to navigate, Enter or number keys to select:",
    },
    "menu_list": {
        "zh_CN": "管理文章",
        "en_US": "Manage posts",
    },
    "menu_new": {
        "zh_CN": "新建文章并打开编辑器",
        "en_US": "Create post and open editor",
    },
    "menu_config": {
        "zh_CN": "设置路径、编辑器与品牌",
        "en_US": "Configure path, editor, and brand",
    },
    "menu_publish": {
        "zh_CN": "选择草稿并发布",
        "en_US": "Select drafts to publish",
    },
    "menu_serve": {
        "zh_CN": "启动本地热更新预览",
        "en_US": "Start local live preview",
    },
    "menu_uninstall": {
        "zh_CN": "卸载与清理配置，保留原稿",
        "en_US": "Uninstall and clean configuration (keep drafts)",
    },
    "menu_quit": {
        "zh_CN": "退出 Paper",
        "en_US": "Exit Paper",
    },

    # ── Posts & List ──
    "posts_title": {
        "zh_CN": "文章列表",
        "en_US": "Posts",
    },
    "posts_empty": {
        "zh_CN": "（暂无文章）",
        "en_US": "(No posts found)",
    },
    "tag_published": {
        "zh_CN": "已发布",
        "en_US": "Published",
    },
    "tag_draft": {
        "zh_CN": "草稿",
        "en_US": "Draft",
    },
    "action_new_post": {
        "zh_CN": "➕ 新建文章",
        "en_US": "➕ New post",
    },
    "action_filter_all": {
        "zh_CN": "全部",
        "en_US": "All",
    },
    "action_filter_published": {
        "zh_CN": "已发布",
        "en_US": "Published",
    },
    "action_filter_drafts": {
        "zh_CN": "草稿",
        "en_US": "Drafts",
    },
    "post_operation_title": {
        "zh_CN": "操作文章：{title}",
        "en_US": "Post: {title}",
    },
    "post_op_edit": {
        "zh_CN": "在编辑器中打开",
        "en_US": "Open in editor",
    },
    "post_op_publish": {
        "zh_CN": "发布此草稿",
        "en_US": "Publish this draft",
    },
    "post_op_unpublish": {
        "zh_CN": "撤回为草稿",
        "en_US": "Revert to draft",
    },
    "post_op_delete": {
        "zh_CN": "删除文章",
        "en_US": "Delete post",
    },
    "post_delete_confirm": {
        "zh_CN": "确定要删除文章《{title}》吗？文件将被永久删除！",
        "en_US": "Are you sure you want to delete '{title}'? The file will be permanently deleted!",
    },
    "post_deleted": {
        "zh_CN": "✅ 已删除文章：{path}",
        "en_US": "✅ Deleted post: {path}",
    },
    "list_console_header": {
        "zh_CN": "📄 Paper 文章控制台（🟢 已上线　⚪ 草稿或已下线）",
        "en_US": "📄 Paper Posts Console (🟢 Published  ⚪ Draft)",
    },
    "list_home_tag": {
        "zh_CN": "（首页）",
        "en_US": " (Homepage)",
    },
    "list_home_op_title": {
        "zh_CN": "首页操作：{title}",
        "en_US": "Homepage: {title}",
    },
    "list_home_op_edit": {
        "zh_CN": "编辑首页",
        "en_US": "Edit homepage",
    },
    "list_home_op_edit_desc": {
        "zh_CN": "使用默认编辑器打开 index.md",
        "en_US": "Open index.md in default editor",
    },
    "list_post_op_edit_desc": {
        "zh_CN": "使用默认编辑器打开 Markdown",
        "en_US": "Open Markdown in default editor",
    },
    "list_post_op_publish": {
        "zh_CN": "发布",
        "en_US": "Publish",
    },
    "list_post_op_archive": {
        "zh_CN": "下架",
        "en_US": "Unpublish",
    },
    "list_post_op_rebuild_desc": {
        "zh_CN": "重新构建站点",
        "en_US": "Rebuild static site",
    },
    "list_post_op_delete_desc": {
        "zh_CN": "移动到废纸篓，可恢复",
        "en_US": "Move to Trash (recoverable)",
    },
    "list_post_archived": {
        "zh_CN": "✅ 已下架：{title}",
        "en_US": "✅ Unpublished: {title}",
    },
    "list_post_delete_confirm_prompt": {
        "zh_CN": "将《{title}》移动到废纸篓？按 Enter 确认删除（输入任意内容取消）：",
        "en_US": "Move '{title}' to Trash? Press Enter to confirm (type anything to cancel):",
    },
    "list_post_trash_moved": {
        "zh_CN": "✅ 已移动到废纸篓：{target}",
        "en_US": "✅ Moved to Trash: {target}",
    },

    # ── New Post ──
    "new_post_prompt": {
        "zh_CN": "文章标题：",
        "en_US": "Post title: ",
    },
    "new_post_title_empty": {
        "zh_CN": "标题不能为空",
        "en_US": "Title cannot be empty",
    },
    "new_post_title_newline": {
        "zh_CN": "标题不能包含换行",
        "en_US": "Title cannot contain newlines",
    },
    "new_post_created": {
        "zh_CN": "✅ 已创建草稿：{path}",
        "en_US": "✅ Draft created: {path}",
    },
    "new_post_exists": {
        "zh_CN": "文章已存在：{filename}",
        "en_US": "Post already exists: {filename}",
    },
    "new_post_noninteractive": {
        "zh_CN": "非交互环境必须传入标题，例如 paper new 'Hello Paper'",
        "en_US": "Title argument required in non-interactive mode, e.g. paper new 'Hello Paper'",
    },
    "new_post_cancelled": {
        "zh_CN": "已取消新建",
        "en_US": "Post creation cancelled",
    },

    # ── Publish ──
    "publish_no_drafts": {
        "zh_CN": "没有需要首次发布的草稿，已重新生成静态站点。",
        "en_US": "No drafts to publish for the first time. Static site regenerated.",
    },
    "publish_select_prompt": {
        "zh_CN": "选择要发布的草稿（Space 选中/取消，Enter 确认）：",
        "en_US": "Select drafts to publish (Space to toggle, Enter to confirm):",
    },
    "publish_action_publish": {
        "zh_CN": "发布选中文章",
        "en_US": "Publish selected posts",
    },
    "publish_action_all": {
        "zh_CN": "发布全部草稿",
        "en_US": "Publish all drafts",
    },
    "publish_marked_count": {
        "zh_CN": "已将 {count} 篇草稿标记为已发布。",
        "en_US": "Marked {count} draft(s) as published.",
    },
    "publish_success": {
        "zh_CN": "✅ 发布成功！",
        "en_US": "✅ Published successfully!",
    },
    "publish_multiselect_title": {
        "zh_CN": "🚀 勾选要发布的草稿（不勾选直接 Enter 仅重新构建并同步网站）：",
        "en_US": "🚀 Select drafts to publish (Press Enter without selection to just rebuild and sync site):",
    },
    "publish_cancelled": {
        "zh_CN": "已取消发布。",
        "en_US": "Publish cancelled.",
    },
    "publish_rebuilding": {
        "zh_CN": "正在构建站点 ……",
        "en_US": "Building site...",
    },
    "publish_failed_reverted": {
        "zh_CN": "构建失败，已恢复原稿状态：{error}",
        "en_US": "Build failed, drafts reverted: {error}",
    },
    "publish_missing_posts": {
        "zh_CN": "没有找到文章：{missing}。可用文章：{available}",
        "en_US": "Posts not found: {missing}. Available posts: {available}",
    },

    # ── Build & Serve ──
    "build_generated": {
        "zh_CN": "✅ 已生成静态站点：{path}",
        "en_US": "✅ Static site generated: {path}",
    },
    "serve_preview_header": {
        "zh_CN": "Paper 本地实时预览",
        "en_US": "Paper Local Live Preview",
    },
    "serve_watching": {
        "zh_CN": "正在监听文章目录变更：{path}",
        "en_US": "Watching posts directory for changes: {path}",
    },
    "serve_reloaded": {
        "zh_CN": "\n↻ Markdown 修改已合并更新，浏览器即将自动刷新。\n",
        "en_US": "\n↻ Markdown updated, refreshing browser...\n",
    },
    "serve_rebuild_failed": {
        "zh_CN": "\n⚠️ 预览重建失败，继续保留上一次结果：{exc}",
        "en_US": "\n⚠️ Preview rebuild failed, keeping last good output: {exc}",
    },
    "serve_address": {
        "zh_CN": "本地地址：http://localhost:{port}/",
        "en_US": "Local URL: http://localhost:{port}/",
    },
    "serve_stop_hint": {
        "zh_CN": "按 Ctrl+C 停止服务",
        "en_US": "Press Ctrl+C to stop preview",
    },
    "serve_port_occupied": {
        "zh_CN": "⚠️ 端口 {port} 已被占用，已改用随机端口。",
        "en_US": "⚠️ Port {port} is occupied, switched to a random port.",
    },
    "serve_banner": {
        "zh_CN": "🌐 Paper 预览（包含草稿，仅本机可访问）：{url}",
        "en_US": "🌐 Paper Preview (includes drafts, localhost only): {url}",
    },
    "serve_browser_opened": {
        "zh_CN": "已在默认浏览器中打开。",
        "en_US": "Opened in default browser.",
    },
    "serve_browser_failed": {
        "zh_CN": "未能自动打开浏览器，请复制上方地址。",
        "en_US": "Could not open browser automatically, please copy the URL above.",
    },
    "serve_stopped_hint": {
        "zh_CN": "\n已停止预览。",
        "en_US": "\nPreview stopped.",
    },

    # ── Link ──
    "link_linked": {
        "zh_CN": "✅ 已关联文章目录：{path}",
        "en_US": "✅ Linked posts directory: {path}",
    },
    "link_prompt": {
        "zh_CN": "文章目录绝对路径（留空取消）：",
        "en_US": "Absolute path to posts directory (leave blank to cancel):",
    },
    "link_noninteractive_error": {
        "zh_CN": "非交互环境必须传入文章目录，例如 paper link ~/Documents/Paper/posts",
        "en_US": "Posts directory argument required in non-interactive mode, e.g. paper link ~/Documents/Paper/posts",
    },
    "link_cancelled": {
        "zh_CN": "已取消关联",
        "en_US": "Link cancelled",
    },
    "link_not_found": {
        "zh_CN": "目录不存在：{path}",
        "en_US": "Directory does not exist: {path}",
    },
    "link_not_dir": {
        "zh_CN": "路径不是目录：{path}",
        "en_US": "Path is not a directory: {path}",
    },

    # ── Init ──
    "init_already": {
        "zh_CN": "当前目录已存在 Paper 配置：{path}",
        "en_US": "Paper configuration already exists in current directory: {path}",
    },
    "init_created": {
        "zh_CN": "✅ 已在当前目录初始化 Paper 博客：{path}",
        "en_US": "✅ Initialized Paper blog in current directory: {path}",
    },
    "init_welcome_header": {
        "zh_CN": "📖 欢迎使用 Paper 博客系统初始化向导",
        "en_US": "📖 Welcome to Paper Blog Initialization Wizard",
    },
    "init_mode_choose": {
        "zh_CN": "请选择博客初始化模式：",
        "en_US": "Please choose initialization mode:",
    },
    "init_mode_global": {
        "zh_CN": "全局模式（推荐：随时随地输入 paper 写作，文章存于统一文档库，全局托管）",
        "en_US": "Global Mode (Recommended: write anywhere with paper, posts in unified folder)",
    },
    "init_mode_local": {
        "zh_CN": "当前目录模式（项目工程：基于当前目录生成 .paper-config.json，文章保存在 ./posts）",
        "en_US": "Local Directory Mode (Project mode: generates .paper-config.json, posts in ./posts)",
    },
    "init_detected_existing": {
        "zh_CN": "\n💡 检测到该环境已初始化过 Paper：",
        "en_US": "\n💡 Detected existing Paper environment:",
    },
    "init_mode_label_local": {
        "zh_CN": "当前目录模式",
        "en_US": "Local Directory Mode",
    },
    "init_mode_label_global": {
        "zh_CN": "全局模式",
        "en_US": "Global Mode",
    },
    "init_posts_count": {
        "zh_CN": "已有 {count} 篇文章",
        "en_US": "{count} post(s)",
    },
    "init_action_choose": {
        "zh_CN": "请选择接下来的操作：",
        "en_US": "Please choose next action:",
    },
    "init_op_serve": {
        "zh_CN": "🚀 启动本地热更新预览（paper serve）",
        "en_US": "🚀 Start local live preview (paper serve)",
    },
    "init_op_new": {
        "zh_CN": "📝 新建文章草稿并在编辑器打开（paper new）",
        "en_US": "📝 Create draft and open editor (paper new)",
    },
    "init_op_reinit": {
        "zh_CN": "🔄 重新运行初始化向导（更新配置与关联）",
        "en_US": "🔄 Re-run initialization wizard (update configuration)",
    },
    "init_op_exit": {
        "zh_CN": "🚪 退出",
        "en_US": "🚪 Exit",
    },
    "init_exited": {
        "zh_CN": "已退出。",
        "en_US": "Exited.",
    },
    "init_cancelled": {
        "zh_CN": "已取消初始化。",
        "en_US": "Initialization cancelled.",
    },
    "init_confirm_path_prompt": {
        "zh_CN": "\n📁 请确认文章保存路径 [默认: {path}]（直接 Enter 确认）：",
        "en_US": "\n📁 Confirm posts directory [Default: {path}] (Press Enter to confirm):",
    },
    "init_posts_ready": {
        "zh_CN": "✅ 文章库已就绪：{path}",
        "en_US": "✅ Posts directory ready: {path}",
    },
    "init_choose_editor": {
        "zh_CN": "✍️ 请选择常用写作编辑器（当前: {editor}）：",
        "en_US": "✍️ Select writing editor (Current: {editor}):",
    },
    "init_auto_linked_remote": {
        "zh_CN": "🔗 已自动关联 Git 远程仓库：{remote}",
        "en_US": "🔗 Auto-linked Git remote: {remote}",
    },
    "init_pages_url": {
        "zh_CN": "🌐 站点 Pages 地址：{url}",
        "en_US": "🌐 Site Pages URL: {url}",
    },
    "init_remote_prompt": {
        "zh_CN": "🔗 配置 GitHub 远程仓库（例如 git@github.com:username/blog.git，直接 Enter 跳过）：",
        "en_US": "🔗 Configure GitHub remote (e.g. git@github.com:user/blog.git, Enter to skip):",
    },
    "init_remote_invalid": {
        "zh_CN": "⚠️ 仓库地址格式无法识别，已跳过关联，后续可在设置中随时配置。",
        "en_US": "⚠️ Unrecognized repository address, skipped. Can configure in settings later.",
    },
    "init_building_site": {
        "zh_CN": "正在进行首次站点构建 ……",
        "en_US": "Building site for the first time...",
    },
    "init_build_done": {
        "zh_CN": "✅ 站点初始构建完成！产物输出目录：{path}",
        "en_US": "✅ Initial build complete! Output directory: {path}",
    },
    "init_build_hint": {
        "zh_CN": "⚠️ 初始构建提示：{error}",
        "en_US": "⚠️ Initial build note: {error}",
    },
    "init_done_title": {
        "zh_CN": "\n🎉 Paper 初始化全部就绪！请选择接下来的操作：",
        "en_US": "\n🎉 Paper initialization complete! Choose next action:",
    },
    "init_done_serve": {
        "zh_CN": "🚀 启动本地热更新预览（在浏览器查看博客效果）",
        "en_US": "🚀 Start local live preview in browser",
    },
    "init_done_publish": {
        "zh_CN": "🌐 立即同步发布到 GitHub Pages",
        "en_US": "🌐 Publish to GitHub Pages now",
    },
    "init_done_exit": {
        "zh_CN": "🚪 完成并退出",
        "en_US": "🚪 Done and exit",
    },
    "init_quick_start_title": {
        "zh_CN": "\n💡 常用命令指引：",
        "en_US": "\n💡 Quick Commands Guide:",
    },

    # ── Editor ──
    "editor_set": {
        "zh_CN": "✅ 默认编辑器已设置为：{editor}",
        "en_US": "✅ Default editor set to: {editor}",
    },
    "editor_picker_title": {
        "zh_CN": "选择新建文章后自动打开的编辑器：",
        "en_US": "Choose editor to open when creating posts:",
    },
    "editor_custom_input": {
        "zh_CN": "编辑器应用路径或启动命令（留空取消）：",
        "en_US": "Editor application path or command (leave blank to cancel):",
    },
    "editor_custom_invalid": {
        "zh_CN": "无法执行指定的编辑器命令：{cmd}",
        "en_US": "Cannot execute specified editor command: {cmd}",
    },
    "editor_default_system": {
        "zh_CN": "macOS 默认 Markdown 应用",
        "en_US": "macOS default Markdown application",
    },
    "editor_custom_option": {
        "zh_CN": "选择其他应用（打开文件管理器）",
        "en_US": "Choose another application (open file picker)",
    },
    "editor_installed": {
        "zh_CN": "已安装",
        "en_US": "Installed",
    },
    "editor_not_detected": {
        "zh_CN": "未检测到",
        "en_US": "Not detected",
    },
    "choose_posts_folder_prompt": {
        "zh_CN": "选择 Paper 文章目录",
        "en_US": "Choose Paper posts directory",
    },
    "choose_favicon_prompt": {
        "zh_CN": "选择 Paper 网站图标",
        "en_US": "Choose Paper website icon",
    },
    "choose_editor_app_prompt": {
        "zh_CN": "选择用于打开 Markdown 文章的编辑器应用",
        "en_US": "Choose editor application for opening Markdown",
    },

    # ── Remote & Deploy Wizard ──
    "wizard_step1_title": {
        "zh_CN": "创建仓库",
        "en_US": "Create repository",
    },
    "wizard_step1_desc": {
        "zh_CN": "已为你打开 GitHub 新建仓库页，在浏览器里新建一个仓库。\n· 仓库名决定博客地址：用户名.github.io → 根路径；其它 → /仓库名 子路径\n· 可见性选 Public；已有仓库可跳过本步，直接粘贴地址。",
        "en_US": "Opened GitHub new repo page in browser.\n· Repo name determines blog URL: user.github.io -> root; others -> /repo subpath\n· Select Public; skip if you already have a repository.",
    },
    "wizard_step2_title": {
        "zh_CN": "粘贴地址",
        "en_US": "Paste address",
    },
    "wizard_step2_desc": {
        "zh_CN": "支持三种写法（任选其一）：\ngit@github.com:用户名/仓库.git\nhttps://github.com/用户名/仓库\n用户名/仓库",
        "en_US": "Supports 3 formats (choose any):\ngit@github.com:user/repo.git\nhttps://github.com/user/repo\nuser/repo",
    },
    "wizard_step3_title": {
        "zh_CN": "核对保存",
        "en_US": "Verify & save",
    },
    "wizard_step3_desc": {
        "zh_CN": "保存后发布将推送到该仓库。请核对：\n仓库所有者：{owner}\n仓库名称：{repo}\nRemote URL：{url}\n预期 Pages URL：{pages_url}",
        "en_US": "Publishing will push to this repo. Please verify:\nOwner: {owner}\nRepository: {repo}\nRemote URL: {url}\nExpected Pages URL: {pages_url}",
    },
    "wizard_step4_title": {
        "zh_CN": "发布开启",
        "en_US": "Publish & enable",
    },
    "wizard_step4_desc": {
        "zh_CN": "gh-pages 分支要等你发布之后才存在，所以顺序是：先发布，再开启 Pages。",
        "en_US": "The gh-pages branch exists only after publishing: publish first, then enable Pages.",
    },
    "wizard_pushed_gh_pages": {
        "zh_CN": "✅ 已推送 gh-pages —— 设置页里现在可以选到它了。",
        "en_US": "✅ Pushed gh-pages branch -- now selectable in settings.",
    },
    "wizard_skipped_publish": {
        "zh_CN": "⏭ 已跳过发布。之后执行 paper publish，推送 gh-pages 后再来开启 Pages。",
        "en_US": "⏭ Skipped publish. Run paper publish later and push gh-pages before enabling Pages.",
    },
    "wizard_settings_page_open": {
        "zh_CN": "设置页：{url}\n已为你打开设置页。\n⚠️ 若下拉框里没有 gh-pages，说明还没推送成功 —— 稍后执行 paper publish 再回来刷新。",
        "en_US": "Settings: {url}\nOpened settings in browser.\n⚠️ If gh-pages is not listed, publish has not succeeded yet -- run paper publish later and refresh.",
    },
    "wizard_settings_skipped": {
        "zh_CN": "设置页：{url}\n⏭ 已跳过。发布后打开上面的设置页，在「Deploy from a branch」选 gh-pages 并保存。",
        "en_US": "Settings: {url}\n⏭ Skipped. After publishing, open settings and select gh-pages under 'Deploy from a branch'.",
    },
    "wizard_done": {
        "zh_CN": "✅ 配置完成。之后用 paper publish 发布，用 paper serve 本地预览。",
        "en_US": "✅ Setup complete. Use paper publish to deploy and paper serve to preview.",
    },
    "wizard_open_create_page": {
        "zh_CN": "打开 GitHub 新建仓库页",
        "en_US": "Open GitHub new repository page",
    },
    "wizard_skip_to_paste": {
        "zh_CN": "跳过，直接粘贴已有仓库地址",
        "en_US": "Skip, directly paste existing repo URL",
    },
    "wizard_enter_remote_prompt": {
        "zh_CN": "  仓库地址（留空取消）：",
        "en_US": "  Repository address (leave blank to cancel):",
    },
    "wizard_remote_invalid": {
        "zh_CN": "无法识别的 GitHub 仓库地址，请参考上面的三种写法重新输入",
        "en_US": "Unrecognized GitHub repository address, please refer to the 3 formats above and re-enter",
    },
    "remote_saved": {
        "zh_CN": "✅ 已保存 GitHub 远程：{remote}\n   预期站点：{site_url}",
        "en_US": "✅ Saved GitHub remote: {remote}\n   Expected site: {site_url}",
    },
    "deploy_staging": {
        "zh_CN": "  · 暂存并检查站点更新……",
        "en_US": "  · Staging and checking site updates...",
    },
    "deploy_committing": {
        "zh_CN": "  · 提交站点更新……",
        "en_US": "  · Committing site updates...",
    },
    "deploy_pushing": {
        "zh_CN": "  · 正在推送 gh-pages 到 {remote} ……\n    （这一步需要联网上传，首次或网络较慢时可能要等几十秒到几分钟）",
        "en_US": "  · Pushing gh-pages to {remote} ...\n    (Network upload required, may take several seconds to minutes)",
    },
    "deploy_success": {
        "zh_CN": "✅ 已推送 gh-pages；GitHub Pages 可能仍需数分钟完成构建。",
        "en_US": "✅ Pushed gh-pages; GitHub Pages may take a few minutes to build.",
    },
    "deploy_actions_notice": {
        "zh_CN": "ℹ️ 检测到仓库已配置 GitHub Actions Pages 工作流；将通过源码分支触发部署。",
        "en_US": "ℹ️ GitHub Actions Pages workflow detected; deploy will trigger from source branch.",
    },

    # ── Test Connection ──
    "test_testing_git": {
        "zh_CN": "正在测试 Git 运行环境……",
        "en_US": "Testing Git runtime environment...",
    },
    "test_testing_remote": {
        "zh_CN": "正在测试远程仓库连接：{remote} ……",
        "en_US": "Testing remote connection: {remote} ...",
    },
    "test_remote_ok": {
        "zh_CN": "✅ 远程仓库连接正常！",
        "en_US": "✅ Remote connection is normal!",
    },
    "test_remote_failed": {
        "zh_CN": "❌ 远程仓库连接失败：{error}",
        "en_US": "❌ Remote connection failed: {error}",
    },

    # ── Pages URL & Custom Domain ──
    "pages_url_prompt": {
        "zh_CN": "自定义站点地址（留空清除自定义，恢复自动推导）：",
        "en_US": "Custom site URL (leave blank to restore auto derived):",
    },
    "pages_url_set": {
        "zh_CN": "✅ 站点 URL 已设置为：{url}",
        "en_US": "✅ Site URL set to: {url}",
    },

    # ── Brand Config ──
    "brand_menu_title": {
        "zh_CN": "🏠 Home · 首页与品牌\n（使用 ↑/↓ 移动，enter 确认，esc 返回上一级）",
        "en_US": "🏠 Home · Homepage & Brand\n(Use ↑/↓ to move, Enter to confirm, Esc to return)",
    },
    "brand_current_color": {
        "zh_CN": "当前 [{color}]",
        "en_US": "Current [{color}]",
    },
    "brand_icon_desc": {
        "zh_CN": "{icon_label} / 文件 / 粘贴代码",
        "en_US": "{icon_label} / File / Paste code",
    },
    "brand_icon_zine": {
        "zh_CN": "Paper zine 图标",
        "en_US": "Paper zine icon",
    },
    "brand_icon_customized": {
        "zh_CN": "已自定义",
        "en_US": "Customized",
    },
    "brand_back_to_config": {
        "zh_CN": "返回配置上级",
        "en_US": "Back to configuration",
    },
    "brand_item_color": {
        "zh_CN": "高亮颜色 (color)",
        "en_US": "Highlight Color (color)",
    },
    "brand_item_icon": {
        "zh_CN": "网站图标 (icon)",
        "en_US": "Brand Icon (icon)",
    },
    "brand_color_prompt": {
        "zh_CN": "高亮颜色 HEX（当前 {color}）：",
        "en_US": "Highlight color HEX (Current: {color}):",
    },
    "brand_color_set": {
        "zh_CN": "✅ 主题颜色已设置为：{color}",
        "en_US": "✅ Theme color set to: {color}",
    },
    "brand_color_hex_error": {
        "zh_CN": "颜色必须是 #D97757 这样的六位 HEX",
        "en_US": "Color must be a 6-character HEX code like #D97757",
    },
    "brand_icon_source_title": {
        "zh_CN": "选择网站品牌图标来源：",
        "en_US": "Select brand icon source:",
    },
    "brand_icon_opt_default": {
        "zh_CN": "恢复 Paper 默认 favicon",
        "en_US": "Restore Paper default favicon",
    },
    "brand_icon_opt_file": {
        "zh_CN": "复制到文章目录 assets/",
        "en_US": "Copy to posts directory assets/",
    },
    "brand_icon_opt_paste": {
        "zh_CN": "直接保存图标代码",
        "en_US": "Paste and save icon code",
    },
    "brand_icon_opt_back": {
        "zh_CN": "不修改",
        "en_US": "Do not modify",
    },
    "brand_icon_file_prompt": {
        "zh_CN": "图标文件路径（留空取消）：",
        "en_US": "Icon file path (leave blank to cancel):",
    },
    "brand_icon_paste_prompt": {
        "zh_CN": "粘贴一行 SVG、Data URI 或图片 URL：",
        "en_US": "Paste a single line of SVG, Data URI, or image URL:",
    },
    "brand_icon_unrecognized": {
        "zh_CN": "无法识别图标内容",
        "en_US": "Unrecognized icon content",
    },
    "favicon_invalid_format": {
        "zh_CN": "图标文件必须是 SVG、PNG、JPG、WebP 或 ICO",
        "en_US": "Icon file must be SVG, PNG, JPG, WebP, or ICO",
    },
    "brand_icon_prompt": {
        "zh_CN": "选择网站品牌图标来源：",
        "en_US": "Choose brand icon source:",
    },
    "brand_icon_set": {
        "zh_CN": "✅ 品牌图标已设置。",
        "en_US": "✅ Brand icon updated.",
    },

    # ── Compression ──
    "compress_menu_title": {
        "zh_CN": "选择构建图片压缩：",
        "en_US": "Select output image compression:",
    },
    "compress_opt_on": {
        "zh_CN": "开启（默认）· 优化发布副本，不修改原图",
        "en_US": "Enable (Default) · Optimize build output, preserve originals",
    },
    "compress_opt_off": {
        "zh_CN": "关闭 · 发布副本保持原始大小",
        "en_US": "Disable · Keep original file size for build output",
    },
    "compress_feedback": {
        "zh_CN": "✅ 图片压缩已{state}。",
        "en_US": "✅ Image compression is now {state}.",
    },
    "compress_set": {
        "zh_CN": "✅ 图片压缩已设置为：{state}",
        "en_US": "✅ Image compression set to: {state}",
    },
    "state_on": {
        "zh_CN": "开启",
        "en_US": "Enabled",
    },
    "state_off": {
        "zh_CN": "关闭",
        "en_US": "Disabled",
    },

    # ── Language Config ──
    "lang_menu_title": {
        "zh_CN": "选择界面语言 (Language)：",
        "en_US": "Select Interface Language:",
    },
    "lang_option_zh": {
        "zh_CN": "🇨🇳 简体中文 (zh_CN)",
        "en_US": "🇨🇳 简体中文 (zh_CN)",
    },
    "lang_option_en": {
        "zh_CN": "🇺🇸 English (en_US)",
        "en_US": "🇺🇸 English (en_US)",
    },
    "lang_option_auto": {
        "zh_CN": "🌐 跟随系统 / 自动检测 (Auto)",
        "en_US": "🌐 System / Auto-detect (Auto)",
    },
    "lang_set": {
        "zh_CN": "✅ 界面语言已设置为：{lang}",
        "en_US": "✅ Interface language set to: {lang}",
    },

    # ── Deployment Readiness ──
    "readiness_actions": {
        "zh_CN": "GitHub Actions 自动构建",
        "en_US": "GitHub Actions automated build",
    },
    "readiness_not_configured": {
        "zh_CN": "未配置",
        "en_US": "Not configured",
    },
    "readiness_unverified": {
        "zh_CN": "未校验",
        "en_US": "Unverified",
    },
    "readiness_pushed": {
        "zh_CN": "已推送",
        "en_US": "Pushed",
    },
    "readiness_ready": {
        "zh_CN": "已就绪",
        "en_US": "Ready",
    },

    # ── Wizard Stepper & Panels ──
    "wizard_step1_name": {
        "zh_CN": "创建仓库",
        "en_US": "Create Repo",
    },
    "wizard_step2_name": {
        "zh_CN": "粘贴地址",
        "en_US": "Paste URL",
    },
    "wizard_step3_name": {
        "zh_CN": "核对保存",
        "en_US": "Verify & Save",
    },
    "wizard_step4_name": {
        "zh_CN": "发布开启",
        "en_US": "Publish & Enable",
    },
    "wizard_git_missing_error": {
        "zh_CN": "未找到 Git。请先安装 Git（macOS：brew install git），再来配置 GitHub 远程。",
        "en_US": "Git not found. Please install Git (macOS: brew install git) before configuring GitHub remote.",
    },
    "wizard_step1_bound": {
        "zh_CN": "当前已绑定：{owner}/{repo}",
        "en_US": "Currently bound: {owner}/{repo}",
    },
    "wizard_step1_bound_hint": {
        "zh_CN": "无需新建仓库，直接进入第 2 步粘贴新地址即可换绑。",
        "en_US": "No need to create a new repo; proceed to step 2 to paste a new URL.",
    },
    "wizard_step1_open_success": {
        "zh_CN": "已为你打开 GitHub 新建仓库页，在浏览器里新建一个仓库。",
        "en_US": "Opened GitHub new repository page in your browser.",
    },
    "wizard_step1_open_fail": {
        "zh_CN": "未能自动打开浏览器 —— 请手动打开 https://github.com/new 新建一个仓库。",
        "en_US": "Could not open browser automatically -- please open https://github.com/new manually.",
    },
    "wizard_step1_hint_subpath": {
        "zh_CN": "· 仓库名决定博客地址：用户名.github.io → 根路径；其它 → /仓库名 子路径",
        "en_US": "· Repo name determines URL: username.github.io -> root; other -> /repo subpath",
    },
    "wizard_step1_hint_public": {
        "zh_CN": "· 可见性选 Public；已有仓库可跳过本步，直接粘贴地址。",
        "en_US": "· Set visibility to Public; skip this step if you already have a repository.",
    },
    "wizard_step1_continue_prompt": {
        "zh_CN": "\n  按 Enter 继续 · 按 Space 跳过（已有仓库直接粘贴）：",
        "en_US": "\n  Press Enter to continue · Space to skip (paste existing repo):",
    },
    "wizard_step2_formats_hint": {
        "zh_CN": "支持三种写法（任选其一）：",
        "en_US": "Supports 3 formats (choose any):",
    },
    "wizard_verify_hint": {
        "zh_CN": "保存后发布将推送到该仓库。请核对：",
        "en_US": "Publishing will push to this repo. Please verify:",
    },
    "wizard_verify_owner": {
        "zh_CN": "仓库所有者：{owner}",
        "en_US": "Repo Owner: {owner}",
    },
    "wizard_verify_repo": {
        "zh_CN": "仓库名称：{repo}",
        "en_US": "Repo Name: {repo}",
    },
    "wizard_verify_remote": {
        "zh_CN": "Remote URL：{url}",
        "en_US": "Remote URL: {url}",
    },
    "wizard_verify_pages": {
        "zh_CN": "预期 Pages URL：{pages_url}",
        "en_US": "Expected Pages URL: {pages_url}",
    },
    "wizard_origin_mismatch_warning": {
        "zh_CN": "⚠️ 当前托管 origin：{origin}（与将要保存的不一致）",
        "en_US": "⚠️ Current managed origin: {origin} (differs from new setting)",
    },
    "wizard_confirm_save_prompt": {
        "zh_CN": "\n按 Enter 确认保存 · 按 Space 跳过：",
        "en_US": "\nPress Enter to confirm and save · Space to skip:",
    },
    "wizard_save_skipped": {
        "zh_CN": "  ⏭ 已跳过，未修改任何配置。",
        "en_US": "  ⏭ Skipped, no configuration modified.",
    },
    "wizard_replace_origin_prompt": {
        "zh_CN": "origin 不一致，输入 YES 替换托管仓库 origin（其他内容取消）：",
        "en_US": "Origin differs. Type YES to replace managed repo origin (anything else to cancel):",
    },
    "wizard_save_cancelled": {
        "zh_CN": "  ⏭ 已取消，未修改任何配置。",
        "en_US": "  ⏭ Cancelled, no configuration modified.",
    },
    "wizard_binding_origin_spinner": {
        "zh_CN": "正在绑定托管仓库 origin ……",
        "en_US": "Binding managed repository origin...",
    },
    "wizard_bind_origin_failed": {
        "zh_CN": "绑定托管仓库 origin 失败。",
        "en_US": "Failed to bind managed repository origin.",
    },
    "wizard_step4_publish_prompt": {
        "zh_CN": "\n  现在发布并推送 gh-pages 吗？按 Enter 发布 · 按 Space 跳过：",
        "en_US": "\n  Publish and push gh-pages now? Press Enter to publish · Space to skip:",
    },
    "wizard_step4_not_pushed_yet": {
        "zh_CN": "  ⚠️ 尚未推送 gh-pages（刚才可能没有勾选草稿）。",
        "en_US": "  ⚠️ gh-pages not pushed yet (no drafts may have been selected).",
    },
    "wizard_step4_push_all_prompt": {
        "zh_CN": "  要把当前站点（首页 + 已发布内容）先推上去吗？按 Enter 推送 · 按 Space 跳过：",
        "en_US": "  Push current site (homepage + published) now? Press Enter to push · Space to skip:",
    },
    "wizard_step4_pushed_ok": {
        "zh_CN": "  ✅ 已推送 gh-pages。",
        "en_US": "  ✅ Pushed gh-pages.",
    },
    "wizard_step4_push_failed": {
        "zh_CN": "  ⚠️ 推送未成功，稍后执行 paper publish 重试。",
        "en_US": "  ⚠️ Push failed. Run paper publish later to retry.",
    },
    "wizard_step4_open_settings_prompt": {
        "zh_CN": "  现在打开设置页选 gh-pages 吗？按 Enter 打开 · 按 Space 跳过：",
        "en_US": "  Open settings page now to select gh-pages? Press Enter to open · Space to skip:",
    },
    "wizard_settings_opened": {
        "zh_CN": "已为你打开设置页。",
        "en_US": "Opened settings page.",
    },
    "wizard_settings_open_fail": {
        "zh_CN": "未能自动打开设置页。",
        "en_US": "Could not open settings page automatically.",
    },
    "wizard_step4_settings_warning": {
        "zh_CN": "  ⚠️ 若下拉框里没有 gh-pages，说明还没推送成功 —— 稍后执行 paper publish 再回来刷新。",
        "en_US": "  ⚠️ If gh-pages is not in dropdown, push is not complete -- run paper publish later and refresh.",
    },

    # ── Config Menu ──
    "config_menu_title": {
        "zh_CN": "⚙️ Paper Config",
        "en_US": "⚙️ Paper Config",
    },
    "config_mode_prefix": {
        "zh_CN": "（当前目录模式：{dir_name}）",
        "en_US": " (Directory Mode: {dir_name})",
    },
    "config_current_editor": {
        "zh_CN": "当前 {editor}",
        "en_US": "Current: {editor}",
    },
    "config_current_language": {
        "zh_CN": "语言设置 · {lang}",
        "en_US": "Language · {lang}",
    },
    "config_remote_bound": {
        "zh_CN": "当前 {owner}/{repo} · 点入可重新绑定",
        "en_US": "Current {owner}/{repo} · Enter to re-bind",
    },
    "config_remote_not_configured": {
        "zh_CN": "未配置 · 引导创建仓库",
        "en_US": "Not configured · Guide to create repo",
    },
    "config_item_brand_desc": {
        "zh_CN": "高亮颜色 / Favicon 图标",
        "en_US": "Highlight Color / Favicon Icon",
    },
    "config_item_pages_desc": {
        "zh_CN": "Pages 地址 / 自定义域名",
        "en_US": "Pages URL / Custom Domain",
    },
    "config_item_test_desc": {
        "zh_CN": "检查 Git 与远程可达性",
        "en_US": "Check Git & Remote Reachability",
    },
    "config_item_status_desc": {
        "zh_CN": "路径 / 仓库 / 部署（{readiness}）",
        "en_US": "Path / Repo / Deploy ({readiness})",
    },
    "config_item_back": {
        "zh_CN": "返回主菜单",
        "en_US": "Return to main menu",
    },
    "config_unknown_subcmd": {
        "zh_CN": "未知的 config 子命令：{cmd}",
        "en_US": "Unknown config subcommand: {cmd}",
    },
    "config_item_link": {
        "zh_CN": "文章目录 (posts_dir)",
        "en_US": "Posts Directory (posts_dir)",
    },
    "config_item_editor": {
        "zh_CN": "默认编辑器",
        "en_US": "Default Editor",
    },
    "config_item_remote": {
        "zh_CN": "GitHub 远程向导 (remote)",
        "en_US": "GitHub Remote Wizard (remote)",
    },
    "config_item_pages": {
        "zh_CN": "Pages 地址 / 自定义域名 (pages)",
        "en_US": "Pages URL / Custom Domain (pages)",
    },
    "config_item_brand": {
        "zh_CN": "高亮颜色 / Favicon 图标",
        "en_US": "Highlight Color / Favicon Icon",
    },
    "config_item_compress": {
        "zh_CN": "图片压缩",
        "en_US": "Image Compression",
    },
    "config_item_language": {
        "zh_CN": "语言设置",
        "en_US": "Language Settings",
    },
    "config_item_test": {
        "zh_CN": "检查 Git 与远程可达性",
        "en_US": "Check Git & Remote Reachability",
    },
    "config_item_status": {
        "zh_CN": "查看完整状态 (status)",
        "en_US": "View Full Status (status)",
    },

    # ── Pages URL ──
    "pages_derived_url": {
        "zh_CN": "推导的 Pages 地址：{url}",
        "en_US": "Derived Pages URL: {url}",
    },
    "pages_need_remote": {
        "zh_CN": "（需先配置 GitHub 远程）",
        "en_US": "(Requires configuring GitHub remote first)",
    },
    "pages_current_site_url": {
        "zh_CN": "当前站点地址（siteUrl）：{url}",
        "en_US": "Current Site URL (siteUrl): {url}",
    },
    "pages_site_url_unset": {
        "zh_CN": "未设置 —— 构建时自动使用推导值",
        "en_US": "Not set -- auto-derived at build time",
    },
    "pages_custom_prompt": {
        "zh_CN": "自定义站点地址（留空清除自定义，恢复自动推导）：",
        "en_US": "Custom site URL (leave blank to restore auto-derived):",
    },
    "pages_cancelled": {
        "zh_CN": "已取消。",
        "en_US": "Cancelled.",
    },

    # ── Test Connection ──
    "test_git_missing": {
        "zh_CN": "系统未找到 Git。",
        "en_US": "Git not found on system.",
    },
    "test_remote_unconfigured": {
        "zh_CN": "尚未配置有效的 GitHub 远程，请先在「GitHub 远程」设置。",
        "en_US": "No valid GitHub remote configured. Please set up in GitHub Remote first.",
    },
    "test_testing_remote_prefix": {
        "zh_CN": "测试远程：{remote}",
        "en_US": "Testing remote: {remote}",
    },
    "test_connecting_spinner": {
        "zh_CN": "正在连接远程仓库 ……",
        "en_US": "Connecting to remote repository...",
    },
    "test_timeout_error": {
        "zh_CN": "连接超时（>10 秒）。请检查网络与 SSH 认证。",
        "en_US": "Connection timed out (>10s). Check network and SSH authentication.",
    },
    "test_remote_unreachable_error": {
        "zh_CN": "远程不可达或认证失败。",
        "en_US": "Remote unreachable or authentication failed.",
    },
    "test_connection_ok": {
        "zh_CN": "✅ Git 可用，远程仓库可达。",
        "en_US": "✅ Git is working and remote repository is reachable.",
    },

    # ── Deploy ──
    "deploy_actions_intro": {
        "zh_CN": "💡 检测到当前仓库已配置 GitHub Actions 自动化部署（.github/workflows/deploy.yml）。\n   本地静态输出已生成到 ./out。只需将代码变更推送到 GitHub 远程仓库，Actions 会自动构建上线：\n   git add . && git commit -m \"publish: update posts\" && git push\n",
        "en_US": "💡 Detected GitHub Actions automated deployment (.github/workflows/deploy.yml).\n   Static build generated to ./out. Push code changes to remote repo to trigger Actions deploy:\n   git add . && git commit -m \"publish: update posts\" && git push\n",
    },
    "deploy_actions_confirm_prompt": {
        "zh_CN": "🚀 按 Enter 立即执行提交并推送到 GitHub，按其他任意键取消：",
        "en_US": "🚀 Press Enter to commit and push to GitHub now, any other key to cancel:",
    },
    "deploy_actions_cancelled": {
        "zh_CN": "已取消自动推送。后续可手动推送更新。",
        "en_US": "Auto push cancelled. You can push manually later.",
    },
    "deploy_git_missing": {
        "zh_CN": "系统未找到 Git，无法自动推送。",
        "en_US": "Git not found, cannot auto push.",
    },
    "deploy_staging_local": {
        "zh_CN": "  · 暂存本地改动……",
        "en_US": "  · Staging local changes...",
    },
    "deploy_stage_failed": {
        "zh_CN": "无法暂存本地改动",
        "en_US": "Failed to stage local changes",
    },
    "deploy_committing_changes": {
        "zh_CN": "  · 提交变更……",
        "en_US": "  · Committing changes...",
    },
    "deploy_commit_failed": {
        "zh_CN": "Git commit 失败，请检查 Git 配置或 hooks。",
        "en_US": "Git commit failed. Check Git configuration or hooks.",
    },
    "deploy_pushing_remote_spinner": {
        "zh_CN": "正在上传到 GitHub ……",
        "en_US": "Uploading to GitHub...",
    },
    "deploy_push_timeout": {
        "zh_CN": "❌ 推送超时（10 分钟仍未完成）——通常是网络无法稳定连接 GitHub。",
        "en_US": "❌ Push timed out (10 minutes exceeded) -- usually network connectivity issues.",
    },
    "deploy_push_failed": {
        "zh_CN": "❌ 推送失败；本地提交已保留，可稍后重试。",
        "en_US": "❌ Push failed; local commit preserved, retry later.",
    },
    "deploy_actions_success": {
        "zh_CN": "✅ 已成功推送到 GitHub；GitHub Actions 正在云端构建并发布，预计数分钟内生效。",
        "en_US": "✅ Successfully pushed to GitHub; GitHub Actions is building, live in a few minutes.",
    },
    "deploy_remote_missing": {
        "zh_CN": "尚未配置 GitHub remote。请先在设置中配置 gitRemote。",
        "en_US": "No GitHub remote configured. Please configure gitRemote in settings first.",
    },
    "deploy_git_missing_keep_out": {
        "zh_CN": "系统未找到 Git，已保留本地静态输出。",
        "en_US": "Git not found. Local static output preserved.",
    },
    "deploy_init_failed": {
        "zh_CN": "无法初始化 Paper 托管仓库",
        "en_US": "Failed to initialize Paper managed repository",
    },
    "deploy_bind_remote_failed": {
        "zh_CN": "无法绑定 GitHub remote",
        "en_US": "Failed to bind GitHub remote",
    },
    "deploy_origin_mismatch": {
        "zh_CN": "托管仓库的 origin 与 Paper 配置不一致，请先确认 remote，避免推送到错误仓库。",
        "en_US": "Managed repo origin differs from Paper config. Verify remote to avoid pushing to wrong repository.",
    },
    "deploy_stage_out_failed": {
        "zh_CN": "无法暂存静态输出",
        "en_US": "Failed to stage static output",
    },
    "deploy_commit_site_failed": {
        "zh_CN": "Git commit 失败，请检查 user.name、user.email 或 hooks。",
        "en_US": "Git commit failed. Check user.name, user.email, or hooks.",
    },
    "deploy_diff_failed": {
        "zh_CN": "无法检查站点更新（git diff 失败）。",
        "en_US": "Failed to check site updates (git diff failed).",
    },
    "deploy_push_advice_timeout": {
        "zh_CN": "   建议：在配置面板「GitHub 远程 → 测试连接」检查连通性，网络恢复后执行 paper deploy 重试。",
        "en_US": "   Tip: Check connectivity in Config -> Test Connection, and retry with paper deploy when network recovers.",
    },
    "deploy_push_failed_retry_hint": {
        "zh_CN": "❌ GitHub Pages 推送失败；本地状态保留，可稍后执行 paper deploy 重试。",
        "en_US": "❌ GitHub Pages push failed; local state preserved, retry with paper deploy later.",
    },
    "deploy_push_common_reasons": {
        "zh_CN": "   常见原因：网络连不上 GitHub、SSH 密钥 / 个人访问令牌未配置或已失效、仓库地址填错。\n   建议：配置面板「GitHub 远程 → 测试连接」检查连通性，或 ssh -T git@github.com 验证认证。",
        "en_US": "   Common causes: Network issue, SSH key/token expired, or wrong repository URL.\n   Tip: Check connectivity in Config -> Test Connection, or verify with ssh -T git@github.com.",
    },

    # ── Status ──
    "status_actions_tip": {
        "zh_CN": "  当前项目已配置 GitHub Actions 自动构建，代码 push 到远程分支即可自动触发部署。",
        "en_US": "  This project has GitHub Actions automated deploy configured. Pushing code triggers build automatically.",
    },
    "status_pushed_unable_confirm": {
        "zh_CN": "  无法确认远程状态（可运行「测试连接」排查）。",
        "en_US": "  Unable to confirm remote status (run 'Test Connection' to diagnose).",
    },
    "status_pushed_ahead_retry": {
        "zh_CN": "  本地 gh-pages 领先远程，上次推送可能失败，可执行 paper deploy 重试。",
        "en_US": "  Local gh-pages is ahead of remote. Previous push may have failed, retry with paper deploy.",
    },
    "status_pushed_waiting_pages": {
        "zh_CN": "  已推送，等待 GitHub Pages 构建（通常需数分钟）。",
        "en_US": "  Pushed, waiting for GitHub Pages build (usually takes a few minutes).",
    },

    # ── Doctor ──
    "doctor_dependencies": {
        "zh_CN": "Markdown/Pygments 运行依赖",
        "en_US": "Markdown/Pygments dependencies",
    },
    "doctor_python_req": {
        "zh_CN": "Python >= 3.11（当前 {ver}）",
        "en_US": "Python >= 3.11 (Current: {ver})",
    },
    "doctor_git_req": {
        "zh_CN": "Git（仅发布需要）",
        "en_US": "Git (required for publishing)",
    },
    "doctor_config_req": {
        "zh_CN": "Paper 配置（{path}）",
        "en_US": "Paper config ({path})",
    },

    # ── Update & Uninstall ──
    "update_checking": {
        "zh_CN": "正在检查新版本……",
        "en_US": "Checking for updates...",
    },
    "update_brew_missing": {
        "zh_CN": "未找到 Homebrew，Paper 自更新依赖 brew。请先安装 Homebrew。",
        "en_US": "Homebrew not found. Self-update relies on brew. Please install Homebrew first.",
    },
    "update_non_brew": {
        "zh_CN": "当前 paper 不是 Homebrew 安装（源码或开发环境），无法用 brew 自更新。\n请先 `brew install ohmyangboy/tap/paper`，之后即可用 `paper update` 自更新。",
        "en_US": "Current paper is not a Homebrew installation (source or dev mode).\nInstall with `brew install ohmyangboy/tap/paper` to enable `paper update`.",
    },
    "update_current_ver": {
        "zh_CN": "当前版本：paper {version}",
        "en_US": "Current version: paper {version}",
    },
    "update_refreshing_tap": {
        "zh_CN": "正在刷新 Homebrew tap …",
        "en_US": "Updating Homebrew tap...",
    },
    "update_fetching_failed": {
        "zh_CN": "无法读取 Paper 最新版本信息，请检查网络后重试。",
        "en_US": "Failed to read Paper latest version info, check network and retry.",
    },
    "update_latest_version": {
        "zh_CN": "最新版本：paper {version}",
        "en_US": "Latest version: paper {version}",
    },
    "update_already_latest": {
        "zh_CN": "✅ 已是最新版本，无需更新。",
        "en_US": "✅ Already up to date.",
    },
    "update_upgrading": {
        "zh_CN": "发现新版本 {current} → {latest}，正在升级 …",
        "en_US": "New version available: {current} -> {latest}, upgrading...",
    },
    "update_success": {
        "zh_CN": "✅ 已升级到最新版本。",
        "en_US": "✅ Upgraded to latest version.",
    },
    "update_failed_brew_upgrade": {
        "zh_CN": "brew upgrade 失败，请手动运行：brew upgrade ohmyangboy/tap/paper",
        "en_US": "brew upgrade failed, please run manually: brew upgrade ohmyangboy/tap/paper",
    },
    "uninstall_guide": {
        "zh_CN": "Paper 程序由 Homebrew 管理，请使用：brew uninstall paper",
        "en_US": "Paper is managed by Homebrew, use: brew uninstall paper",
    },
    "uninstall_prompt_clean": {
        "zh_CN": "确认清理 ~/.paper（不会删除文章原稿）？输入 CLEAN：",
        "en_US": "Confirm cleaning ~/.paper (posts will NOT be deleted)? Type CLEAN:",
    },
    "uninstall_cleaned_msg": {
        "zh_CN": "✅ 已清理 Paper 配置与托管站点。原稿目录未修改。",
        "en_US": "✅ Cleaned Paper configuration and site data. Drafts were untouched.",
    },
    "uninstall_clean_cancelled": {
        "zh_CN": "已取消清理。",
        "en_US": "Cleanup cancelled.",
    },

    # ── Web Templates / RSS / HTML ──
    "html_lang_code": {
        "zh_CN": "zh-CN",
        "en_US": "en-US",
    },
    "rss_lang_code": {
        "zh_CN": "zh-CN",
        "en_US": "en-US",
    },
    "rss_description": {
        "zh_CN": "{site_name} 的最新文章",
        "en_US": "Latest posts from {site_name}",
    },
    "back_to_previous": {
        "zh_CN": "返回上一页",
        "en_US": "Back to previous page",
    },
    "draft_preview": {
        "zh_CN": "草稿预览",
        "en_US": "Draft Preview",
    },
    "draft_tag_paren": {
        "zh_CN": "（草稿）",
        "en_US": " (Draft)",
    },
    "image_not_found": {
        "zh_CN": "图片未找到：{filename}",
        "en_US": "Image not found: {filename}",
    },
    "lightbox_preview": {
        "zh_CN": "图片大图预览",
        "en_US": "Image Preview",
    },
    "lightbox_close": {
        "zh_CN": "关闭大图",
        "en_US": "Close Preview",
    },
    "not_found": {
        "zh_CN": "Not found",
        "en_US": "Not found",
    },

    # ── Argparse Help Texts ──
    "cli_description": {
        "zh_CN": "极简 Markdown 静态博客生成器与写作 CLI",
        "en_US": "Minimal Markdown static site generator and writing CLI",
    },
    "help_lang": {
        "zh_CN": "指定界面语言 (zh_CN, en_US, auto)",
        "en_US": "Set interface language (zh_CN, en_US, auto)",
    },
    "help_local": {
        "zh_CN": "以当前目录作为项目运行（忽略全局配置）",
        "en_US": "Run in local directory mode (ignore global config)",
    },
    "help_dir": {
        "zh_CN": "指定项目根目录路径",
        "en_US": "Specify project root directory path",
    },
    "help_cmd_init": {
        "zh_CN": "在当前目录初始化 Paper 博客",
        "en_US": "Initialize Paper blog in current directory",
    },
    "help_cmd_link": {
        "zh_CN": "关联外部 Markdown 文章目录",
        "en_US": "Link an external Markdown posts directory",
    },
    "help_cmd_new": {
        "zh_CN": "创建新文章草稿并打开编辑器",
        "en_US": "Create a new post draft and open editor",
    },
    "help_cmd_list": {
        "zh_CN": "列出并管理所有文章",
        "en_US": "List and manage all posts",
    },
    "help_cmd_build": {
        "zh_CN": "生成静态博客 HTML/CSS/RSS 站点",
        "en_US": "Generate static blog HTML/CSS/RSS site",
    },
    "help_cmd_serve": {
        "zh_CN": "启动本地热更新预览服务",
        "en_US": "Start local live-reload preview server",
    },
    "help_cmd_publish": {
        "zh_CN": "选择草稿并标记发布，重新生成站点",
        "en_US": "Select drafts, mark as published, and rebuild",
    },
    "help_cmd_deploy": {
        "zh_CN": "推送站点到 GitHub Pages (gh-pages)",
        "en_US": "Push site to GitHub Pages (gh-pages)",
    },
    "help_cmd_config": {
        "zh_CN": "查看或修改 Paper 配置",
        "en_US": "View or modify Paper configuration",
    },
    "help_cmd_status": {
        "zh_CN": "查看当前配置与部署就绪状态",
        "en_US": "Show configuration and deployment status",
    },
    "help_cmd_doctor": {
        "zh_CN": "检查运行环境与依赖完整性",
        "en_US": "Check runtime environment and dependencies",
    },
    "help_cmd_update": {
        "zh_CN": "检查并更新 Paper",
        "en_US": "Check and update Paper",
    },
    "help_cmd_uninstall": {
        "zh_CN": "卸载与清理配置，保留文章原件",
        "en_US": "Uninstall and clean data, keeping posts",
    },
}


def t(key: str, default: str | None = None, **kwargs: Any) -> str:
    """Translate a key into the currently active language with variable interpolation."""
    lang = get_current_language()
    entry = TRANSLATIONS.get(key)
    if entry:
        template = entry.get(lang) or entry.get("zh_CN") or entry.get("en_US")
        if template is not None:
            if kwargs:
                try:
                    return template.format(**kwargs)
                except KeyError:
                    return template
            return template

    if default is not None:
        if kwargs:
            try:
                return default.format(**kwargs)
            except KeyError:
                return default
        return default

    return key
