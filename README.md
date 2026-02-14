# 🛡️ PaperLint-Suite (Online & Private)

PaperLint 是一个专注于学术论文格式合规性的在线检查工具。

它旨在帮助作者在提交前快速发现常见的格式错误（如页边距溢出、字体未嵌入、标题间距违规等），从而降低 Desk Rejection 的风险。

👉 **[点击这里开始使用](https://你的用户名.github.io/你的仓库名/)**

## ✨ 核心特性

* **100% 隐私保护**：采用 WebAssembly (Wasm) 技术，核心检查逻辑完全在您的浏览器本地运行。您的 PDF 文件**永远不会**被上传到任何服务器。
* **多会议支持**：模块化设计，目前支持：
    * USENIX Security 2026 (Beta)
* **即时反馈**：无需安装 Python 环境，拖拽 PDF 即可查看详细的违规报告。
* **像素级精度**：基于 PyMuPDF 进行渲染分析，比单纯的文本提取更准确地捕捉布局问题。

## 🛠️ 本地开发

如果您想为本项目贡献新的会议检查脚本：

1.  克隆仓库：
    ```bash
    git clone [https://github.com/your-username/PaperLint-Suite.git](https://github.com/your-username/PaperLint-Suite.git)
    cd PaperLint-Suite
    ```

2.  在 `check_logic/` 目录下添加新的脚本（例如 `acm_2024.py`），确保包含 `run_check(file)` 函数。

3.  运行构建脚本生成本地测试页面：
    ```bash
    python build.py
    # 然后在浏览器打开生成的 index.html
    ```

## 📄 许可证

MIT License
