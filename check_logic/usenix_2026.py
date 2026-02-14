try:
    # Try to use PDF.js wrapper (for browser/Pyodide environment)
    from check_logic import pdf_wrapper as fitz
except ImportError:
    # Fallback to PyMuPDF (for local testing)
    import pymupdf as fitz

import re
from collections import defaultdict

# ==========================================
# 1. 核心常量定义 (来源于 USENIX 脚本)
# ==========================================
TOTAL_HEIGHT = 11 * 72         # \paperheight
TOTAL_WIDTH = int(8.5 * 72)    # \paperwidth
TEXT_WIDTH = 7 * 72            # \textwidth
TEXT_HEIGHT = 9 * 72           # \textheight
TOP_OFFSET = 72                # 1 inch
MARGIN_WIDTH = (TOTAL_WIDTH - TEXT_WIDTH) / 2
OFFSET_TITLE = int(3.5 * 72)   # Title area offset

# 间距计算常量
ONE_EX = 4.5
ERROR_CORRECTION = 0.9
REQ_SPACING_SECTION = (2.3 * ONE_EX) * ERROR_CORRECTION
REQ_SPACING_SUBSECTION = (1.5 * ONE_EX) * ERROR_CORRECTION
REQ_SPACING_SECTION_ABOVE = (3.3 * ONE_EX) * ERROR_CORRECTION
REQ_SPACING_SUBSECTION_ABOVE = (3.05 * ONE_EX) * ERROR_CORRECTION

CAPTION_LINES_ABOVE = 7
CAPTION_LINES_BELOW = 0

TOLERANCE = 5
ANNOTATION_TOLERANCE = 5

ALLOWED_AREA = (
    MARGIN_WIDTH - ANNOTATION_TOLERANCE, 
    TOP_OFFSET - ANNOTATION_TOLERANCE, 
    TOTAL_WIDTH - MARGIN_WIDTH + ANNOTATION_TOLERANCE, 
    TOP_OFFSET + TEXT_HEIGHT + ANNOTATION_TOLERANCE
)

# ==========================================
# 2. 辅助工具函数
# ==========================================

async def count_lines(page, rect, invert=False, stop=30):
    """通过像素分析计算空白行数 (核心黑科技)"""
    try:
        # 获取灰度位图
        pix = await page.get_pixmap(clip=rect, colorspace=fitz.csGRAY, alpha=False)
        w, h, pixels = pix.width, pix.height, pix.samples

        # 将字节流转换为行数据
        lines = [pixels[offset:offset + w] for offset in range(0, w * h, w)]

        if invert:
            lines = lines[::-1]

        white_lines = 0
        for line in lines:
            if white_lines > stop:
                break
            # 检查该行是否足够"白" (阈值200/255)
            if sum([1 for i in range(w) if line[i] > 200]) >= w:
                white_lines += 1
            # else: break # 严格模式下遇到黑点即停，这里保持原逻辑松散检查

        if len(lines) < stop and white_lines == len(lines):
            return stop
        return white_lines
    except Exception:
        return 0

def excess_area(allowed, bbox):
    """计算超出允许区域的面积"""
    ax0, ay0, ax1, ay1 = allowed
    bx0, by0, bx1, by1 = bbox

    bbox_area = max(0, bx1 - bx0) * max(0, by1 - by0)

    ox0 = max(ax0, bx0)
    oy0 = max(ay0, by0)
    ox1 = min(ax1, bx1)
    oy1 = min(ay1, by1)

    overlap_area = 0
    if ox1 > ox0 and oy1 > oy0:
        overlap_area = (ox1 - ox0) * (oy1 - oy0)

    return bbox_area - overlap_area

# ==========================================
# 3. 具体检查逻辑函数
# ==========================================

