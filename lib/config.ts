import fs from 'fs';
import os from 'os';
import path from 'path';

export interface PaperConfig {
  postsDir: string;
  repoDir?: string;
  gitRemote?: string;
  editor?: string;
  deploy?: string;
  icon?: string;
  color?: string;
}

export const DEFAULT_COLOR = '#D97757';

// 内置款一：单色几何极简 P（默认）
export const DEFAULT_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="32" height="32"><rect width="100" height="100" rx="22" fill="#F9F9FB"/><path d="M 32 25 L 56 25 C 68 25 74 33 74 44 C 74 55 68 63 56 63 L 44 63 L 44 75" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/><path d="M 44 37 L 55 37 C 62 37 65 40 65 44 C 65 48 62 51 55 51 Z" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><line x1="32" y1="25" x2="32" y2="75" stroke="currentColor" stroke-width="6" stroke-linecap="round"/></svg>`;

// 内置款二：纸艺双色叠层 P
export const DEFAULT_ICON_LAYERED = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="32" height="32"><rect width="100" height="100" rx="22" fill="#F9F9FB"/><g opacity="0.35"><path d="M 26 24 L 58 24 C 71 24 78 32 78 45 C 78 58 71 66 58 66 L 42 66 L 42 76" fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></g><g opacity="0.9"><path d="M 40 36 L 62 36 C 71 36 78 42 78 51 C 78 60 71 66 62 66 L 52 66 L 52 74" fill="none" stroke="currentColor" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></g></svg>`;

// 精选预设色板（暖橙 / 经典蓝 / 翡翠绿 / 优雅紫 / 墨黑）
export const PRESET_COLORS: { name: string; hex: string }[] = [
  { name: '暖橙 Terracotta', hex: '#D97757' },
  { name: '经典蓝', hex: '#3B82F6' },
  { name: '翡翠绿', hex: '#10B981' },
  { name: '优雅紫', hex: '#8B5CF6' },
  { name: '墨黑', hex: '#111827' },
];

const CONFIG_FILE_NAME = '.paper-config.json';

export function getProjectRoot(): string {
  return process.cwd();
}

export function getLocalConfigPath(): string {
  return path.join(getProjectRoot(), CONFIG_FILE_NAME);
}

export function getGlobalConfigPath(): string {
  return path.join(os.homedir(), CONFIG_FILE_NAME);
}

export function getConfigFilePath(): string {
  // 本地目录优先，全局兜底
  if (fs.existsSync(getLocalConfigPath())) return getLocalConfigPath();
  return getGlobalConfigPath();
}

export function getDefaultPostsDir(): string {
  return path.join(getProjectRoot(), 'posts');
}

export function loadPaperConfig(): PaperConfig {
  let loaded: Partial<PaperConfig> = {};

  const localPath = getLocalConfigPath();
  const globalPath = getGlobalConfigPath();
  const configPath = fs.existsSync(localPath) ? localPath : (fs.existsSync(globalPath) ? globalPath : '');

  if (configPath) {
    try {
      const content = fs.readFileSync(configPath, 'utf-8');
      loaded = JSON.parse(content);
    } catch {
      // 容错读取失败
    }
  }

  const postsDir = loaded.postsDir
    ? path.resolve(loaded.postsDir)
    : (process.env.POSTS_DIR ? path.resolve(process.env.POSTS_DIR) : getDefaultPostsDir());

  return {
    postsDir,
    repoDir: loaded.repoDir || '',
    gitRemote: loaded.gitRemote || '',
    editor: loaded.editor || 'default',
    deploy: loaded.deploy || 'auto',
    icon: loaded.icon || DEFAULT_ICON_SVG,
    color: loaded.color || DEFAULT_COLOR,
  };
}

export function savePaperConfig(config: Partial<PaperConfig>): PaperConfig {
  const current = loadPaperConfig();
  const updated: PaperConfig = {
    ...current,
    ...config,
  };

  // 检测本地 .paper-config.json 存在则写本地，否则写全局
  const configPath = getConfigFilePath();
  fs.writeFileSync(configPath, JSON.stringify(updated, null, 2), 'utf-8');
  return updated;
}

// 将 git 远程地址统一转换为 HTTPS GitHub URL
export function resolveGithubUrl(gitRemote?: string): string {
  if (!gitRemote) return 'https://github.com';
  const raw = gitRemote.trim();
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    return raw;
  }
  if (raw.startsWith('git@github.com:')) {
    return `https://github.com/${raw.replace('git@github.com:', '').replace(/\.git$/, '')}`;
  }
  return `https://github.com/${raw.replace(/\.git$/, '')}`;
}
