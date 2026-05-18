class Siberia < Formula
  include Language::Python::Virtualenv

  desc "Supply-chain hardening for pip, uv, npm, pnpm, and Cargo"
  homepage "https://github.com/cavanaug/siberia"
  url "https://github.com/cavanaug/siberia/releases/download/v0.1.0/siberia-0.1.0.tar.gz"
  sha256 "REPLACE_WITH_GITHUB_RELEASE_TARBALL_SHA256"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage: siberia", shell_output("#{bin}/siberia --help")
  end
end
