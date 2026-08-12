import './globals.css';
import type { Metadata } from 'next';
import { loadPaperConfig } from '@/lib/config';

export const metadata: Metadata = {
  title: {
    default: 'Paper Blog',
    template: '%s | Paper Blog',
  },
  description: 'A minimal SSG blog powered by Paper.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const config = loadPaperConfig();
  const primaryColor = config.color || '#D97757';
  const rawIcon = (config.icon || '').trim();
  const lowerIcon = rawIcon.toLowerCase();
  let faviconHref = '';
  let faviconType: string | undefined;

  if (lowerIcon.startsWith('data:image/')) {
    faviconHref = rawIcon;
    faviconType = rawIcon.slice(5).split(';')[0];
  } else if (lowerIcon.includes('<svg')) {
    faviconHref = `data:image/svg+xml;utf8,${encodeURIComponent(rawIcon)}`;
    faviconType = 'image/svg+xml';
  } else if (rawIcon) {
    faviconHref = rawIcon;
  }

  return (
    <html lang="zh-CN">
      <head>
        {faviconHref && (
          <link
            rel="icon"
            {...(faviconType ? { type: faviconType } : {})}
            href={faviconHref}
          />
        )}
        <style>{`:root { --primary: ${primaryColor}; }`}</style>
      </head>
      <body className="antialiased tracking-tight min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
        <div className="flex-1 flex flex-col max-w-[60ch] mx-auto w-full px-8 py-16 text-gray-900 dark:text-zinc-200">
          <main className="flex-1 space-y-6 md:mt-16">
            {children}
          </main>
          <Footer />
        </div>
      </body>
    </html>
  );
}

function Footer() {
  const config = loadPaperConfig();
  let githubUrl = 'https://github.com';
  if (config.gitRemote) {
    const raw = config.gitRemote.trim();
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      githubUrl = raw;
    } else if (raw.startsWith('git@github.com:')) {
      githubUrl = `https://github.com/${raw.replace('git@github.com:', '').replace(/\.git$/, '')}`;
    } else {
      githubUrl = `https://github.com/${raw.replace(/\.git$/, '')}`;
    }
  }

  return (
    <footer className="mt-auto pt-16 text-center w-full">
      <a
        href={githubUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="font-serif italic text-[0.725rem] tracking-wider text-gray-900 dark:text-zinc-200 opacity-[0.12] hover:opacity-50 hover:text-[var(--primary)] transition-all duration-200 no-underline inline-block"
      >
        Paper Blog
      </a>
    </footer>
  );
}

