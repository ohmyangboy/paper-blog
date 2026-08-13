class Paper < Formula
  include Language::Python::Virtualenv

  desc "Minimal Markdown static site generator and writing CLI"
  homepage "https://github.com/ohmyangboy/paper-blog"
  url "https://github.com/ohmyangboy/paper-blog/archive/refs/tags/v0.1.1-beta.2.tar.gz"
  sha256 "891bd370f9833976c8e8f793402ec2280618a168c60266593b3a25e993ff1f37"
  license "MIT"

  depends_on "python@3.12"

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/b3/81/4da04ced5a082363ecfa159c010d200ecbd959ae410c10c0264a38cac0f5/markdown_it_py-4.2.0-py3-none-any.whl"
    sha256 "9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl"
    sha256 "84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8"
  end

  resource "Pygments" do
    url "https://files.pythonhosted.org/packages/f4/7e/a72dd26f3b0f4f2bf1dd8923c85f7ceb43172af56d63c7383eb62b332364/pygments-2.20.0-py3-none-any.whl"
    sha256 "81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176"
  end

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      📄 Paper 卸载与清理提示：

      方法一（推荐）：直接在终端执行 `paper uninstall`，即可自动擦除所有配置、缓存并自动卸载 Homebrew 包自身。

      方法二：若已执行 `brew uninstall paper`，可手动运行以下命令擦除家目录残留配置：
        rm -rf ~/.paper ~/.paper-config.json

      （注意：你的 Markdown 文章原件不受任何影响，安全保留）
    EOS
  end

  test do
    system bin/"paper", "--version"
  end
end
