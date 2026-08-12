# Paper v0.1 极简 SSG、写作控制台与发布流程规范

**Status:** ready-for-agent

## Problem Statement

Paper 的目标是让用户通过一次 Homebrew 安装获得完整的 Markdown 写作、管理、预览、构建和发布体验，不需要理解或手动维护 Node、npm、Next.js、Python 包和多套构建系统。

项目早期同时存在 Python CLI 与 Next.js/Node 构建链，导致 Markdown 渲染、网页样式、预览行为、配置路径和发布流程出现重复实现。主实现切换到 Python 后，又发生了一批用户可见的回归：原有方向键菜单消失、终端滚动条跳动、Ctrl+C 输出 traceback、菜单文案错位、网页视觉与页脚品牌改变、favicon 配置丢失、预览不再热更新、预览链接不能自动打开，以及部分外链图片因 CDN 防盗链返回 403。

用户还需要一条容易理解且安全的 GitHub Pages 发布路径。当前底层已经能使用已配置的 Git remote 推送 `gh-pages`，但 remote 与站点地址仍需手工编辑 JSON。下一阶段需要把 GitHub remote 配置、校验和发布准备完整纳入 CLI。

## Solution

Paper 使用 Python 作为唯一用户可见运行时和唯一构建图。CLI、配置、Markdown Profile、静态生成、本地预览和 GitHub Pages 部署全部进入同一套 Python 核心；浏览器端只接收生成后的静态 HTML、CSS 和少量预览刷新脚本。

用户直接执行 `paper` 进入方向键控制台，也可以继续使用明确的子命令完成自动化。控制台恢复原有菜单风格、备用屏幕、状态灯、文章工作台、多选发布和品牌设置。网站保持原有极简视觉，仅完善 Markdown 语法覆盖、安全输出、代码高亮、图片资源、favicon、RSS 与 sitemap。

本地预览只绑定本机地址，自动打开默认浏览器，监听 Markdown 与资源变化并自动刷新。生产构建排除草稿，并以临时目录和备份交换方式保护旧输出。

GitHub Pages 发布使用 Paper 隔离管理的托管目录，不在用户原稿目录中创建 Git 仓库。下一阶段通过 CLI 引导用户录入、检查和更新 GitHub remote 与站点 URL，在推送前明确展示目标仓库，避免误发到错误仓库。

## User Stories

