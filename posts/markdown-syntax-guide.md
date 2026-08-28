---
title: Markdown 常用语法与样式测试
date: "2026-08-28"
published: true
description: Paper Blog 全功能 Markdown 渲染测试用例，包含基础排版、代码高亮、多维表格、经典数学公理与定理公式，以及科学矢量图表。
---

这篇文章用于测试和全面展示 **Paper Blog** 渲染常用 Markdown 语法、数学公式、图标以及科学图表的效果。

---

## 1. 标题层级

# 一级标题 (H1)
## 二级标题 (H2)
### 三级标题 (H3)
#### 四级标题 (H4)
##### 五级标题 (H5)
###### 六级标题 (H6)

---

## 2. 文本强调与行内样式

- **粗体文本**：使用 `**粗体**` 或 `__粗体__` $\rightarrow$ **加粗强调**
- *斜体文本*：使用 `*斜体*` 或 `_斜体_` $\rightarrow$ *倾斜强调*
- ***粗斜体***：使用 `***粗斜体***` $\rightarrow$ ***粗斜体文本***
- ~~删除线~~：使用 `~~删除线~~` $\rightarrow$ ~~已废弃内容~~
- `行内代码`：使用反引号 `` `const pi = 3.14159;` ``
- **组合样式**：**粗体与 `行内代码` 结合** 或 *斜体中的 $E = mc^2$ 公式*

---

## 3. 引用块与提示 (Blockquotes & Callouts)

### 3.1 基础与名人引言

> 简单是可靠的前提。
> —— *Edsger W. Dijkstra*

> “数学是上帝用来书写宇宙的语言。”  
> —— *伽利略·伽利莱 (Galileo Galilei)*

### 3.2 多层嵌套引用

> 这是一个一级引用块。
> > 这是嵌套的二级引用块，用于补充说明或引用前置结论。
> > > 深度嵌套的三级引用，用于标注注释与定理背景。

### 3.3 提示与状态标注 (Callouts)

> 💡 **核心提示 (Note)**：所有公理与数学定理均具备自洽性，是现代科学大厦的逻辑基石。

> ⚠️ **警告注意 (Warning)**：除法运算中分母不能为零，在极限求值时需注意不定型 $\frac{0}{0}$ 与洛必达法则（L'Hôpital's Rule）的适用条件。

---

## 4. 列表与任务清单 (Lists)

### 4.1 无序列表
- 基础数学与几何学 (Euclidean Geometry)
- 微积分与数学分析 (Calculus & Real Analysis)
- 抽象代数与线性代数 (Linear Algebra)
- 概率论与数理统计 (Probability & Statistics)

### 4.2 有序列表
1. 建立公理系统（Axiom System）
2. 提出数学假设与命题猜想（Conjecture）
3. 严格形式化演绎证明（Formal Proof）
4. 得出推论并应用于物理与工程建模（Application）

### 4.3 任务清单 (Task Lists)
- [x] 验证欧拉恒等式与复数运算闭包性
- [x] 验证微积分基本定理与牛顿-莱布尼茨公式
- [x] 绘制高斯正态分布 3D 钟形曲面
- [ ] 探索黎曼猜想非平凡零点分布
- [ ] 形式化检验连续统假设独立性

---

## 5. 代码块 (Code Blocks)

### 5.1 Python：数值积分与高斯分布模拟

```python
import math
import numpy as np

def normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """计算一维标准正态分布概率密度函数"""
    coeff = 1.0 / (sigma * math.sqrt(2.0 * math.pi))
    exponent = -0.5 * ((x - mu) / sigma) ** 2
    return coeff * math.exp(exponent)

def trapezoidal_rule(f, a: float, b: float, n: int = 1000) -> float:
    """梯形数值积分法验证全概率积分为 1"""
    h = (b - a) / n
    total = 0.5 * (f(a) + f(b))
    for i in range(1, n):
        total += f(a + i * h)
    return total * h

if __name__ == "__main__":
    integral = trapezoidal_rule(normal_pdf, -5.0, 5.0, n=10000)
    print(f"标准正态分布在 [-5, 5] 积分值: {integral:.6f} (理论值 ≈ 1.0)")
```

### 5.2 TypeScript / JavaScript：欧拉公式验证

