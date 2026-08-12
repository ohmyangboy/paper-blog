---
title: Markdown 常用语法与样式测试
date: '2026-08-12'
published: true
---

这篇文章用于测试和展示 Paper Blog 渲染常用 Markdown 语法的效果。

## 1. 标题层级

# 一级标题
## 二级标题
### 三级标题
#### 四级标题

---

## 2. 文本强调与行内样式

- **粗体文本**：使用 `**粗体**` 或 `__粗体__`
- *斜体文本*：使用 `*斜体*` 或 `_斜体_`
- ~~删除线~~：使用 `~~删除线~~`
- `行内代码`：使用反引号 `` `code` ``

---

## 3. 引用块 (Blockquote)

> 简单是可靠的前提。
> — Edsger W. Dijkstra

嵌套引用：

> 这是一个一级引用。
> > 这是嵌套的二级引用。

---

## 4. 列表

### 无序列表
- 前端开发 (Next.js, React)
- 命令行工具 (Python SSG)
- 设计系统 (Vanilla CSS)

### 有序列表
1. 编写 Markdown 内容
2. 执行 `paper publish` 构建
3. 自动同步并部署站点

---

## 5. 代码块 (Code Blocks)

### JavaScript 示例
```javascript
function greet(name) {
  const greeting = `Hello, ${name}! Welcome to Paper Blog.`;
  console.log(greeting);
  return greeting;
}

greet('World');
```

### Python 示例
```python
def generate_site(posts_dir, out_dir):
    print(f"Building site from {posts_dir} to {out_dir}...")
    return True

if __name__ == "__main__":
    generate_site("posts", "out")
```

---

## 6. 链接与图片

- 访问 [Paper Blog 官方 GitHub 仓库](https://github.com)
- 行内链接样式：[Lee Rob 极简博客](https://leerob.com)
- 图片 ![image](https://i1.hdslb.com/bfs/face/c7c9deecf9f61d8d45717778b4059b7b2e15cd55.jpg@96w_96h)

---

## 7. 表格 (Table)

| 语法 | 说明 | 示例 |
| :--- | :--- | :--- |
| Header | 标题说明 | `# Title` |
| Emphasis | 强调文字 | `**Bold**` |
| Link | 网页超链接 | `[Text](URL)` |
| Code | 代码片段 | `` `npm run dev` `` |

---

## 8. 分隔线

使用三个以上的连字符 `---` 或星号 `***`：

---

*Markdown 语法检测测试完成。*
