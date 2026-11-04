"""Create the one-page practical-value PDF from its tracked Markdown source."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'docs/eda/05-analysis/checkpoint-2-practical-value.md'
TARGET = ROOT/'output/pdf/checkpoint-2-practical-value.pdf'


def build():
    fonts = Path('C:/Windows/Fonts')
    pdfmetrics.registerFont(TTFont('Body', str(fonts/'arial.ttf')))
    pdfmetrics.registerFont(TTFont('BodyBold', str(fonts/'arialbd.ttf')))
    body=ParagraphStyle('body',fontName='Body',fontSize=9.4,leading=13.2,spaceAfter=7,textColor=HexColor('#243945'),alignment=TA_LEFT)
    title=ParagraphStyle('title',parent=body,fontName='BodyBold',fontSize=22,leading=27,spaceAfter=9,textColor=HexColor('#075b66'))
    heading=ParagraphStyle('heading',parent=body,fontName='BodyBold',fontSize=11,leading=15,spaceBefore=6,spaceAfter=4,textColor=HexColor('#075b66'))
    subtitle=ParagraphStyle('subtitle',parent=body,fontSize=9,leading=13,spaceAfter=12,textColor=HexColor('#61747d'))
    story=[]
    blocks=SOURCE.read_text(encoding='utf-8').strip().split('\n\n')
    for i,block in enumerate(blocks):
        style=title if block.startswith('# ') else heading if block.startswith('## ') else subtitle if i==1 else body
        txt=block.removeprefix('## ').removeprefix('# ').replace('\n',' ')
        story.append(Paragraph(escape(txt),style))
    def footer(c,doc):
        c.setStrokeColor(HexColor('#bad2d6'));c.line(42,37,553,37)
        c.setFont('Body',8);c.setFillColor(HexColor('#61747d'))
        c.drawString(42,24,'Чекпойнт 2  |  4 ноября 2026  |  Предварительные результаты EDA')
        c.drawRightString(553,24,str(doc.page))
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    # invariant makes byte-level output stable for unchanged source and runtime.
    def stable_canvas(*a,**kw):
        kw['invariant']=1
        return canvas.Canvas(*a,**kw)
    doc=SimpleDocTemplate(str(TARGET),pagesize=(595.276,841.89),leftMargin=42,rightMargin=42,topMargin=34,bottomMargin=47,
        title='Предварительная версия: практическая ценность тьютора по профильному ЕГЭ',author='Проект №65')
    doc.build(story,onFirstPage=footer,onLaterPages=footer,canvasmaker=stable_canvas)
    from pypdf import PdfReader
    pdf=PdfReader(TARGET)
    assert len(pdf.pages)==1, f'Expected one page, got {len(pdf.pages)}'
    text=pdf.pages[0].extract_text()
    for token in ['1148','110','197','Практическая ценность','не измерены']:
        assert token in text, f'Missing PDF text: {token}'
    print(TARGET)


if __name__=='__main__':
    build()
