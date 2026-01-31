import json
import os
import re
from html import unescape
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.colors import Color
from reportlab.lib.utils import simpleSplit


# ================= PAGE CONFIG =================
PAGE_W, PAGE_H = A4

LEFT = 65
RIGHT = 65
TOP = PAGE_H - 72
BOTTOM_LIMIT = 30 * mm

ROW_H = 14
LINE_GAP = 14
SECTION_GAP = 10
TEXT_GAP = 8

MAX_COL = 10
LABEL_W = 18 * mm
TABLE_W = PAGE_W - LEFT - RIGHT - LABEL_W
COL_W = TABLE_W / MAX_COL
# ===============================================


# ---------- WATERMARK ----------
def draw_watermark(c):
    c.saveState()
    c.translate(PAGE_W / 2, PAGE_H / 2 + 20)
    c.rotate(20)
    c.setFillColor(Color(0.95, 0.95, 0.95))
    c.setFont("Helvetica-Bold", 60)
    c.drawCentredString(0, 0, "PHUC DUONG")
    c.restoreState()


# ---------- BULLET ----------
def draw_bullet_text(c, x, y, text):
    r = 4
    cy = y + 3.8
    c.circle(x + r, cy, r, stroke=0, fill=1)
    c.drawString(x + r * 2 + 4, y, text)


# ---------- FILE GROUP ----------
def group_exam_files():
    groups = {}
    for f in os.listdir("."):
        if not f.endswith(".json"):
            continue
        m = re.match(r"(.*)-([123])\.json$", f)
        if not m:
            continue
        base = m.group(1)
        part = int(m.group(2))
        groups.setdefault(base, {})[part] = f

    return {
        base: parts
        for base, parts in groups.items()
        if {1, 2, 3}.issubset(parts.keys())
    }


# ---------- DATA ----------
def load_exam(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chunk_questions(questions, size):
    for i in range(0, len(questions), size):
        yield questions[i:i + size]


def clean_expl(text):
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    return unescape(text.strip())


# ---------- DRAW TITLE ----------
def draw_center_title(c, text, y):
    c.setFont("HeiseiKakuGo-W5", 20)
    c.drawCentredString(PAGE_W / 2, y, text)


# ---------- ANSWER TABLE ----------
def draw_answer_table(c, x, y, section_no, questions, labels):
    col_count = len(questions)
    table_x = x + LABEL_W
    table_w_used = COL_W * col_count

    top = y
    bottom = y - ROW_H * 2
    right = table_x + table_w_used

    c.setFont("HeiseiKakuGo-W5", 11)
    c.drawString(x, y - ROW_H * 0.9, f"問題{section_no}")

    c.setLineWidth(0.6)
    c.rect(table_x, bottom, table_w_used, ROW_H * 2)

    for i in range(1, col_count):
        vx = table_x + COL_W * i
        c.line(vx, bottom, vx, top)

    c.line(table_x, y - ROW_H, right, y - ROW_H)

    c.setFont("HeiseiKakuGo-W5", 10)
    for i, q in enumerate(questions):
        cx = table_x + COL_W * i + COL_W / 2
        c.drawCentredString(cx, y - ROW_H * 0.75, labels[i])
        c.drawCentredString(cx, y - ROW_H * 1.75, str(q["answer"]))

    return bottom - SECTION_GAP


# ---------- PART 1 & 2 ----------
def render_reading_parts(c, files, y):
    section_no = 1
    qno = 1

    for file in files:
        data = load_exam(file)
        for section in data["sections"]:
            questions = sorted(section["questions"], key=lambda x: x["qid"])
            for chunk in chunk_questions(questions, MAX_COL):
                if y < BOTTOM_LIMIT:
                    c.showPage()
                    # draw_watermark(c)
                    y = TOP

                labels = [str(qno + i) for i in range(len(chunk))]
                y = draw_answer_table(c, LEFT, y, section_no, chunk, labels)
                qno += len(chunk)

            section_no += 1
    return y


# ---------- PART 3 ANSWER ----------
def render_listening_answer(c, file, y):
    c.showPage()
    # draw_watermark(c)
    y = TOP

    c.setFont("HeiseiKakuGo-W5", 11)
    draw_bullet_text(c, LEFT, y, "聴解")
    y -= LINE_GAP + 10

    data = load_exam(file)
    sections = data["sections"]
    last_idx = len(sections) - 1

    section_no = 1
    for idx, section in enumerate(sections):
        questions = section["questions"]
        total = len(questions)

        if idx == last_idx and total >= 3:
            base = total - 1
            labels = [
                str(i + 1) if i < base - 1 else f"{base}-{i - (base - 1) + 1}"
                for i in range(total)
            ]
        else:
            labels = [str(i + 1) for i in range(total)]

        for chunk in chunk_questions(questions, MAX_COL):
            if y < BOTTOM_LIMIT:
                c.showPage()
                # draw_watermark(c)
                y = TOP

            cl = labels[:len(chunk)]
            labels = labels[len(chunk):]
            y = draw_answer_table(c, LEFT, y, section_no, chunk, cl)

        section_no += 1
    return y


# ---------- MAIN ----------
def create_pdfs():
    exam_groups = group_exam_files()

    for base, parts in exam_groups.items():
        output_pdf = f"{base}-A.pdf"
        c = canvas.Canvas(output_pdf, pagesize=A4)
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

        # draw_watermark(c)
        y = TOP

        draw_center_title(c, "正答表", y)
        y -= LINE_GAP * 2 + 10

        c.setFont("HeiseiKakuGo-W5", 11)
        draw_bullet_text(c, LEFT, y, "言語知識（文字・語彙・文法）・読解")
        y -= LINE_GAP + 10

        y = render_reading_parts(c, [parts[1], parts[2]], y)
        y = render_listening_answer(c, parts[3], y)


        c.save()
        print(f"Exported: {output_pdf}")


if __name__ == "__main__":
    create_pdfs()
