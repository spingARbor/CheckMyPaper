import os
import json

# ==========================================
# 前端交互逻辑 (Streamlit App)
# ==========================================
MAIN_PY_CONTENT = """
import streamlit as st
import os
import importlib
import sys
import asyncio

# 设置页面配置
st.set_page_config(
    page_title="PaperLint - Privacy First Checker",
    page_icon="🛡️",
    layout="centered"
)

# 自定义 CSS 优化界面
st.markdown(\"\"\"
    <style>
    .stAlert { padding: 0.5rem; }
    .reportview-container { margin-top: -2em; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1rem; font-weight: 600; }
    </style>
\"\"\", unsafe_allow_html=True)

st.title("🛡️ PaperLint-Suite")
st.markdown("### 隐私保护的论文格式在线检查工具")

st.info(\"\"\"
**🔒 隐私承诺 (Privacy First)**
此工具基于 **WebAssembly** 技术构建。
您的论文文件**完全在您的浏览器本地内存中处理**，绝不会上传至任何服务器。
\"\"\")

# 1. 自动扫描 check_logic 目录下的会议脚本
# 注意：在 Stlite 虚拟文件系统中，我们通过 os.listdir 动态获取
try:
    available_scripts = [f.replace('.py', '') for f in os.listdir('check_logic') if f.endswith('.py') and not f.startswith('__')]
except FileNotFoundError:
    available_scripts = []
    st.error("未找到检查脚本目录，请检查构建配置。")

# 2. 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")
    selected_conf = st.selectbox("选择会议/期刊规范", available_scripts, index=0 if available_scripts else None)
    st.markdown("---")
    st.caption("Version: 1.0.0 (Wasm)")

# 3. 主上传区
uploaded_file = st.file_uploader("上传论文 (仅限 PDF)", type=['pdf'])

if uploaded_file and selected_conf:
    st.divider()
    
    # 动态导入对应的检查模块
    module_name = f"check_logic.{selected_conf}"
    
    try:
        checker_module = importlib.import_module(module_name)
        
        if st.button(f"开始检查 ({selected_conf})", type="primary"):
            with st.spinner("正在本地分析文档结构 (这可能需要几秒钟)..."):
                # 调用核心检查函数 (使用 asyncio 运行异步函数)
                # 注意：文件指针在读取后需要重置，但 fitz.open(stream=...) 处理字节流，这里传递 file object
                uploaded_file.seek(0)
                results = asyncio.run(checker_module.run_check(uploaded_file))
            
            # --- 结果展示逻辑 ---
            if results["status"] == "error":
                st.error(f"分析过程中发生错误: {results.get('message')}")
            else:
                violations = results["violations"]
                
                if not violations:
                    st.balloons()
                    st.success("🎉 完美！未检测到明显的格式违规。")
                else:
                    st.warning(f"⚠️ 检测到 {len(violations)} 个潜在问题")
                    
                    # 按类型分组展示 (可选)
                    for i, v in enumerate(violations, 1):
                        # 根据违规类型选择图标
                        icon = "🔴" if "Margin" in v['type'] else "🟡"
                        
                        label = f"{icon} Page {v.get('page', '?')}: {v['type']}"
                        
                        with st.expander(label):
                            col1, col2 = st.columns([1, 3])
                            with col1:
                                st.caption("位置 / 区域")
                                st.code(str(v.get('bbox', 'N/A')))
                            with col2:
                                st.caption("相关文本片段")
                                st.info(v.get('text', 'N/A'))
                                
    except ModuleNotFoundError:
        st.error(f"无法加载脚本: {module_name}")
    except Exception as e:
        st.error(f"运行时错误: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

elif not selected_conf:
    st.warning("暂无可用检查脚本，请联系管理员添加。")
"""

def generate_build():
    files_dict = {}

    # 1. 写入主程序 main.py
    files_dict["main.py"] = MAIN_PY_CONTENT

    # 2. 遍历读取 check_logic 文件夹
    # 确保你的本地目录结构正确
    logic_dir = "check_logic"
    if not os.path.exists(logic_dir):
        os.makedirs(logic_dir)
        print(f"Warning: Created empty directory '{logic_dir}'. Please put usenix_2026.py inside.")

    for filename in os.listdir(logic_dir):
        if filename.endswith(".py"):
            path = os.path.join(logic_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                # 关键：保留目录结构 check_logic/filename.py
                files_dict[f"check_logic/{filename}"] = f.read()
                print(f"Packed: {filename}")

    # 3. 生成 JSON 并注入 HTML
    files_json = json.dumps(files_dict)
    
    try:
        with open("template.html", "r", encoding="utf-8") as f:
            template = f.read()
            
        final_html = template.replace("{{FILES_JSON}}", files_json)

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(final_html)
        
        print("✅ Build Success: index.html generated.")
    except FileNotFoundError:
        print("❌ Error: template.html not found.")

if __name__ == "__main__":
    generate_build()