def find_margins(doc, start=1):
    violations = []

    for page in doc:
        page_num = page.page_num
        if page_num < start:
            continue

        # 1. 检查页面物理尺寸
        if page_num == 1:
            if abs(page.rect.width - TOTAL_WIDTH) > 1 or abs(page.rect.height - TOTAL_HEIGHT) > 1:
                 violations.append({
                    "type": f"Invalid page size: {page.rect.width:.1f}x{page.rect.height:.1f} pt (Required: 8.5x11 inch)",
                    "page": page_num
                })

        text_dict = page.get_text("dict")
        
        # 2. 扫描所有文本块
        for block in text_dict["blocks"]:
            start_x, start_y, end_x, end_y = block["bbox"]
            if "lines" not in block: continue
            
            all_text = " ".join(span["text"] for line in block["lines"] for span in line["spans"])
            
            # 忽略页脚
            if "USENIX Association" in all_text: continue
            
            # 忽略页码 (简单判断)
            if all_text.strip().isdigit() and start_y > TOP_OFFSET + TEXT_HEIGHT: continue

            # 3. 检查第一页 Title 区域是否混入 Abstract
            if page_num == 1:
                # 标题区域内的文本
                if start_y < OFFSET_TITLE - TOLERANCE:
                    if re.search("abstract($|\\s)", all_text.lower()):
                         violations.append({
                            "type": "Abstract appears inside Title/Author box",
                            "page": page_num,
                            "text": all_text[:50]
                        })

            # 4. 检查是否超出版心 (Margins)
            exceeding = excess_area(ALLOWED_AREA, block["bbox"])
            if exceeding > 1: # 容忍 1pt 的误差
                violation_type = None
                
                # 判断具体是哪个方向超标
                if start_x < MARGIN_WIDTH - TOLERANCE:
                    # 再次确认是否只是行号
                    violating_lines = [l for l in block["lines"] if l["bbox"][0] < MARGIN_WIDTH - TOLERANCE]
                    line_texts = [s["text"] for l in violating_lines for s in l["spans"]]
                    if not all(t.strip().isdigit() for t in line_texts):
                        violation_type = "Margin Violation (Left)"
                
                elif end_x > TOTAL_WIDTH - MARGIN_WIDTH + TOLERANCE:
                    violation_type = "Margin Violation (Right)"
                elif start_y < TOP_OFFSET - TOLERANCE:
                    violation_type = "Margin Violation (Top)"
                elif int(end_y) > TOP_OFFSET + TEXT_HEIGHT + TOLERANCE:
                    violation_type = "Margin Violation (Bottom)"

                if violation_type:
                    violations.append({
                        "type": violation_type,
                        "page": page_num,
                        "text": all_text[:50],
                        "bbox": block["bbox"]
                    })
    return violations

async def find_sections(doc, start=1):
    violations = []

    for page in doc:
        page_num = page.page_num
        if page_num < start or page_num == 1:
            continue  # 跳过首页

        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            if "lines" not in block: continue

            # 筛选可能是标题的文本 (根据字号)
            potential_section_items = []
            for line in block["lines"]:
                for span in line["spans"]:
                    # USENIX 标题通常在 12pt 左右 (11.8 - 12.2)
                    if 11.8 < span["size"] < 12.2:
                        potential_section_items.append(span)

            if potential_section_items:
                joined_text = " ".join(span["text"] for span in potential_section_items)

                # 区分 Section 和 Subsection
                req_below = 0
                req_above = 0

                if re.match(r"\d+ ", joined_text): # "1 Introduction"
                    req_below = REQ_SPACING_SECTION
                    req_above = REQ_SPACING_SECTION_ABOVE
                elif re.match(r"\d+\.\d+", joined_text): # "2.1 Threat Model"
                    req_below = REQ_SPACING_SUBSECTION
                    req_above = REQ_SPACING_SUBSECTION_ABOVE
                else:
                    continue # 不是标准标题

                # 计算 BBox
                all_bboxes = [d['bbox'] for d in potential_section_items]
                x0 = min(b[0] for b in all_bboxes)
                y0 = min(b[1] for b in all_bboxes)
                x1 = max(b[2] for b in all_bboxes)
                y1 = max(b[3] for b in all_bboxes)

                # 检查下方间距
                rect_below = fitz.Rect(x0, y1 + 1, x1, y1 + int(req_below))
                lines_below = await count_lines(page, rect_below, stop=int(req_below))

                if lines_below < int(req_below):
                    violations.append({
                        "type": f"Spacing BELOW section too small (Found {lines_below}px, Need {int(req_below)}px)",
                        "page": page_num,
                        "text": joined_text[:50]
                    })

                # 检查上方间距
                rect_above = fitz.Rect(x0, y0 - int(req_above), x1, y0 - 1)
                lines_above = await count_lines(page, rect_above, invert=True, stop=int(req_above))

                if lines_above < int(req_above):
                    violations.append({
                        "type": f"Spacing ABOVE section too small (Found {lines_above}px, Need {int(req_above)}px)",
                        "page": page_num,
                        "text": joined_text[:50]
                    })
    return violations