```typescript
interface Complex {
  readonly re: number;
  readonly im: number;
}

export function eulerFormula(theta: number): Complex {
  // e^(i * theta) = cos(theta) + i * sin(theta)
  return {
    re: Math.cos(theta),
    im: Math.sin(theta)
  };
}

// 验证欧拉恒等式 e^(i * π) + 1 ≈ 0
const result = eulerFormula(Math.PI);
console.log(`e^(iπ) = ${result.re.toFixed(4)} + ${result.im.toFixed(4)}i`);
```

---

## 6. 链接与多媒体图片

- 访问项目：[Paper Blog GitHub 仓库](https://github.com/ohmyangboy/paper-blog)
- 外部链接测试：[Wolfram MathWorld 公开数学百科](https://mathworld.wolfram.com)
- 站点图标展示：
  ![Paper Blog Icon](https://ohmyangboy.github.io/paper-blog/assets/paper-blog-icon.png)

---

## 7. 复杂表格 (Tables)

| 定理 / 公式名称 | 核心数学表达式 | 提出者 / 纪元 | 领域与重要性 | 状态 |
| :--- | :--- | :---: | :--- | :---: |
| **勾股定理** | $a^2 + b^2 = c^2$ | 毕达哥拉斯 (公元前5世纪) | 欧氏几何与度量空间基础 | ✅ 已验证 |
| **欧拉恒等式** | $e^{i\pi} + 1 = 0$ | 莱昂哈德·欧拉 (1748) | 连结分析、几何与代数的桥梁 | 🌟 经典 |
| **质能等价公理** | $E = mc^2$ | 阿尔伯特·爱因斯坦 (1905) | 狭义相对论基本物理定律 | ⚡ 物理基石 |
| **微积分基本定理** | $\int_a^b f(x) dx = F(b) - F(a)$ | 牛顿 & 莱布尼茨 (17世纪) | 微分与积分的互逆运算对偶性 | 📐 核心工具 |
| **高斯积分** | $\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}$ | 卡尔·弗里德里希·高斯 (1809) | 概率论与统计物理归一化因子 | 📊 基础定理 |

---

## 8. 数学公式与经典公理定理 (Math Equations & Axioms)

本模块系统测试 LaTeX 语法的行内公式（Inline Math）与独立块级公式（Block Math）在各种复杂场景下的表现。

### 8.1 经典数学恒等式与分析学公理

#### 欧拉公式与五大常数恒等式
欧拉公式将三角函数与复指数函数相统一：

$$e^{i\theta} = \cos\theta + i\sin\theta$$

当 $\theta = \pi$ 时，导出连结数学五大基础常数（$e, i, \pi, 1, 0$）的欧拉恒等式：

$$e^{i\pi} + 1 = 0$$

#### 微积分基本定理 (Newton-Leibniz Formula)
设 $f$ 在闭区间 $[a, b]$ 上连续，且 $F' = f$，则定积分等于原函数的增量：

$$\int_a^b f(x) dx = F(b) - F(a) = \left. F(x) \right|_a^b$$

#### 泰勒级数展开定理 (Taylor Expansion)
光滑函数在点 $a$ 处的无穷级数展开：

$$f(x) = \sum_{n=0}^{\infty} \frac{f^{(n)}(a)}{n!} (x - a)^n = f(a) + f'(a)(x - a) + \frac{f''(a)}{2!}(x - a)^2 + \cdots + R_n(x)$$

---

### 8.2 概率论、信息论与数理统计公理

#### 一维与多维高斯正态分布概率密度函数 (Gaussian PDF)
一维正态分布 $X \sim \mathcal{N}(\mu, \sigma^2)$ 的密度函数为：

$$f(x) = \frac{1}{\sigma \sqrt{2\pi}} \exp\left( -\frac{(x - \mu)^2}{2\sigma^2} \right)$$

二维不相关标准正态分布 $(X, Y)$ 的联合概率密度函数（三维旋转对称钟形曲面）：

$$f(x, y) = \frac{1}{2\pi} \exp\left( -\frac{x^2 + y^2}{2} \right)$$

#### 贝叶斯定理 (Bayes' Theorem)
条件概率与先验-后验概率更新公式：

$$P(A \mid B) = \frac{P(B \mid A) P(A)}{P(B)} = \frac{P(B \mid A) P(A)}{\sum_{i} P(B \mid A_i) P(A_i)}$$

#### 香农信息熵定理 (Shannon Entropy)
离散随机变量 $X$ 的信息度量公理：

$$H(X) = -\sum_{i=1}^{n} P(x_i) \log_2 P(x_i) = \mathbb{E}[-\log_2 P(X)]$$

---

### 8.3 线性代数与向量空间几何

#### 柯西-施瓦茨不等式 (Cauchy-Schwarz Inequality)
对于内积空间中的任意向量 $u, v \in V$：

$$|\langle u, v \rangle|^2 \le \langle u, u \rangle \cdot \langle v, v \rangle \quad \Longleftrightarrow \quad \left(\sum_{i=1}^n u_i v_i\right)^2 \le \left(\sum_{i=1}^n u_i^2\right) \left(\sum_{i=1}^n v_i^2\right)$$

#### 矩阵特征值分解定理 (Spectral Decomposition)
若方阵 $A$ 具有特征值 $\lambda$ 与对应的非零特征向量 $v$：

$$A v = \lambda v \quad \Longleftrightarrow \quad \det(A - \lambda I) = 0$$

---

### 8.4 物理学基础公理与微分方程

#### 麦克斯韦方程组微分形式 (Maxwell's Equations)

$$\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0} \qquad \text{(高斯电场定律)}$$

$$\nabla \cdot \mathbf{B} = 0 \qquad \text{(高斯磁场定律)}$$

$$\nabla \times \mathbf{E} = -\frac{\partial \mathbf{B}}{\partial t} \qquad \text{(法拉第电磁感应定律)}$$

$$\nabla \times \mathbf{B} = \mu_0 \mathbf{J} + \mu_0 \varepsilon_0 \frac{\partial \mathbf{E}}{\partial t} \qquad \text{(安培-麦克斯韦定律)}$$

#### 薛定谔波动方程 (Schrödinger Equation)
量子力学中微观粒子状态演化的基本动力学方程：

$$i\hbar \frac{\partial}{\partial t}\Psi(\mathbf{r}, t) = \hat{H}\Psi(\mathbf{r}, t) = \left[ -\frac{\hbar^2}{2m}\nabla^2 + V(\mathbf{r}, t) \right] \Psi(\mathbf{r}, t)$$

---

### 8.5 行内数学符号与上下标边界测试

- **集合论与数系**：$\mathbb{N} \subset \mathbb{Z} \subset \mathbb{Q} \subset \mathbb{R} \subset \mathbb{C}$
- **极限求值**：$\lim_{x \to 0} \frac{\sin x}{x} = 1$ 以及重要极限 $\lim_{n \to \infty} \left(1 + \frac{1}{n}\right)^n = e$
- **无穷级数收敛性**：几何级数 $\sum_{k=0}^\infty q^k = \frac{1}{1 - q} \quad (|q| < 1)$
- **分段函数表示**：
  $$f(x) = \begin{cases} \frac{\sin x}{x}, & x \neq 0 \\ 1, & x = 0 \end{cases}$$

---

## 9. 科学图表与几何可视化 (Diagrams & Visualizations)

### 9.1 高斯二维联合正态分布 3D 钟形曲面
![[gaussian-distribution-3d.svg|center]]

*图 1：二维标准正态分布概率密度函数 $f(x, y) = \frac{1}{2\pi}e^{-\frac{x^2+y^2}{2}}$ 的三维透视投影曲面。底面网格展示自变量取值范围 $[-3, 3] \times [-3, 3]$，色彩梯度映射高度密度值。（公开数学模型，CC0 矢量绘制）*

### 9.2 复平面单位圆与欧拉公式几何意义
![[euler-unit-circle.svg|center]]

*图 2：在复数平面（Complex Plane）上，复数 $e^{i\theta} = \cos\theta + i\sin\theta$ 构成单位圆上半径为 1 的旋转矢量，直观诠释三角函数与复指数函数的内在联系。*

---

## 10. 分隔线与附录

### 参考文献与公理出处

1. **Euclid (c. 300 BC)**. *Elements of Geometry*.
2. **Euler, L. (1748)**. *Introductio in analysin infinitorum*.
3. **Gauss, C. F. (1809)**. *Theoria motus corporum coelestium*.
4. **Maxwell, J. C. (1865)**. *A Dynamical Theory of the Electromagnetic Field*.
5. **Shannon, C. E. (1948)**. *A Mathematical Theory of Communication*. *Bell System Technical Journal*.

---

*Markdown 常用语法、公开公理定理与数学公式测试完毕。*
