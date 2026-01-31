import json, re, os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter
from io import BytesIO

# ================= fonts =================
pdfmetrics.registerFont(TTFont("JP-Mincho", "fonts/IPAexMincho.ttf"))
pdfmetrics.registerFont(TTFont("JP-Gothic", "fonts/IPAexGothic.ttf"))
pdfmetrics.registerFont(TTFont("Times", "fonts/Times New Roman.ttf"))

PAGE_W, PAGE_H = A4
LEFT = 67
TOP = PAGE_H - 72
BOTTOM = 70
TEXT_W = PAGE_W - LEFT * 2
LINE_H = 19
SECTION_INDENT = 20
SAFE_BOTTOM = BOTTOM + 40
NO_LINE_START = {"、","｡", "。", ")", "）", "」", "』", "】", "！", "？", "_"}
NO_LINE_END = {"(", "（", "「"}
COVER_PATH = "cover-1-1.pdf"

# ================= utils =================

def strip_ruby(html):
    html = re.sub(r"</\s*ru\s*by\s*>", "</ruby>", html, flags=re.IGNORECASE)
    html = re.sub(r"<rp[^>]*>.*?</rp>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<rt[^>]*>.*?</rt>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"</?ruby[^>]*>", "", html, flags=re.IGNORECASE)
    return html


def strip_span(html):
    return re.sub(r"<span[^>]*>(.*?)</span>", r"\1", html, flags=re.DOTALL)


def normalize_passage_leading_number(html):
    return re.sub(r'^\s*(\(\d+\))\s*', r'\1\n', html)


def normalize_newlines(text: str) -> str:
    return re.sub(r"\n+", "\n", text)


def clean_text(html):
    return strip_ruby(strip_span(html))


def parse_underline(html):
    parts, buf = [], ""
    u = small = False
    i = 0
    while i < len(html):
        if html[i:i+3] == "<u>":
            if buf: parts.append((buf, u, small)); buf = ""
            u = True; i += 3
        elif html[i:i+4] == "</u>":
            if buf: parts.append((buf, u, small)); buf = ""
            u = False; i += 4
        elif html[i:i+7] == "<small>":
            if buf: parts.append((buf, u, small)); buf = ""
            small = True; i += 7
        elif html[i:i+8] == "</small>":
            if buf: parts.append((buf, u, small)); buf = ""
            small = False; i += 8
        else:
            buf += html[i]; i += 1
    if buf:
        parts.append((buf, u, small))
    return parts


def draw_rich(c, x, y, parts, max_w, size=11.3, font="JP-Mincho", wrap_indent=0):
    c.setFont(font, size)
    cx, cy, h = x, y, LINE_H
    prev_ch = None
    prev_w = 0

    for txt, u, small in parts:
        for ch in txt:
            cur = size - 2 if small else size

            w = c.stringWidth(ch, font, cur)

            if cx - x + w > max_w:
                if ch in NO_LINE_START:
                    pass
                else:
                    cx = x + wrap_indent
                    cy -= LINE_H
                    h += LINE_H

            c.setFont(font, cur)
            c.drawString(cx, cy, ch)

            if u:
                c.line(cx, cy - 2, cx + w, cy - 2)

            cx += w
            prev_ch = ch

    return h


def draw_qno(c, x, y, qno):
    c.setFont("JP-Gothic", 10.5)
    box_h = 13
    box_w = 17
    txt = str(qno)
    tw = c.stringWidth(txt, "JP-Gothic", 10.5)
    c.setLineWidth(0.8)
    c.rect(x, y - 2.6, box_w, box_h)
    c.drawString(
        x + (box_w - tw) / 2,
        y,
        txt
    )

    return box_w + 10


def normalize_question_breaks(html: str) -> str:
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = normalize_newlines(html)
    return html

def normalize_passage_ids(raw):
    if raw is None: return []
    return raw if isinstance(raw, list) else [raw]


def draw_passage(c, x, y, html):
    html = normalize_passage_leading_number(clean_text(html))
    html = strip_private_use_chars(html)
    html = re.sub(r"<div[^>]*>", "", html)
    html = re.sub(r"</?b\s*>", "", html, flags=re.I)
    html = re.sub(r"</div\s*>", "\n", html, flags=re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<hr\s*/?>", "\n", html, flags=re.I)

    PASSAGE_GAP = 6
    total = 3

    for line in html.split("\n"):
        if line.strip().lower().startswith("<center>"):
            center_text = re.sub(r"</?center\s*>", "", line, flags=re.I).strip()

            c.setFont("JP-Mincho", 11.3)
            c.drawCentredString(x + TEXT_W / 2, y,center_text)

            y -= LINE_H + PASSAGE_GAP
            total += LINE_H + PASSAGE_GAP
            continue
        
        if not line.strip():
            y -= LINE_H - 5
            total += LINE_H
            continue

        stripped = line.strip()

        # Check if line is wrapped in () or （）
        is_parenthesized = (
            (stripped.startswith("(") and stripped.endswith(")")) or
            (stripped.startswith("（") and stripped.endswith("）"))
        )

        is_note_line = (
            re.match(r"^\(注\d+\)", stripped) or
            re.match(r"^（注\d+）", stripped)
        )

        if is_note_line:
            note_size = 10.5
            h = draw_rich(
                c,
                x,
                y,
                parse_underline(line),
                TEXT_W,
                size=note_size
            )
            y -= h - 1
            total += h - 1
            continue

        # Exclude pure numeric markers like (1), （2）
        is_only_number = re.fullmatch(r"[（(]\d+[）)]", stripped) is not None
        is_churyaku = stripped in {"（中略）", "(中略)"}

        is_right_line = is_parenthesized and not is_only_number and not is_churyaku

        if is_right_line:
            cite_size = 10.5
            text_w = sum(
                pdfmetrics.stringWidth(ch, "JP-Mincho", cite_size)
                for ch in line
            )
            rx = x + max(TEXT_W - text_w, 0)
            h = draw_rich(
                c,
                rx,
                y,
                parse_underline(line),
                TEXT_W,
                size=cite_size
            )
        else:
            h = draw_rich(
                c,
                x,
                y,
                parse_underline(line),
                TEXT_W
            )

        y -= h + PASSAGE_GAP
        # ===== PAGE SAFETY CHECK (after passage line) =====
        if y < SAFE_BOTTOM:
            c.showPage()
            draw_header_footer(c, 0, "")
            y = TOP

        total += h + PASSAGE_GAP

    return total


def col_count(options):
    ml = max(len(v) for v in options.values())
    if ml > 15: return 1
    if ml >= 9: return 2
    return 4


def draw_header_footer(c, page_no, title):
    # Header: use Mincho for a more book-like look
    c.setFont("Times", 9)
    c.drawRightString(
        PAGE_W - LEFT + 20,
        PAGE_H - 25,
        f"www.phucduong.xyz  JLPT {title}"
    )

    # Footer (page number): slightly larger and bold-looking
    c.setFont("JP-Gothic", 10)
    c.drawCentredString(
        PAGE_W / 2,
        40,
        f"－ {page_no} －"
    )


def new_page(c, title, page_no):
    c.showPage()
    page_no += 1
    draw_header_footer(c, page_no, title)
    return page_no, TOP, 0


def contains_table(html: str) -> bool:
    return bool(re.search(r"<table\b", html, flags=re.I))


def strip_private_use_chars(text: str) -> str:
    # Xóa Unicode Private Use Area (ví dụ: 􀀀)
    return re.sub(r"[\uE000-\uF8FF]", "", text)


# ================= merge json =================

def load_and_merge_exam(json_path):
    base = re.sub(r"-\d+$", "", os.path.splitext(json_path)[0])
    merged = None

    for idx in (1, 2):
        path = f"{base}-{idx}.json"
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if merged is None:
            merged = data
        else:
            merged["sections"].extend(data.get("sections", []))
            existing = {p["pid"] for p in merged.get("passages", [])}
            for p in data.get("passages", []):
                if p["pid"] not in existing:
                    merged["passages"].append(p)

    if merged is None:
        raise FileNotFoundError(f"No valid exam files for {base}")

    return os.path.basename(base), merged

# ================= render =================

def render_exam(json_path):
    base, data = load_and_merge_exam(json_path)
    passages = {p["pid"]: p["passage"] for p in data.get("passages", [])}

    # Count how many questions belong to each passage GROUP
    group_question_count = {}
    for sec in data["sections"]:
        for q in sec["questions"]:
            group = tuple(normalize_passage_ids(q.get("pid")))
            if not group:
                continue
            group_question_count[group] = group_question_count.get(group, 0) + 1

    c = canvas.Canvas(f"{base}.pdf", pagesize=A4)
    page_no = 1
    draw_header_footer(c, page_no, base)
    y = TOP

    rendered_groups = set()
    qno_counter = 1
    last_passage_spans_pages = False

    for sec in data["sections"]:
        # ===== Section title =====
        y -= draw_rich(
            c,
            LEFT,
            y,
            parse_underline(clean_text(sec["sec"])),
            TEXT_W,
            font="JP-Gothic"
        ) + 20

        is_first_passage_in_section = True

        for q in sec["questions"]:
            group = tuple(normalize_passage_ids(q.get("pid")))

            # ===== PASSAGE GROUP =====
            if group and group not in rendered_groups:
                # Decide whether to page-break BEFORE the group
                # (skip break for first passage in section)
                if not is_first_passage_in_section and not last_passage_spans_pages:
                    page_no, y, _ = new_page(c, base, page_no)

                is_first_passage_in_section = False

                # Render all passages in the group consecutively (A, B, ...)
                skip_group_questions = False
                start_page_no = page_no
                for idx, pid in enumerate(group):
                    html = passages.get(pid, "")

                    # ===== SKIP PASSAGE IF CONTAINS TABLE =====
                    if contains_table(html):
                        rendered_groups.add(group)
                        page_no, y, _ = new_page(c, base, page_no)
                        skip_group_questions = True
                        break

                    y -= draw_passage(c, LEFT, y, html)

                    # Small gap between multiple passages (A / B)
                    if idx < len(group) - 1:
                        y -= LINE_H

                if not skip_group_questions:
                    rendered_groups.add(group)

                    # Passage có span sang trang khác không?
                    passage_spans_pages = page_no != start_page_no
                    last_passage_spans_pages = passage_spans_pages

                    # Passage đã span trang
                    if passage_spans_pages:
                        last_passage_spans_pages = True

                    if not passage_spans_pages and group_question_count.get(group, 0) >= 2:
                        page_no, y, _ = new_page(c, base, page_no)
                    else:
                        y -= LINE_H


            # ===== PAGE SAFETY CHECK (before question) =====
            if y < SAFE_BOTTOM and not last_passage_spans_pages:
                page_no, y, _ = new_page(c, base, page_no)

            # ===== QUESTION =====
            q_html = q["ques"]
            q_html = re.sub(r"<img[\s\S]*?(?:>|/>)", "", q_html, flags=re.I)
            q_html = re.sub(r"<img[\s\S]*", "", q_html, flags=re.I)
            q_text = clean_text(q_html)
            q_text = normalize_question_breaks(q_text)
            q_text = re.sub(r"^\d+．", "", q_text)

            box = draw_qno(c, LEFT, y, qno_counter)
            qno_counter += 1

            for line in q_text.split("\n"):
                if not line.strip():
                    y -= LINE_H
                    continue

                h = draw_rich(
                    c,
                    LEFT + box,
                    y,
                    parse_underline(line),
                    TEXT_W - box
                )
                y -= h

            # Gap between question and options
            y -= 5

            # ===== PAGE SAFETY CHECK (before options) =====
            if y < SAFE_BOTTOM:
                page_no, y, _ = new_page(c, base, page_no)

            # ===== OPTIONS =====
            cols = col_count(q["options"])
            if page_no >= 11:
                cols = 1
            col_w = TEXT_W / cols
            ox = LEFT + SECTION_INDENT - 6
            line_gap = 2 if cols in (2, 4) else 5

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
                y -= row_h + line_gap
                i += cols

            # Gap between (question + options) blocks
            y -= 17

        # New page after each section (except the last one)
        if sec is not data["sections"][-1]:
            page_no, y, _ = new_page(c, base, page_no)

    c.save()
    print(f"Exported {base}.pdf")


def make_cover_with_text(cover_pdf_path, text):
    cover_reader = PdfReader(cover_pdf_path)
    cover_page = cover_reader.pages[0]

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    x = PAGE_W / 2 - 10
    y = PAGE_H * 0.83

    c.setFont("JP-Gothic", 30)
    text = text.replace("-", " ", 1)
    c.drawCentredString(x, y, text)

    # c.setFont("Times", 12)
    # c.drawString(
    #     170,
    #     BOTTOM - 1,
    #     "www.phucduong.xyz"
    # )

    c.save()
    buf.seek(0)

    text_pdf = PdfReader(buf)
    cover_page.merge_page(text_pdf.pages[0])

    return cover_page


def merge_cover_with_rendered_pdf(rendered_pdf_path, cover_pdf_path, output_path):
    writer = PdfWriter()

    base_name = os.path.splitext(os.path.basename(rendered_pdf_path))[0]

    cover_page = make_cover_with_text(
        cover_pdf_path,
        f"({base_name})"
    )
    writer.add_page(cover_page)

    body_reader = PdfReader(rendered_pdf_path)
    for page in body_reader.pages:
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

def append_second_cover_with_text(rendered_pdf_path, end_cover_pdf_path, output_path):
    writer = PdfWriter()

    base_name = os.path.splitext(os.path.basename(ORIGINAL_PDF_NAME))[0]

    # đọc toàn bộ pdf đã có cover đầu
    body_reader = PdfReader(rendered_pdf_path)
    for page in body_reader.pages:
        writer.add_page(page)

    # đọc cover cuối
    end_cover_reader = PdfReader(end_cover_pdf_path)
    end_cover_page = end_cover_reader.pages[0]

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    x = PAGE_W / 2 - 8
    y = PAGE_H * 0.83

    c.setFont("JP-Gothic", 30)
    text = base_name.replace("-", " ", 1)
    c.drawCentredString(x, y, f"({text})")

    # c.setFont("Times", 12)
    # c.drawString(
    #     170,
    #     BOTTOM - 1,
    #     "www.phucduong.xyz"
    # )

    c.save()
    buf.seek(0)

    text_pdf = PdfReader(buf)
    end_cover_page.merge_page(text_pdf.pages[0])

    writer.add_page(end_cover_page)

    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    def json_sort_key(filename):
        name = os.path.splitext(filename)[0]

       # Split by dash and convert numeric parts
        parts = []
        for p in name.split("-"):
            if p.isdigit():
                parts.append(int(p))
            else:
                parts.append(p)
        return parts


    json_files = [
        f for f in os.listdir(".")
        if f.lower().endswith(".json")
    ]

    for f in sorted(json_files, key=json_sort_key):
        # Only render base or -1.json
        if re.search(r"-\d+\.json$", f) and not f.endswith("-1.json"):
            continue

        render_exam(f)

    # merge cover cho tất cả pdf vừa tạo
    for f in os.listdir("."):
        if not f.lower().endswith(".pdf"):
            continue
        if f == "cover-1-1.pdf":
            continue
        if f == "cover-1-2.pdf":
            continue

        # 1) prepend cover-1-1.pdf
        merge_cover_with_rendered_pdf(
            rendered_pdf_path=f,
            cover_pdf_path="cover-1-1.pdf",
            output_path="__tmp1__.pdf"
        )
        
        # 2) append cover-1-2.pdf
        ORIGINAL_PDF_NAME = f
        append_second_cover_with_text(
            rendered_pdf_path="__tmp1__.pdf",
            end_cover_pdf_path="cover-1-2.pdf",
            output_path="__tmp2__.pdf"
        )

        os.replace("__tmp2__.pdf", f)
        os.remove("__tmp1__.pdf")