1. As a writer, I want to install Paper once and run `paper` directly, so that I do not need to understand Python, Node, npm, or package managers.
2. As a Mac user, I want Homebrew to install Paper and all internal dependencies, so that runtime dependency prompts do not interrupt writing.
3. As a user, I want Python to be Paper's only runtime and build graph, so that there is only one implementation to understand and debug.
4. As a writer, I want to associate an existing Markdown directory through a native folder picker or path argument, so that my current notes remain the source of truth.
5. As a writer, I want Paper to keep my Markdown directory separate from generated files and Git metadata, so that my notes remain clean and portable.
6. As a first-time user, I want `paper init` to create and associate a standard writing directory, so that I can start without designing a folder structure.
7. As a writer, I want `paper new` to create a draft with safe frontmatter and open my chosen editor, so that I can begin writing immediately.
8. As a writer, I want missing `published` metadata to mean draft, so that a new or imported note is never published accidentally.
9. As a writer, I want Paper to reject multiline titles and slug collisions, so that malformed metadata cannot overwrite another page.
10. As a terminal user, I want running `paper` without arguments to open a keyboard-driven dashboard, so that common tasks are discoverable.
11. As a terminal user, I want to navigate with arrow keys or `j/k`, select with Enter or number keys, and return with Esc/Q, so that the interface feels like a familiar TUI.
12. As a terminal user, I want Paper menus to use the terminal alternate screen, so that redraws do not modify scrollback or make the scrollbar jump.
13. As a terminal user, I want Paper to restore the main screen and cursor on normal exit, errors, and signals, so that my terminal is never left in a broken state.
14. As a terminal user, I want Ctrl+C to exit quietly without a Python traceback, so that cancellation feels intentional.
15. As a terminal user, I want the dashboard to require Esc/Q twice before exiting, so that an accidental keypress does not close Paper.
16. As a terminal user, I want selected and unselected menu rows to keep identical description alignment, so that highlighting does not make text jump.
17. As a terminal user, I want concise, user-facing menu descriptions without implementation jargon, so that I can decide quickly.
18. As a user with a small terminal window, I want long menus to render within the available height, so that navigation never pushes content into scrollback.
19. As a blogger, I want the article console to show a green light for published content and a gray light for drafts or unpublished content, so that status is visible at a glance.
20. As a blogger, I want the homepage entry fixed at the top of the article console, so that editing the homepage is always easy to find.
21. As a blogger, I want all other articles ordered by filesystem modification time from newest to oldest, so that recently edited work appears first.
22. As a blogger, I want the modification date shown in the article console, so that the visible order is understandable.
23. As a blogger, I want to select an article and then edit, publish, unpublish, or delete it, so that content management stays inside Paper.
24. As a blogger, I want deletion to move an article to a recoverable trash location, so that an accidental deletion is not permanent.
25. As a publisher, I want `paper publish` to offer a keyboard multi-select list, so that I can release several drafts together.
26. As a publisher, I want build failure to restore the original draft state, so that a failed build does not silently change editorial status.
27. As a publisher, I want deployment failure to retain the published state and generated output, so that I can repair credentials and retry deployment.
28. As a publisher, I want Paper to verify the configured Git remote against the managed repository's `origin`, so that content is not pushed to the wrong repository.
29. As a publisher, I want Paper to stop when Git commit fails, so that an old commit is not reported or pushed as a new release.
30. As a publisher, I want `paper deploy` to retry a previously generated deployment, so that I do not have to republish content.
31. As a site owner, I want GitHub Pages output pushed as the root of the `gh-pages` branch, so that the repository can use branch-based Pages hosting.
32. As a site owner, I want Paper to generate directory-style post URLs, so that published links remain clean and portable.
33. As a site owner, I want GitHub project base paths handled consistently in HTML, RSS, and sitemap output, so that project Pages sites do not produce duplicate or relative URLs.
34. As a reader, I want the site to preserve Paper's original single-column, quiet visual style and automatic dark mode, so that Markdown improvements do not redesign the product.
35. As a reader, I want the footer `Paper Blog` mark to retain its subtle serif italic treatment, so that the original brand character remains intact.
36. As a site owner, I want the footer brand to link to the configured GitHub repository, so that readers can reach the project source.
37. As a site owner, I want to configure the highlight color through the direction-key configuration menu, so that the site can reflect my identity.
38. As a site owner, I want to configure a favicon using Paper's default P icon, SVG code, a Data URI, a URL, or a local image, so that browser tabs retain the intended brand.
39. As a site owner, I want local favicon files copied into the managed `assets` area, so that published pages do not depend on arbitrary filesystem paths.
40. As a writer, I want Paper to render CommonMark plus tables, strikethrough, task lists, links, images, and syntax-highlighted code, so that common Markdown documents render predictably.
41. As a security-conscious user, I want raw HTML disabled by default, so that untrusted Markdown does not become executable page markup.
42. As a security-conscious user, I want external links to open safely with isolation attributes, so that a linked page cannot control the Paper tab.
43. As a writer, I want local Markdown images written as `assets/...` to resolve at the site's public asset root, so that the same document works in preview and production.
44. As a reader, I want remote images loaded lazily and decoded asynchronously, so that image-heavy pages remain responsive.
45. As a writer, I want external images to omit the preview-page referrer, so that CDNs with hotlink protection do not return 403 solely because the source page is localhost.
46. As a security-conscious publisher, I want Paper to reject symbolic links in published assets, so that files outside the article directory cannot leak into the site.
47. As a writer, I want `paper serve` to include drafts and label them clearly, so that I can preview unpublished work safely.
48. As a writer, I want the preview server bound only to `127.0.0.1`, so that drafts are not exposed to the local network.
49. As a writer, I want `paper serve` to open the default browser automatically, so that I do not need to copy the preview URL.
50. As a writer, I want Paper to fall back to another local port when the requested port is unavailable, so that preview startup does not fail unnecessarily.
51. As a writer, I want Paper to watch Markdown and asset changes, rebuild the preview, and reload the browser automatically, so that editing has a tight feedback loop.
52. As a writer, I want a failed preview rebuild to keep serving the last good output, so that one temporary syntax error does not blank the preview.
53. As a user, I want damaged configuration JSON to produce an explicit actionable error, so that Paper does not silently write to a default directory.
54. As a returning user, I want Paper to migrate the earlier flat configuration once and retain a backup, so that upgrades do not lose settings.
55. As a user, I want `paper doctor` to report missing Markdown dependencies even when those dependencies are absent, so that diagnosis itself never crashes.
56. As a user, I want uninstall cleanup to remove only Paper-managed configuration and generated output, so that original Markdown files remain untouched.
57. As a future GitHub Pages user, I want GitHub remote configuration available inside `paper config`, so that I do not need to edit JSON manually.
58. As a future GitHub Pages user, I want to enter either an SSH or HTTPS GitHub repository address, so that Paper supports my existing authentication method.
59. As a future GitHub Pages user, I want Paper to normalize common GitHub repository URL forms, so that equivalent remote formats behave consistently.
60. As a future GitHub Pages user, I want Paper to derive the default Pages URL from the repository when possible, so that `siteUrl` requires minimal manual input.
61. As a future GitHub Pages user, I want Paper to show the repository owner, repository name, remote URL, and expected Pages URL before saving, so that I can catch mistakes.
62. As a future GitHub Pages user, I want Paper to test Git availability and remote accessibility before the first publish, so that authentication failures are found before content state changes.
63. As a future GitHub Pages user, I want Paper to detect an existing mismatched `origin` and ask for explicit confirmation before changing it, so that it never silently retargets a repository.
64. As a future GitHub Pages user, I want the configuration dashboard to report whether deployment is ready, so that I know what remains before publishing.

