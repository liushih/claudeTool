"""把 Markdown 渲染成 Word / PPT。"""

from __future__ import annotations

from pathlib import Path

SECTIONS_PER_SLIDE = 6


def parse_markdown(text: str) -> tuple[str, list[str], list[tuple[str, list[str]]]]:
    title = ""
    intro: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            current = (line[3:].strip(), [])
            sections.append(current)
            continue
        if not line or line.startswith("<!--"):
            continue
        entry = line[2:].strip() if line.startswith("- ") else line
        if current is None:
            intro.append(entry)
        else:
            current[1].append(entry)

    return title, intro, sections


def render_docx(md_text: str, path: Path, title: str) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading(title, 0)
    _, intro, sections = parse_markdown(md_text)
    for line in intro:
        doc.add_paragraph(line)
    for heading, lines in sections:
        doc.add_heading(heading, level=1)
        for line in lines:
            doc.add_paragraph(line, style="List Bullet")
    doc.save(str(path))


def render_pptx(md_text: str, path: Path, title: str, subtitle: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    _title, intro, sections = parse_markdown(md_text)

    cover = prs.slides.add_slide(blank)
    cover_box = cover.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(11.7), Inches(1.4))
    cover_box.text_frame.text = title
    sub_box = cover.shapes.add_textbox(Inches(0.8), Inches(3.9), Inches(11.7), Inches(0.8))
    sub_box.text_frame.text = subtitle
    if intro:
        note_box = cover.shapes.add_textbox(Inches(0.8), Inches(4.8), Inches(11.7), Inches(1.4))
        note_frame = note_box.text_frame
        note_frame.word_wrap = True
        note_frame.text = "\n".join(intro)

    for heading, lines in sections:
        chunks = [lines[i:i + SECTIONS_PER_SLIDE] for i in range(0, len(lines), SECTIONS_PER_SLIDE)] or [[]]
        for index, chunk in enumerate(chunks):
            slide = prs.slides.add_slide(blank)
            head = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9))
            head.text_frame.text = heading if index == 0 else f"{heading}（续）"

            body = slide.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(5.4))
            frame = body.text_frame
            frame.word_wrap = True
            for line_index, line in enumerate(chunk):
                paragraph = frame.paragraphs[0] if line_index == 0 else frame.add_paragraph()
                paragraph.text = f"• {line}"

    prs.save(str(path))