async def find_captions(doc, start=1):
    violations = []

    for page in doc:
        page_num = page.page_num
        if page_num < start or page_num == 1:
            continue

        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
            if "lines" not in block: continue

            caption_items = []
            is_caption = False

            # 简化的 Caption 提取逻辑
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    # 检测 Figure/Table 关键字
                    if re.match(r"Fig[ure.]{1,3} \d+:", text) or re.match(r"Tab[le.]{1,2} \d+:", text):
                        is_caption = True
                        caption_items.append(span)
                    elif is_caption:
                        # 简单的连续性检查：如果同一个 Block 里后续文本字号差不多，视为 Caption 一部分
                        if caption_items and abs(span["size"] - caption_items[-1]["size"]) < 1:
                             caption_items.append(span)
                        else:
                            is_caption = False

            if caption_items:
                all_bboxes = [d['bbox'] for d in caption_items]
                x0 = min(b[0] for b in all_bboxes)
                y0 = min(b[1] for b in all_bboxes)
                x1 = max(b[2] for b in all_bboxes)
                y1 = max(b[3] for b in all_bboxes)

                # 检查 Caption 上方间距 (通常用于 Table)
                rect_above = fitz.Rect(x0, y0 - CAPTION_LINES_ABOVE, x1, y0 - 1)
                lines_above = await count_lines(page, rect_above, True, stop=10)

                if lines_above < CAPTION_LINES_ABOVE:
                     violations.append({
                        "type": f"Spacing ABOVE caption too small",
                        "page": page_num,
                        "text": caption_items[0]["text"][:30] + "..."
                    })

                # 检查 Caption 下方间距
                if CAPTION_LINES_BELOW > 0:
                    rect_below = fitz.Rect(x0, y1 + 3, x1, y1 + CAPTION_LINES_BELOW - 2)
                    lines_below = await count_lines(page, rect_below, False, stop=10)
                    if lines_below < CAPTION_LINES_BELOW:
                         violations.append({
                            "type": f"Spacing BELOW caption too small",
                            "page": page_num,
                            "text": caption_items[0]["text"][:30] + "..."
                        })
    return violations

def find_appendices(doc, start=1):
    found = {"Ethical": False, "Ethics": False, "Open": False}
    found_pages = {"Ethical": None, "Ethics": None, "Open": None}

    for page in doc:
        page_num = page.page_num
        if page_num < start:
            continue

        text_dict = page.get_text("dict")
        for block in text_dict["blocks"]:
             texts = [span["text"].lower() for line in block.get("lines", []) for span in line["spans"]]
             full_text = " ".join(texts)
             
             if "ethical considerations" in full_text:
                 found["Ethical"] = True
                 found_pages["Ethical"] = page_num
             elif "ethics considerations" in full_text:
                 found["Ethics"] = True
                 found_pages["Ethics"] = page_num
             elif "open science" in full_text:
                 found["Open"] = True
                 found_pages["Open"] = page_num

    violations = []
    # USENIX 2026 强制要求 Ethical Considerations 和 Open Science
    if not found["Ethical"]:
        if found["Ethics"]:
            violations.append({"type": "Wrong Section Title: Found 'Ethics Considerations', expected 'Ethical Considerations'", "page": found_pages["Ethics"]})
        else:
            violations.append({"type": "Missing Section: 'Ethical Considerations' not found", "page": None})
            
    if not found["Open"]:
        violations.append({"type": "Missing Section: 'Open Science' not found", "page": None})
        
    return violations

def font_stats(doc, start=1):
    stats = defaultdict(int)
    total_len = 0

    for page in doc:
        page_num = page.page_num
        if page_num < start:
            continue

        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block: continue
            for line in block["lines"]:
                for span in line.get("spans", []):
                    # 统计字数
                    stats[span["font"]] += len(span["text"])
                    total_len += len(span["text"])

    violations = []
    if total_len > 0:
        most_common = max(stats, key=stats.get)
        # 允许的字体白名单 (USENIX 常见字体)
        allowed_fonts = ['NimbusRomNo9L', 'TeXGyreTermes', 'STIXGeneral', 'Times', 'LiberationSerif']
        
        is_valid = any(allowed in most_common for allowed in allowed_fonts)
        if not is_valid:
             violations.append({
                "type": f"Main Font Warning: Detected '{most_common}'. USENIX usually requires Times/Nimbus/STIX.",
                "page": "All",
                "text": "Check your LaTeX compiler settings."
            })
            
    return violations

# ==========================================
# 4. 主入口函数 (供 Stlite 调用)
# ==========================================

async def run_check(uploaded_file):
    """
    接收 Streamlit UploadedFile 对象，返回检测结果字典
    """
    try:
        # 读取文件流
        file_bytes = uploaded_file.read()

        # 调试信息：文件大小
        import sys
        print(f"DEBUG: File size: {len(file_bytes)} bytes", file=sys.stderr)

        doc = await fitz.open(stream=file_bytes, filetype="pdf")

        print(f"DEBUG: PDF loaded successfully, {doc.num_pages} pages", file=sys.stderr)

        all_violations = []

        # 1. 页边距检查
        all_violations.extend(find_margins(doc, start=1))

        # 2. 章节间距检查
        all_violations.extend(await find_sections(doc, start=1))

        # 3. 标题间距检查
        all_violations.extend(await find_captions(doc, start=1))

        # 4. 附录完整性检查
        all_violations.extend(find_appendices(doc, start=1))

        # 5. 字体检查
        all_violations.extend(font_stats(doc, start=1))

        # 结果汇总
        return {
            "status": "finished",
            "violations": all_violations
        }

    except Exception as e:
        import traceback
        import sys
        # 打印完整的 traceback 到 stderr
        traceback.print_exc(file=sys.stderr)
        return {
            "status": "error",
            "message": f"An internal error occurred: {type(e).__name__}: {str(e)}"
        }