## Implementation Decisions

- Python is the only supported user-facing runtime and build graph. The historical Node/Next.js prototype is not part of the official build or deployment path.
- The runtime is split into a thin CLI entry point and a core module responsible for configuration, content discovery, Markdown rendering, static generation, URL generation, RSS, sitemap, and publication-state updates.
- `markdown-it-py` provides the CommonMark token and rendering model; Pygments provides syntax highlighting. These are internal Paper dependencies and must be packaged by the installer rather than requested from users at runtime.
- Paper defines a deliberate Markdown Profile: CommonMark baseline, tables, strikethrough, task lists, code highlighting, safe external links, local and remote images, and raw HTML disabled by default. GitHub-specific site post-processing and MDX are not compatibility targets.
- The single-site configuration lives under Paper's managed home and uses a versioned JSON schema. It records the source directory, managed site directory, Git remote, editor, deploy mode, site name, site URL, highlight color, favicon, and schema version.
- The user source directory contains top-level Markdown documents and an optional `assets` directory. Generated output, Git metadata, preview output, and configuration never live in that source directory.
- The homepage is represented by `index.md`. It is always the first row in the article console and is treated as online because it is the site's root page. If no physical homepage exists, Paper displays the virtual default and creates `index.md` when the user chooses to edit it.
- Regular articles are sorted by filesystem modification timestamp descending. Frontmatter `date` remains publication metadata for HTML/RSS but does not control the management console order.
- Article status uses `published: true` as the only online state. Missing or false values are shown as draft/unpublished.
- TUI menus use the terminal alternate-screen buffer and maintain a nesting depth so nested menus do not prematurely restore the main screen. Cursor and screen restoration also run from an exit guard.
- TUI rendering computes padding before adding ANSI color sequences. Selection color therefore cannot change visible column alignment.
- TUI menus use a window based on terminal height and keep the active row visible. Empty option lists return without entering terminal raw/alternate mode.
- Dashboard Esc/Q behavior is a two-step state: the first press arms exit and renders a warning; any real menu selection disarms exit; a second Esc/Q exits. Ctrl+C exits immediately with status 130 and no traceback.
- The article console allows editing the homepage. Regular articles additionally support publish, unpublish, and recoverable deletion.
- Preview builds use an isolated managed directory rather than overwriting production output. The HTTP handler receives its directory explicitly so atomic output replacement does not leave the server pointed at a renamed directory.
- Preview change detection uses a dependency-free filesystem snapshot poll covering Markdown and assets. Successful builds increment a revision endpoint; injected preview JavaScript reloads when the revision changes.
- The preview server binds to `127.0.0.1`, disables caching, falls back from an occupied requested port, and invokes the operating system's default browser after listening successfully.
- Static builds write into a temporary sibling directory and replace the previous output through a backup/rename sequence. Build failure preserves the last good output.
- Only the managed assets directory is copied. Symbolic links are rejected before copying.
- Remote Markdown images receive `referrerpolicy="no-referrer"`, lazy loading, and asynchronous decoding. Local `assets/...` image URLs are rewritten to the configured public base path.
- The website shell retains the established single-column layout, spacing, typography, automatic dark theme, original post list, back link, and subtle `Paper Blog` footer. New CSS is scoped to Markdown elements and syntax-highlight spans so highlighting cannot style the whole article container.
- The default favicon is Paper's geometric P SVG. Configuration accepts this preset, inline SVG, image Data URIs, external URLs, and selected local image files.
- Published posts use directory URLs. Public base-path and absolute-origin calculation are separated so GitHub Pages project paths are added exactly once.
- `paper publish` changes selected drafts, builds, then deploys. Build failure restores the original Markdown files; deploy failure keeps the published state and local output for retry.
- The managed deployment repository verifies that its `origin` equals the configured Git remote. Commit failure aborts before subtree push. Deployment pushes generated output to the root of `gh-pages`.
- The next GitHub remote CLI phase extends the existing configuration dashboard rather than adding a second configuration system. It must support SSH and HTTPS input, normalization, preview/confirmation, remote reachability checks, Pages URL derivation, mismatch handling, and readiness status.
- GitHub credentials remain owned by Git/SSH/GitHub CLI. Paper must never store tokens, passwords, private keys, or credential material in its configuration.
- Homebrew is the intended user installation surface. A release is not valid until the Formula uses a real tagged archive and checksum, installs the CLI/core plus locked Python resources, and passes a clean-machine smoke test without Node, npm, pip, or globally installed Python packages.

