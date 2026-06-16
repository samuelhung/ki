"""辅导中心 — HTML 讲题稿模板引擎"""

# ── 语文讲题稿 HTML（灰蓝配色） ──

CHINESE_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: "PingFang SC", "Hiragino Sans GB", sans-serif; font-size: 14px; line-height: 1.9; color: #1a1a1a; max-width: 700px; margin: 0 auto; }}
  h1 {{ font-size: 22px; text-align: center; margin: 24px 0 32px; color: #111; }}
  h2 {{ font-size: 18px; margin: 28px 0 14px; padding-bottom: 6px; border-bottom: 2px solid #e0e0e0; color: #333; }}
  h3 {{ font-size: 16px; margin: 20px 0 10px; color: #444; }}
  h4 {{ font-size: 14px; margin: 12px 0 6px; color: #555; }}
  .passage {{ background: #fafafa; padding: 20px; border-radius: 8px; margin: 16px 0; line-height: 2; }}
  .question-block {{ margin: 24px 0; padding-left: 12px; border-left: 3px solid #d0d0d0; }}
  .answer {{ background: #f6f9fc; padding: 14px 18px; border-radius: 6px; margin: 12px 0; border-left: 3px solid #4a90d9; }}
  .answer-label {{ font-size: 12px; color: #4a90d9; font-weight: 600; margin-bottom: 6px; }}
  .detail {{ margin: 10px 0; padding: 12px 14px; background: #fefefe; border-radius: 4px; }}
  .detail-item {{ margin: 6px 0; }}
  .mistake {{ background: #fff8f0; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #e8962e; }}
  .tip {{ background: #f0f7f4; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #5ba88c; }}
  .clean-answers {{ margin-top: 32px; padding: 16px 20px; background: #fafafa; border-radius: 8px; }}
  .clean-answers h3 {{ margin-top: 0; }}
  .clean-answers p {{ margin: 6px 0; padding-left: 1em; text-indent: -1em; }}
  @media print {{ body {{ font-size: 13px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""

# ── 数学讲题稿 HTML（蓝绿配色） ──

MATH_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 16mm 14mm; }}
  body {{ font-family: "PingFang SC", "Hiragino Sans GB", sans-serif; font-size: 14px; line-height: 1.9; color: #1a1a1a; max-width: 700px; margin: 0 auto; }}
  h1 {{ font-size: 22px; text-align: center; margin: 24px 0 32px; }}
  h2 {{ font-size: 18px; margin: 28px 0 14px; padding-bottom: 6px; border-bottom: 2px solid #e0e0e0; }}
  h3 {{ font-size: 16px; margin: 20px 0 10px; }}
  .problem {{ background: #fafafa; padding: 16px 20px; border-radius: 8px; margin: 16px 0; }}
  .steps {{ margin: 12px 0; padding: 14px 18px; background: #f6f9fc; border-radius: 6px; border-left: 3px solid #3b82f6; }}
  .step {{ margin: 8px 0; }}
  .formula {{ font-family: "Times New Roman", serif; font-size: 15px; background: #eef2ff; padding: 2px 8px; border-radius: 3px; }}
  .answer-box {{ background: #f0fdf4; padding: 12px 16px; border-radius: 6px; margin: 10px 0; border-left: 3px solid #22c55e; }}
  .final-answer {{ font-size: 18px; font-weight: 700; color: #166534; }}
  .mistake {{ background: #fff8f0; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #e8962e; }}
  .tip {{ background: #f0f7f4; padding: 10px 14px; border-radius: 4px; margin: 8px 0; border-left: 3px solid #5ba88c; }}
  @media print {{ body {{ font-size: 13px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""

# ── 英语讲题稿 HTML（参照 Unit4 范本，青蓝配色） ──

ENGLISH_STUDY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4; margin: 12mm 11mm; }}
  body {{ font-family: "Times New Roman", "PingFang SC", sans-serif; font-size: 13px; line-height: 1.8; color: #1a1a1a; max-width: 750px; margin: 0 auto; }}
  h1 {{ font-size: 20px; text-align: center; margin: 20px 0 24px; color: #16829c; }}
  h2 {{ font-size: 16px; margin: 24px 0 12px; color: #16829c; border-bottom: 1px solid #95d8e1; padding-bottom: 4px; }}
  h3 {{ font-size: 14px; margin: 16px 0 8px; color: #0d5c6e; }}
  .sheet {{ background: #f8fcfd; padding: 18px; border: 1px solid #95d8e1; border-radius: 6px; margin: 16px 0; }}
  .q {{ background: #f0f4f5; padding: 12px 14px; margin: 10px 0; border-radius: 4px; border-left: 3px solid #76c7d3; }}
  .answer {{ background: #e6f9f2; padding: 12px 14px; margin: 10px 0; border-radius: 4px; border-left: 3px solid #5ba88c; }}
  .answer-label {{ font-size: 11px; color: #5ba88c; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }}
  .tip {{ background: #fff8e8; padding: 10px 14px; margin: 8px 0; border-radius: 4px; border-left: 3px solid #e8962e; }}
  .tip-label {{ font-size: 11px; color: #e8962e; font-weight: 700; }}
  .en {{ font-family: "Times New Roman", serif; font-style: italic; }}
  .cn {{ color: #555; }}
  .vocab {{ display: inline-block; background: #eef2ff; padding: 1px 6px; border-radius: 3px; margin: 2px; font-size: 12px; }}
  .clean-answers {{ margin-top: 28px; padding: 14px 18px; background: #fafafa; border-radius: 6px; }}
  @media print {{ body {{ font-size: 12px; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
{body}
</body>
</html>"""


def render_chinese_html(title: str, body_html: str) -> str:
    return CHINESE_STUDY_HTML.format(title=title, body=body_html)


def render_math_html(title: str, body_html: str) -> str:
    return MATH_STUDY_HTML.format(title=title, body=body_html)


def render_english_html(title: str, body_html: str) -> str:
    return ENGLISH_STUDY_HTML.format(title=title, body=body_html)


def render_html(subject: str, title: str, body_html: str) -> str:
    """根据学科选择对应 HTML 模板"""
    if subject == "英语":
        return render_english_html(title, body_html)
    elif subject == "数学":
        return render_math_html(title, body_html)
    else:
        return render_chinese_html(title, body_html)
