class Paper < Formula
  desc "超级极简零依赖 SSG 博客引擎与 CLI 工具"
  homepage "https://github.com/username/paper-blog"
  url "https://github.com/username/paper-blog/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on "python@3"

  def install
    bin.install "paper.py" => "paper"
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
    system "#{bin}/paper"
  end
end
