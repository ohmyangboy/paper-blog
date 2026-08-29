---
title: Paper Blog's Markdown
date: "2026-08-28"
published: true
description: Paper Blog 全功能 Markdown 渲染测试与排版指南，融合文学叙事、深度学习图表、核心数学公式、多语言代码与结构化组件。
---

![[paper-blog-icon.png|40|left]]

## 1. 正文演示

唐代少年**李白**（字太白，号*青莲居士*）入象耳山读书，曾因攻读艰深欲废学下山。过小溪见一老妪在溪石上磨铁杵，问之，妪曰：*“欲作绣花针耳。”* 太白大受震撼，顿悟“**只要功夫深，铁杵磨成针**”之真谛，遂折节苦读成一代“诗仙”。后入长安醉令力士脱靴，挥毫写下千古豪迈绝唱：

> **《将进酒》· 李白（节选）**  
> 人生得意须尽欢，莫使金樽空对月。**天生我材必有用，千金散尽还复来！**

---

## 2. 科研图表

The empirical loss and probability density follow parametric surfaces $\hat{\mathcal{L}}(D, N) \approx \frac{A}{N^\alpha} + \frac{B}{D^\beta} + E$ and $f(x, y) = \frac{1}{2\pi}\exp\left(-\frac{x^2+y^2}{2}\right)$:

![[dual-3d-surfaces.svg|center]]

*Figure 1: Side-by-side 3D perspective projections: (a) Black-Gold Scaling Law empirical loss manifold, and (b) Crimson Bivariate Gaussian probability density bell surface.*

![[scaling-law-extrapolation.svg|center]]

*Figure 2: Empirical error extrapolation on small-regime calibration: (a) Grid sample space, (b) Vision error, (c) Language loss, and (d) Multi-optimizer convergence.*

---

## 3. 基础排版与交互容器

### 3.1 标题层级与行内样式 (Hierarchy & Typography)

# 一级标题 (H1) · 核心主题
## 二级标题 (H2) · 主功能模块
### 三级标题 (H3) · 子组件细分
#### 四级标题 (H4) · 具体知识点

- **加粗强调**：`**粗体**` $\rightarrow$ **加粗关键结论**
- *斜体强调*：`*斜体*` $\rightarrow$ *倾斜学术名词*
- ***粗斜体***：`***粗斜体***` $\rightarrow$ ***复合强调***
- ~~删除线~~：`~~删除线~~` $\rightarrow$ ~~已废弃内容~~
- `行内代码`：`` `const model = new Transformer();` ``
- **组合嵌套**：**粗体中嵌入 `行内代码`** 与 *斜体中的行内公式 $E = mc^2$*

### 3.2 引用、Callout 提示与任务清单 (Quotes, Callouts & Lists)

> “数学是上帝用来书写宇宙的语言。” —— *伽利略·伽利莱 (Galileo Galilei)*
> > **嵌套推论**：任何自洽形式系统必存在不可判定命题（哥德尔不完备定理）。

> 💡 **核心提示 (Note)**：LaTeX 行内公式使用单个 `$...$`，独立块级公式使用双美元符号 `$$...$$`。

> ⚠️ **警告注意 (Warning)**：计算极限时需严格验证洛必达法则不定式前置条件。

- **多维列表与任务清单**
  - [x] 完成并排 3D 曲面与黑金/暗红科研图表渲染
  - [x] 验证 LaTeX 扩展律公式与行内符号
  - [x] 基础排版模块合并与紧凑同屏优化
  - [ ] 探索超大规模参数模型涌现能力边界

### 3.3 图片排版与多图画廊 (Images & Gallery)

![[macos-mountain-lake.jpg]] ![[macos-coastal-cliff.jpg]]

![[macos-mountain-lake.jpg|460]] ![[macos-coastal-cliff.jpg|460]]

---

## 4. 工程组件与结构化数据

### 4.1 多语言语法高亮代码块 (Code Blocks)

```python
import numpy as np

def scaled_dot_product_attention(q: np.ndarray, k: np.ndarray, v: np.ndarray) -> np.ndarray:
    """计算 Scaled Dot-Product Attention: Softmax(QK^T / sqrt(d_k)) * V"""
    d_k = q.shape[-1]
    scores = np.matmul(q, k.swapaxes(-2, -1)) / np.sqrt(d_k)
    weights = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
    weights /= np.sum(weights, axis=-1, keepdims=True)
    return np.matmul(weights, v)
```

```typescript
export interface ApiResponse<T> {
  readonly status: "success" | "error";
  readonly data: T;
  readonly timestamp: number;
}

export async function fetchWithSchema<T>(endpoint: string): Promise<ApiResponse<T>> {
  const response = await fetch(endpoint);
  const data = (await response.json()) as T;
  return { status: "success", data, timestamp: Date.now() };
}
```

### 4.2 结构化多维表格与文献附录 (Tables & References)

| 定理 / 技术名称 | 核心表达式 / 架构 | 提出者 / 年代 | 领域与核心地位 | 验证状态 |
| :--- | :--- | :---: | :--- | :---: |
| **欧拉恒等式** | $e^{i\pi} + 1 = 0$ | 莱昂哈德·欧拉 (1748) | 贯通代数、几何与复分析的明珠 | 🌟 经典 |
| **质能方程** | $E = mc^2$ | 阿尔伯特·爱因斯坦 (1905) | 狭义相对论与现代物理学大厦基石 | ⚡ 基石 |
| **Transformer** | $\text{Attention}(Q, K, V)$ | Vaswani et al. (2017) | 大语言模型与现代 AI 核心底座 | 🚀 主流 |
| **微积分基本定理** | $\int_a^b f(x) dx = F(b) - F(a)$ | 牛顿 & 莱布尼茨 (17世纪) | 建立微分与积分的互逆对偶机制 | 📐 核心 |

- 访问项目主页：[Paper Blog GitHub 仓库](https://github.com/ohmyangboy/paper-blog)
- 文献参考：
  1. **Vaswani, A., et al. (2017)**. *Attention Is All You Need*. NeurIPS.
  2. **Kaplan, J., et al. (2020)**. *Scaling Laws for Neural Language Models*. arXiv:2001.08361.

---

*Markdown 全功能排版、文学典故、黑金暗红 3D 曲面与工程组件综合测试完毕。*
