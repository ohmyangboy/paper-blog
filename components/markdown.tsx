import React from 'react';
import { marked } from 'marked';
import { highlight } from 'sugar-high';

interface MarkdownProps {
  content: string;
}

// marked v18: renderer.code 收到的是未转义的原始代码文本，
// 直接交给 sugar-high（内部自行转义），避免旧方案手动反转义的双重转义问题。
const renderer = new marked.Renderer();

renderer.code = ({ text, lang }) => {
  const language = lang ? ` class="language-${lang}"` : '';
  const langAttr = lang ? ` data-lang="${lang}"` : '';
  const normalized = text.replace(/\n$/, '') + '\n';
  return `<pre${langAttr}><code${language}>${highlight(normalized)}</code></pre>`;
};

marked.use({ renderer });

export function MarkdownRenderer({ content }: MarkdownProps) {
  const html = marked.parse(content, { async: false }) as string;

  return (
    <div
      className="markdown max-w-none text-gray-800 dark:text-zinc-300"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
