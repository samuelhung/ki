"""逐页 OCR 识别整本教材 PDF，输出全部文本"""
import sys, os, time, base64, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(override=True)

import fitz
from zhiji_backend.ingest.pdf_ocr import ocr_page

PDF_PATH = Path("/Users/mrh/Documents/Projects/KnowledgeIntelligence/data/study/3517596a-e7ab-46e6-a32f-e68d5bbdb20e/raw/original.pdf")
OUT_PATH = Path("/tmp/textbook_ocr.json")

def main():
    doc = fitz.open(str(PDF_PATH))
    total = doc.page_count
    print(f"总页数: {total}", flush=True)
    
    pages_text = []
    for i in range(total):
        page = doc[i]
        # Render page to PNG at 200 DPI
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("ascii")
        
        # OCR
        text = ocr_page(b64)
        pages_text.append({"page": i + 1, "text": text})
        
        pct = (i + 1) / total * 100
        print(f"  [{i+1}/{total}] {pct:.0f}% - {len(text)} chars", flush=True)
        
        # Rate limit: 1 QPS
        if i < total - 1:
            time.sleep(1.05)
    
    doc.close()
    
    # Save
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(pages_text, f, ensure_ascii=False, indent=2)
    
    full_text = "\n\n--- PAGE BREAK ---\n\n".join(
        f"[第{p['page']}页]\n{p['text']}" for p in pages_text
    )
    print(f"\n完成！共 {len(full_text)} 字符，已保存到 {OUT_PATH}")

if __name__ == "__main__":
    main()
