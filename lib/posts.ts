import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';
import { loadPaperConfig } from './config';

export interface PostItem {
  slug: string;
  title: string;
  date: string;
  published: boolean;
  content: string;
  filePath: string;
}

// 将 frontmatter 日期规范化为 YYYY-MM-DD（gray-matter 会把无引号日期解析为 Date 对象）
function normalizeDate(value: unknown, fallback: string): string {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().split('T')[0];
  }
  const s = String(value ?? '');
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return fallback;
}

export function ensurePostsDirExists(dirPath?: string): string {
  const targetDir = dirPath || loadPaperConfig().postsDir;
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }
  return targetDir;
}

export const DEFAULT_INDEX_MD = '# Paper Blog\n\n写简单的文字，做干净的博客。\n';

// 历史遗留文案迁移：旧版默认首页含 "Lee Rob" / "macOS 原生" 字样，检测到即整体替换为新默认内容
function migrateLegacyIndexMd(indexPath: string): void {
  const content = fs.readFileSync(indexPath, 'utf-8');
  if (/Lee Rob|macOS 原生/.test(content)) {
    fs.writeFileSync(indexPath, DEFAULT_INDEX_MD, 'utf-8');
  }
}

export function ensureIndexMdExists(dirPath?: string): string {
  const targetDir = ensurePostsDirExists(dirPath);
  const indexPath = path.join(targetDir, 'index.md');
  if (!fs.existsSync(indexPath)) {
    fs.writeFileSync(indexPath, DEFAULT_INDEX_MD, 'utf-8');
    return indexPath;
  }
  migrateLegacyIndexMd(indexPath);
  return indexPath;
}

export function getIndexPost(): PostItem {
  const indexPath = ensureIndexMdExists();
  const fileContent = fs.readFileSync(indexPath, 'utf-8');
  const { data, content } = matter(fileContent);
  const stat = fs.statSync(indexPath);

  return {
    slug: 'index',
    title: data.title || 'Paper Blog',
    date: normalizeDate(data.date, new Date(stat.mtime).toISOString().split('T')[0]),
    published: true,
    content,
    filePath: indexPath,
  };
}

export function getAllPosts(): PostItem[] {
  const postsDir = ensurePostsDirExists();
  ensureIndexMdExists(postsDir);
  if (!fs.existsSync(postsDir)) {
    return [];
  }

  const files = fs.readdirSync(postsDir);
  const posts: PostItem[] = [];

  for (const file of files) {
    if (!file.endsWith('.md') && !file.endsWith('.mdx')) {
      continue;
    }
    const lowerName = file.toLowerCase();
    if (lowerName === 'index.md' || lowerName === 'readme.md') {
      continue;
    }

    const filePath = path.join(postsDir, file);
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) continue;

    const fileContent = fs.readFileSync(filePath, 'utf-8');
    const { data, content } = matter(fileContent);

    const slug = file.replace(/\.(md|mdx)$/, '');
    const title = data.title || slug;
    const date = normalizeDate(data.date, new Date(stat.mtime).toISOString().split('T')[0]);
    const published = data.published !== undefined ? Boolean(data.published) : true;

    posts.push({
      slug,
      title,
      date,
      published,
      content,
      filePath,
    });
  }

  // 按日期降序排列
  return posts.sort((a, b) => (a.date < b.date ? 1 : -1));
}

export function getPublishedPosts(): PostItem[] {
  return getAllPosts().filter((post) => post.published);
}

export function getPostBySlug(slug: string): PostItem | null {
  if (slug === 'index') {
    return getIndexPost();
  }
  const posts = getAllPosts();
  const found = posts.find((p) => p.slug === slug);
  return found || null;
}

export function updatePostPublishedStatus(filePath: string, published: boolean): void {
  if (!fs.existsSync(filePath)) return;
  const fileContent = fs.readFileSync(filePath, 'utf-8');
  const parsed = matter(fileContent);

  parsed.data.published = published;
  const newContent = matter.stringify(parsed.content, parsed.data);
  fs.writeFileSync(filePath, newContent, 'utf-8');
}

