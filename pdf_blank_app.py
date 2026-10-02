import os
import re
import io
import html
import tempfile
import urllib.request
import streamlit as st
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ----------------------------------------------------------------------
# 1. Page Config
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="PDF 키워드 빈칸 학습지 생성기",
    page_icon="📝",
    layout="centered"
)

# ----------------------------------------------------------------------
# 2. Korean Font Setup for ReportLab
# ----------------------------------------------------------------------
@st.cache_resource
def get_korean_font():
    font_name = "KoreanFont"
    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except KeyError:
        pass

    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto-cjk/NotoSansKR-Regular.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception:
                continue

    # Streamlit Cloud 환경 등 폰트 미설치 시 온라인 자동 다운로드
    tmp_font = os.path.join(tempfile.gettempdir(), "NanumGothic.ttf")
    if not os.path.exists(tmp_font):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
            urllib.request.urlretrieve(url, tmp_font)
        except Exception:
            pass

    if os.path.exists(tmp_font):
        try:
            pdfmetrics.registerFont(TTFont(font_name, tmp_font))
            return font_name
        except Exception:
            pass

    return "Helvetica"

# ----------------------------------------------------------------------
# 3. Canvas with Header & Page Number
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        font_name = get_korean_font()
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages, font_name)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count, font_name):
        self.saveState()
        self.setFont(font_name, 8)
        self.setFillColor(colors.HexColor("#666666"))
        
        # Header
        self.drawString(54, 800, "PDF 자동 빈칸 학습지 (Blank Study Guide)")
        self.setStrokeColor(colors.HexColor("#DDDDDD"))
        self.setLineWidth(0.5)
        self.line(54, 792, 541, 792)
        
        # Footer
        self.line(54, 45, 541, 45)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(541, 32, page_text)
        self.restoreState()

