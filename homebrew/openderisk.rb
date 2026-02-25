class Openderisk < Formula
  desc "AI-Native Risk Intelligence Systems for application stability"
  homepage "https://github.com/derisk-ai/OpenDerisk"
  url "https://github.com/derisk-ai/OpenDerisk/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.10"
  depends_on "git"
  depends_on "uv"

  resource "uv" do
    url "https://github.com/astral-sh/uv/releases/download/0.5.0/uv-aarch64-apple-darwin.tar.gz"
    sha256 "PLACEHOLDER_UV_SHA256"
  end

  def install
    # Install uv if not present
    uv_bin = buildpath/"uv"
    resource("uv").stage do
      bin.install "uv"
      bin.install "uvx"
    end

    # Create wrapper scripts
    (bin/"openderisk").write <<~EOS
      #!/bin/bash
      export PATH="#{bin}:${PATH}"
      cd "#{libexec}" || exit 1
      exec uv run derisk "$@"
    EOS

    (bin/"openderisk-server").write <<~EOS
      #!/bin/bash
      export PATH="#{bin}:${PATH}"
      cd "#{libexec}" || exit 1
      exec uv run derisk start webserver "$@"
    EOS

    chmod 0755, bin/"openderisk"
    chmod 0755, bin/"openderisk-server"

    # Install Python dependencies
    system "uv", "sync", "--all-packages", "--frozen",
           "--extra", "base",
           "--extra", "proxy_openai",
           "--extra", "rag",
           "--extra", "storage_chromadb",
           "--extra", "derisks",
           "--extra", "storage_oss2",
           "--extra", "client",
           "--extra", "ext_base"

    # Copy project files
    libexec.install Dir["*"]

    # Create config directory
    (etc/"openderisk").mkpath
  end

  def post_install
    ohai "OpenDerisk installed successfully!"
    ohai "Next steps:"
    puts "  1. Configure API keys in: #{etc}/openderisk/derisk-proxy-aliyun.toml"
    puts "  2. Run: openderisk --help"
    puts "  3. Start server: openderisk-server"
    puts ""
    puts "Documentation: https://github.com/derisk-ai/OpenDerisk"
  end

  def caveats
    <<~EOS
      OpenDerisk Configuration:
      ========================
      
      1. Copy the example config and edit your API keys:
         cp #{opt_libexec}/configs/derisk-proxy-aliyun.toml ~/.config/openderisk/config.toml
      
      2. Edit the config file and add your API keys:
         nano ~/.config/openderisk/config.toml
      
      3. Start the server:
         openderisk-server
      
      4. Or use the CLI:
         openderisk
      
      Requirements:
      - Python >= 3.10 (installed via Homebrew)
      - API key for your LLM provider (DeepSeek, OpenAI, etc.)
    EOS
  end

  test do
    system "#{bin}/openderisk", "--version"
    system "#{bin}/openderisk-server", "--help"
  end
end
