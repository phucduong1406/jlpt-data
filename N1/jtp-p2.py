import json, re, os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter

# ===== FONT =====
pdfmetrics.registerFont(TTFont("JP-Mincho", "fonts/IPAexMincho.ttf"))
pdfmetrics.registerFont(TTFont("JP-Gothic", "fonts/IPAexGothic.ttf"))
pdfmetrics.registerFont(TTFont("Times", "fonts/Times New Roman.ttf"))

# ===== PAGE CONFIG =====
PAGE_W, PAGE_H = A4
LEFT = 67
TOP = PAGE_H - 72
BOTTOM = 70
TEXT_W = PAGE_W - LEFT * 2
LINE_H = 18
SECTION_INDENT = 20
SAFE_BOTTOM = BOTTOM + 40

NO_LINE_START = {"、","｡", "。", ")", "）", "」", "』", "】", "！", "？", "_"}

# ===== UTILS =====
def clean_text(html):
    html = re.sub(r"<rp[^>]*>.*?</rp>", "", html, flags=re.DOTALL)
    html = re.sub(r"<rt[^>]*>.*?</rt>", "", html, flags=re.DOTALL)
    html = re.sub(r"</?ruby[^>]*>", "", html)
    html = re.sub(r"<span[^>]*>(.*?)</span>", r"\1", html)
    return html

def parse_underline(html):
    parts, buf = [], ""
    u = False
    i = 0
    while i < len(html):
        if html[i:i+3] == "<u>":
            if buf: parts.append((buf, u)); buf = ""
            u = True; i += 3
        elif html[i:i+4] == "</u>":
            if buf: parts.append((buf, u)); buf = ""
            u = False; i += 4
        else:
            buf += html[i]; i += 1
    if buf:
        parts.append((buf, u))
    return parts

def draw_rich(c, x, y, parts, max_w, size=11.3, font="JP-Mincho", wrap_indent=0):
    c.setFont(font, size)
    cx, cy, h = x, y, LINE_H

    for txt, underline in parts:
        for ch in txt:
            w = c.stringWidth(ch, font, size)
            if cx - x + w > max_w and ch not in NO_LINE_START:
                cx = x + wrap_indent
                cy -= LINE_H
                h += LINE_H

            c.drawString(cx, cy, ch)
            if underline:
                c.line(cx, cy - 2, cx + w, cy - 2)
            cx += w
    return h

def draw_header_footer(c, page_no, title):
    c.setFont("Times", 9)
    c.drawRightString(
        PAGE_W - LEFT + 20,
        PAGE_H - 25,
        f"www.phucduong.xyz  JLPT {title}"
    )
    c.setFont("JP-Gothic", 10)
    c.drawCentredString(PAGE_W / 2, 40, f"－ {page_no} －")

def new_page(c, title, page_no):
    c.showPage()
    page_no += 1
    draw_header_footer(c, page_no, title)
    return page_no, TOP

def col_count(options):
    ml = max(len(v) for v in options.values())
    if ml > 18: return 1
    return 2

# ===== LOAD PART 3 ONLY =====
def load_part3(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

# ===== RENDER PART 3 EXAM =====
def render_part3_exam(json_path):
    base = os.path.splitext(os.path.basename(json_path))[0].replace("-3", "")
    data = load_part3(json_path)

    c = canvas.Canvas(f"{base}-L.pdf", pagesize=A4)
    page_no = 1
    draw_header_footer(c, page_no, base)
    y = TOP

    rendered_passages = set()

    for sec_idx, sec in enumerate(data["sections"]):

        # bottom safe: nếu không đủ chỗ cho section mới thì sang trang
        if y < SAFE_BOTTOM + 60:
            page_no, y = new_page(c, base, page_no)

        # section title
        y -= draw_rich(
            c,
            LEFT,
            y,
            parse_underline(clean_text(sec["sec"])),
            TEXT_W,
            font="JP-Gothic"
        ) + 5

        for q in sec["questions"]:

            pid = q.get("pid")
            if pid is not None and pid not in rendered_passages:
                for p in data.get("passages", []):
                    if p.get("pid") == pid:
                        passage_text = clean_text(p.get("passage", ""))
                        if passage_text:
                            if y < SAFE_BOTTOM:
                                page_no, y = new_page(c, base, page_no)

                            # split passage by <br/> into separate lines
                            for line in re.split(r"<br\s*/?>", p.get("passage", "")):
                                line = clean_text(line)
                                if not line.strip():
                                    y -= LINE_H
                                    continue

                                if y < SAFE_BOTTOM:
                                    page_no, y = new_page(c, base, page_no)

                                h = draw_rich(
                                    c,
                                    LEFT,
                                    y,
                                    parse_underline(line),
                                    TEXT_W,
                                    font="JP-Gothic"
                                )
                                y -= h + 14

                            y -= 14  # khoảng cách sau passage

                        rendered_passages.add(pid)
                        break

            options = q.get("options", {})
            if options and all(str(v).strip().isdigit() for v in options.values()):
                continue

            if y < SAFE_BOTTOM:
                page_no, y = new_page(c, base, page_no)

            # question
            q_html = re.sub(r"^\d+．", "", q["ques"])
            q_text = clean_text(q_html)

            h = draw_rich(
                c,
                LEFT,
                y,
                parse_underline(q_text),
                TEXT_W
            )
            y -= h + 4

            # options
            cols = col_count(q["options"])
            col_w = TEXT_W / cols
            ox = LEFT + SECTION_INDENT - 6

            options = list(q["options"].values())
            i = 0
            while i < len(options):
                row = options[i:i + cols]
                row_h = 0
                for col, opt in enumerate(row):
                    h = draw_rich(
                        c,
                        ox + col * col_w,
                        y,
                        parse_underline(clean_text(opt)),
                        col_w - 10,
                        wrap_indent=14
                    )
                    row_h = max(row_h, h)
                y -= row_h + 4
                i += cols

            y -= 17
        

        # ngắt trang sau section 1
        if sec_idx == 0:
            page_no, y = new_page(c, base, page_no)

        # page_no, y = new_page(c, base, page_no)

    c.save()
    print(f"Exported {base}-L.pdf")

# ===== MAIN =====
if __name__ == "__main__":
    for f in os.listdir("."):
        if f.endswith("-3.json"):
            render_part3_exam(f)