# ----------------------------------------------------------------------
# 4. Core Logic Functions
# ----------------------------------------------------------------------
def extract_text_from_pdf_bytes(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(text)
    return pages_text

def find_auto_keywords(text, blank_ratio=0.15):
    # 특수 괄호 및 따옴표 안의 핵심 단어
    bracket_terms = re.findall(r'[\'\"「『\(\<\[]([가-힣a-zA-Z0-9\s]{2,15})[\'\"」』\)\>\]]', text)
    # 한글 단어
    korean_words = re.findall(r'\b[가-힣]{2,10}\b', text)
    
    stopwords = {
        "그리고", "하지만", "또한", "따라서", "경우", "이상", "이하", "통해", "의한",
        "대해", "위해", "관한", "대한", "관련", "가지", "모든", "어떤", "이러한", "때문",
        "사항", "내용", "기준", "방법", "원칙", "구분", "의미", "특징", "역할", "필요",
        "하여", "에서", "으로", "로써", "이다", "있다", "없다", "위한", "통하여", "때문에"
    }

    candidates = []
    for w in bracket_terms + korean_words:
        w_clean = w.strip()
        if len(w_clean) >= 2 and w_clean not in stopwords:
            candidates.append(w_clean)

    if not candidates:
        return []

    freq = {}
    for c in candidates:
        freq[c] = freq.get(c, 0) + 1

    sorted_candidates = sorted(freq.keys(), key=lambda x: (freq[x], len(x)), reverse=True)
    max_blanks = max(5, int(len(sorted_candidates) * blank_ratio))
    return sorted_candidates[:max_blanks]

def build_pdf_bytes(filename, raw_text, keywords):
    font_name = get_korean_font()
    
    answer_key = []
    blank_counter = 1
    processed_text = raw_text

    # 키워드 길이에 따라 내림차순 정렬 (긴 키워드 우선 치환)
    sorted_kw = sorted(set(keywords), key=len, reverse=True)

    for kw in sorted_kw:
        if kw in processed_text:
            pattern = re.escape(kw)
            placeholder = f"___BLANK_{blank_counter}___"
            new_text, count = re.subn(pattern, placeholder, processed_text, count=1)
            if count > 0:
                processed_text = new_text
                answer_key.append((blank_counter, kw))
                blank_counter += 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor('#1A237E'),
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#555555'),
        spaceAfter=15
    )

    body_style = ParagraphStyle(
        'BodyKorean',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        leading=16,
        textColor=colors.HexColor('#222222'),
        spaceAfter=10
    )

    section_heading = ParagraphStyle(
        'SecHeading',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#1A237E'),
        spaceBefore=15,
        spaceAfter=8
    )

    story = []

    safe_filename = html.escape(filename)
    story.append(Paragraph("<b>PDF 핵심 키워드 빈칸 학습지</b>", title_style))
    story.append(Paragraph(f"원문 파일: <b>{safe_filename}</b> | 핵심 키워드가 빈칸으로 자동 변환된 학습지입니다.", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A237E'), spaceAfter=15))

    paragraphs = processed_text.split('\n\n')
    for p in paragraphs:
        p_strip = p.strip()
        if p_strip:
            # HTML 특수문자 이스케이프 처리 후 개행 적용
            p_escaped = html.escape(p_strip).replace('\n', '<br/>')
            # 플레이스홀더를 빨간색 빈칸 XML 태그로 변경
            p_html = re.sub(
                r'___BLANK_(\d+)___',
                r'<font color="#D32F2F"><b>[ \1. ____________ ]</b></font>',
                p_escaped
            )
            story.append(Paragraph(p_html, body_style))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CCCCCC'), spaceAfter=15))
    story.append(Paragraph("<b>정답지 (Answer Key)</b>", section_heading))

    table_data = []
    for i in range(0, len(answer_key), 2):
        k1, v1 = answer_key[i]
        cell1 = Paragraph(f"<b>{k1}.</b> {html.escape(v1)}", body_style)
        if i + 1 < len(answer_key):
            k2, v2 = answer_key[i+1]
            cell2 = Paragraph(f"<b>{k2}.</b> {html.escape(v2)}", body_style)
        else:
            cell2 = Paragraph("", body_style)
        table_data.append([cell1, cell2])

    if table_data:
        t = Table(table_data, colWidths=[240, 240])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()

# ----------------------------------------------------------------------
# 5. Streamlit UI App
# ----------------------------------------------------------------------
def main():
    st.title("📝 PDF 빈칸 학습지 자동 생성기")
    st.write("PDF 문서를 업로드하면 핵심 키워드를 자동으로 빈칸 문제로 만들어 줍니다.")

    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        st.success(f"파일명: {uploaded_file.name} (업로드 완료)")

        mode = st.radio("키워드 지정 방식", ["자동 추출 모드", "직접 입력 모드"])

        target_keywords = []
        blank_ratio = 0.15

        if mode == "자동 추출 모드":
            blank_ratio = st.slider("빈칸 비율 선택", min_value=0.05, max_value=0.30, value=0.15, step=0.05)
        else:
            user_kw_input = st.text_input("빈칸으로 만들 키워드를 쉼표(,)로 구분하여 입력하세요", placeholder="예: 교육과정, 잠재적 교육과정, 타일러")
            if user_kw_input:
                target_keywords = [k.strip() for k in user_kw_input.split(",") if k.strip()]

        if st.button("🚀 빈칸 학습지 생성하기", type="primary"):
            with st.spinner("PDF 텍스트 추출 및 빈칸 학습지 생성 중..."):
                try:
                    pages = extract_text_from_pdf_bytes(file_bytes)
                    full_text = "\n\n".join(pages)

                    if not full_text.strip():
                        st.error("⚠️ PDF에서 텍스트를 추출할 수 없습니다. (스캔된 이미지 전용 PDF인 경우 텍스트 선택이 불가능할 수 있습니다.)")
                    else:
                        if mode == "자동 추출 모드":
                            target_keywords = find_auto_keywords(full_text, blank_ratio=blank_ratio)

                        if not target_keywords:
                            st.warning("⚠️ 문서에서 적절한 키워드를 찾지 못했습니다. 직접 입력 모드를 사용해 보세요.")
                        else:
                            pdf_out_bytes = build_pdf_bytes(uploaded_file.name, full_text, target_keywords)
                            
                            st.success("🎉 빈칸 학습지 생성이 완료되었습니다!")
                            st.write(f"총 **{len(target_keywords)}개**의 핵심 키워드가 빈칸으로 변환되었습니다.")
                            
                            output_filename = f"{os.path.splitext(uploaded_file.name)[0]}_blank.pdf"
                            st.download_button(
                                label="📥 완성된 PDF 학습지 다운로드",
                                data=pdf_out_bytes,
                                file_name=output_filename,
                                mime="application/pdf"
                            )
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    main()
