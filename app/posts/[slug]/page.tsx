import { notFound } from 'next/navigation';
import { getPublishedPosts, getPostBySlug } from '@/lib/posts';
import { MarkdownRenderer } from '@/components/markdown';

interface PostPageProps {
  params: Promise<{
    slug: string;
  }>;
}

export async function generateStaticParams() {
  const posts = getPublishedPosts();
  return posts.map((post) => ({
    slug: post.slug,
  }));
}

export default async function PostPage({ params }: PostPageProps) {
  const { slug } = await params;
  const post = getPostBySlug(slug);

  if (!post || !post.published) {
    notFound();
  }

  return (
    <article className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 text-gray-400 dark:text-zinc-500"
            aria-hidden="true"
          >
            <path d="M19 12H5" />
            <path d="M12 19l-7-7 7-7" />
          </svg>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-zinc-100">
            {post.title}
          </h1>
        </div>
        <div className="text-xs text-gray-400 dark:text-zinc-500 tabular-nums">
          {post.date}
        </div>
      </div>

      <div className="pt-4">
        <MarkdownRenderer content={post.content} />
      </div>
    </article>
  );
}
