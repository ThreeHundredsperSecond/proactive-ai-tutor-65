"""Build the one-page practical-value brief from its Markdown source."""
import re
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/eda/05-analysis/checkpoint-2-practical-value.md'
TARGET = ROOT / 'output/pdf/checkpoint-2-practical-value.pdf'
INK, TEAL, MUTED = map(HexColor, ['#223B44', '#086B70', '#647780'])
WIDTH = 511.276
FONTS = {
    'Body': ['C:/Windows/Fonts/arial.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf', '/Library/Fonts/Arial.ttf'],
    'BodyBold': ['C:/Windows/Fonts/arialbd.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/Library/Fonts/Arial Bold.ttf'],
}

def inline(text):
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escape(text))

class Cycle(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = WIDTH, 53

    def draw(self):
        c, gap = self.canv, 17
        box = (self.width - gap * 3) / 4
        labels = ['Задача', 'Помощь|с шагом', 'Тренировка|действия', 'Целая задача']
        for i, label in enumerate(labels):
            x = i * (box + gap)
            c.setFillColor(HexColor('#EDF6F4'))
            c.roundRect(x, 9, box, 36, 9, fill=1, stroke=0)
            c.setFillColor(TEAL)
            c.setFont('BodyBold', 8.7)
            lines = label.split('|')
            for j, line in enumerate(lines):
                c.drawCentredString(x + box / 2, (24 if len(lines)==1 else 29) - j * 11, line)
            if i < 3:
                a, y = x + box + 4, 27
                c.setStrokeColor(TEAL)
                c.setLineWidth(.8)
                c.line(a, y, a + 9, y)
                c.line(a + 6, y + 3, a + 9, y)
                c.line(a + 6, y - 3, a + 9, y)

def build():
    for name, candidates in FONTS.items():
        file = next((f for f in candidates if Path(f).is_file()), None)
        assert file, f'Arial not found for {name}: {candidates}'
        pdfmetrics.registerFont(TTFont(name, file))
    addMapping('Body', 0, 0, 'Body')
    addMapping('Body', 1, 0, 'BodyBold')
    body = ParagraphStyle('body', fontName='Body', fontSize=9.4, leading=12.6, spaceAfter=5, textColor=INK)
    title = ParagraphStyle('title', parent=body, fontName='BodyBold', fontSize=22, leading=26, spaceAfter=4, textColor=TEAL)
    heading = ParagraphStyle('heading', parent=body, fontName='BodyBold', fontSize=10.8, leading=14, spaceBefore=6, spaceAfter=4, textColor=TEAL, keepWithNext=True)
    subtitle = ParagraphStyle('subtitle', parent=body, fontSize=9, leading=12, spaceAfter=8, textColor=MUTED)
    bullet = ParagraphStyle('bullet', parent=body, leftIndent=11, bulletIndent=0, spaceAfter=3)
    note = ParagraphStyle('note', parent=body, fontSize=8, leading=11, textColor=MUTED, spaceBefore=6, spaceAfter=0)
    story = []
    blocks = SOURCE.read_text(encoding='utf-8').strip().split('\n\n')
    for i, block in enumerate(blocks):
        if block.startswith('СХЕМА:'):
            story.append(Cycle())
        elif block.startswith('- '):
            for line in block.splitlines():
                story.append(Paragraph(inline(line.removeprefix('- ')), bullet, bulletText='•'))
        else:
            style = title if block.startswith('# ') else heading if block.startswith('## ') else subtitle if i == 1 else note if block.startswith('Основание:') else body
            text = block.removeprefix('## ').removeprefix('# ').replace('\n', ' ')
            story.append(Paragraph(inline(text), style))
    def footer(c, doc):
        c.setStrokeColor(HexColor('#D4E3E4'))
        c.line(42, 33, 553.276, 33)
        c.setFillColor(MUTED)
        c.setFont('Body', 8)
        c.drawString(42, 20, 'Практическая ценность  /  Чекпойнт 2')
        c.drawRightString(553.276, 20, 'Проект №65  ·  2026/27')
    def stable_canvas(*args, **kwargs):
        kwargs['invariant'] = 1
        return canvas.Canvas(*args, **kwargs)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(TARGET), pagesize=(595.276, 841.89), leftMargin=42, rightMargin=42, topMargin=30, bottomMargin=44, title='Практическая ценность: тьютор по профильному ЕГЭ', author='Проект №65')
    doc.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=stable_canvas)
    from pypdf import PdfReader
    pdf = PdfReader(TARGET)
    assert len(pdf.pages) == 1, f'Expected one page, got {len(pdf.pages)}'
    text = pdf.pages[0].extract_text()
    for token in ['1148', '315', '312', '20', '280', '71%', '83%', 'KC', 'Целая задача', 'рабочей версией',
                  'Трудности и их серьёзность', 'Как оценивать качество']:
        assert token in text, f'Missing text: {token}'
    print(TARGET)

if __name__ == '__main__':
    build()