## Testing Decisions

- Tests assert external behavior and durable state rather than private implementation details. The highest practical seam is preferred even when a smaller unit seam also exists.
- The primary CLI seam is a real pseudo-terminal session that launches `paper`, sends arrow/Esc/Q/Ctrl+C input, and inspects exit code and rendered terminal protocol. This covers navigation, alternate-screen entry/restoration, double-confirm exit, quiet Ctrl+C, status lights, homepage ordering, windowed rendering, and visible alignment.
- Small deterministic terminal helpers may additionally be unit-tested for escape-sequence grouping, visible menu windows, and empty-list behavior, but these do not replace PTY coverage.
- The primary preview seam is a real localhost server with an isolated Paper home and source directory. Tests modify Markdown, poll generated HTML and the revision endpoint, and verify rebuild, reload signaling, image policy, cache policy, browser-open invocation, port behavior, and last-good-output preservation.
- The primary static-generation seam builds a complete temporary site and inspects generated HTML, post paths, favicon, footer, Markdown structures, assets, RSS, sitemap, base paths, and draft exclusion.
- Content discovery tests control filesystem modification timestamps explicitly and verify homepage-first console composition separately from regular-article modification ordering.
- Configuration tests use an isolated Paper home and cover missing config, invalid JSON, migration, persistence, brand fields, and future GitHub remote fields without touching the user's real configuration.
- Deployment tests use disposable local Git repositories and fake remotes where possible. They cover missing Git, missing remote, mismatched origin, commit failure, push failure, published-state behavior, and retryability without contacting a real user repository.
- The future GitHub remote CLI should have one end-to-end configuration seam: drive the configuration dashboard in a PTY, save a normalized remote, derive or accept the Pages URL, and then inspect both persisted configuration and managed-repository origin. URL parsing helpers may have table-driven unit coverage for SSH/HTTPS variants.
- A release-level Homebrew smoke test must start from an environment without Node/npm and without globally installed Paper Python dependencies, install through the Formula/bottle, and run version, doctor, init/link, build, serve, and help commands.
- Existing Python unit tests, PTY harnesses, localhost curl harnesses, wheel inspection, syntax compilation, and headless browser screenshots are the prior art to extend.

## Out of Scope

- Node.js, npm, Next.js, React, MDX, JSX, or another parallel production rendering pipeline.
- Dynamic databases, server-side rendering, authentication, accounts, comments, or an administration web application.
- Multiple independent sites in one Paper configuration for v0.1.
- Full YAML support beyond Paper's documented frontmatter fields and scalar profile.
- Exact byte-for-byte GitHub Markdown rendering or GitHub's private site post-processing.
- Automatic creation of GitHub accounts, repositories, SSH keys, personal access tokens, or credential storage.
- Silently changing an existing Git remote or pushing without showing and validating the target.
- Deleting user Markdown during uninstall or cleanup.
- Public LAN preview or production hosting through the local preview server.
- Advanced taxonomies, themes, plugins, MDX components, search indexing, or client-side application hydration.
- A Homebrew release that uses placeholder URLs, fake checksums, or relies on the user's global Python environment.

## Further Notes

- The current Python implementation covers the CLI dashboard, article console, status lights, homepage-first ordering, modification-time ordering, multiselect publishing, brand/favicons, Markdown Profile, external-image 403 mitigation, isolated hot-reload preview, static generation, RSS/sitemap, and guarded Git deployment.
- The repository still contains historical Next.js prototype files and a placeholder Homebrew Formula. They are not the official runtime but remain release blockers until removed or explicitly archived and until a real Formula is produced.
- The current deployment backend expects `gitRemote` and normally `siteUrl` to already be configured. Until the GitHub remote CLI phase is implemented, users must edit configuration manually.
- GitHub remote configuration is the next planned feature and should be delivered through the existing `paper config` direction-key flow, not as a separate wizard or another config file.
- A future deployment readiness view should distinguish at least: not configured, configured but unverified, ready, push failed, and pushed awaiting Pages availability.
- The local issue tracker uses `ready-for-agent` as the execution-ready triage state; this specification is published with that status.
