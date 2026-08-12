import Link from 'next/link';
import { getPublishedPosts, getIndexPost } from '@/lib/posts';
import { MarkdownRenderer } from '@/components/markdown';
import { loadPaperConfig } from '@/lib/config';

export default function HomePage() {
  const indexPost = getIndexPost();
  const posts = getPublishedPosts();
  const config = loadPaperConfig();
  const rawIcon = config.icon && config.icon.includes('<svg')
    ? config.icon
    : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 26V6h10a6 6 0 0 1 0 12H8"/></svg>`;

  return (
    <section className="space-y-8">
      <header className="relative space-y-2">
        <MarkdownRenderer content={indexPost.content} />
      </header>

      <div className="space-y-4 pt-4">
        <h2 className="text-sm font-medium tracking-wide text-gray-400 dark:text-zinc-500 uppercase">
          Writing
        </h2>

        {posts.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-zinc-500 italic">
            暂无已发布的文章。使用 <code className="px-1 bg-gray-100 dark:bg-zinc-800 rounded">paper publish</code> 发布第一篇随笔。
          </p>
        ) : (
          <ul className="space-y-3">
            {posts.map((post) => (
              <li key={post.slug} className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-1">
                <Link
                  href={`/posts/${post.slug}`}
                  className="font-medium text-gray-900 dark:text-zinc-200 underline decoration-1 decoration-gray-300 dark:decoration-zinc-700 underline-offset-4 hover:text-[var(--primary)] hover:decoration-[var(--primary)] transition-colors duration-150"
                >
                  {post.title}
                </Link>
                <time className="text-xs text-gray-400 dark:text-zinc-500 tabular-nums shrink-0">
                  {post.date}
                </time>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

