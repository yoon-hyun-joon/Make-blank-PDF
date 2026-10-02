import os
import re
import io
import html
import tempfile
import urllib.request
import streamlit as st
import pypdf
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ----------------------------------------------------------------------
# 1. Page Config
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="PDF 빈칸 학습지 자동 생성기",
    page_icon="📝",
    layout="centered"
)

# ----------------------------------------------------------------------
# 2. Font Registration
# ----------------------------------------------------------------------
@st.cache_resource
def setup_korean_font():
    font_paths = [
        "/usr/share/fonts/truetype/noto-cjk/NotoSansKR-Regular.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    ]
    font_name = "Helvetica"
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("KoreanFont", path))
                return "KoreanFont"
            except Exception:
                continue

    # Fallback: Download NanumGothic for cloud servers
    cached_font_path = os.path.join(tempfile.gettempdir(), "NanumGothic.ttf")
    if not os.path.exists(cached_font_path):
        try:
            url = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
            urllib.request.urlretrieve(url, cached_font_path)
        except Exception:
            pass

    if os.path.exists(cached_font_path):
        try:
            pdfmetrics.registerFont(TTFont("KoreanFont", cached_font_path))
            return "KoreanFont"
        except Exception:
            pass

    return font_name

FONT_NAME = setup_korean_font()

# ----------------------------------------------------------------------
# 3. Canvas with Running Header & Footer
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
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont(FONT_NAME, 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header
        self.drawString(54, 800, "PDF 자동 빈칸 학습지 (Blank Study Guide)")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 792, 541, 792)
        
        # Footer
        self.line(54, 45, 541, 45)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(541, 32, page_text)
        self.restoreState()

# ----------------------------------------------------------------------
# 4. Korean Postposition & Keyword Extractor
# ----------------------------------------------------------------------
def strip_josa(word):
    josa_list = [
        '에서의', '에의', '에서부터', '에대한', '에관한', '에의한', '으로의', '으로부터',
        '에서', '으로', '에게', '한테', '부터', '까지', '보다', '처럼', '으로서', '함으로써',
        '은', '는', '이', '가', '을', '를', '의', '에', '로', '과', '와', '도', '만'
    ]
    josa_list.sort(key=len, reverse=True)
    for j in josa_list:
        if word.endswith(j) and len(word) - len(j) >= 2:
            return word[:-len(j)]
    return word

STOPWORDS = {
    '그리고', '하지만', '또한', '따라서', '이에', '때문에', '통해', '위해', '경우', '대한',
    '통한', '관한', '의해', '속에', '아래', '위의', '모든', '있다', '없다', '한다', '된다',
    '이다', '것이다', '등', '및', '중', '그', '이', '저', '내용', '사항', '개념', '정의',
    '특징', '역할', '종류', '유형', '방법', '원리', '목적', '목표', '의미', '단계', '관련',
    '이상', '이하', '구분', '항목', '분류', '기준', '분야', '어떤', '이러한', '대해'
}

def extract_text_from_pdf_bytes(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            pages_text.append(t)
    return pages_text

def find_auto_keywords(pages_text, max_keywords=30):
    full_text = " ".join(pages_text)
    raw_tokens = re.findall(r'[가-힣a-zA-Z0-9]{2,15}', full_text)
    
    cleaned_words = []
    for token in raw_tokens:
        stem = strip_josa(token)
        if len(stem) >= 2 and stem not in STOPWORDS:
            cleaned_words.append(stem)
            
    freq = {}
    for w in cleaned_words:
        freq[w] = freq.get(w, 0) + 1
        
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_keywords]]

# ----------------------------------------------------------------------
# 5. PDF Generator Engine
# ----------------------------------------------------------------------
def build_blank_pdf(filename, pages_text, target_keywords):
    answer_key = []
    blank_counter = 1
    
    full_body = "\n\n".join(pages_text)
    
    # Sort keywords by length descending to match compound terms first
    sorted_kw = sorted(list(set(target_keywords)), key=len, reverse=True)
    
    for kw in sorted_kw:
        if kw in full_body:
            pattern = re.escape(kw)
            placeholder = f" [[BLANK_START_{blank_counter}]] [[BLANK_END]] "
            new_text, count = re.subn(pattern, placeholder, full_body, count=1)
            if count > 0:
                full_body = new_text
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
    title_style = ParagraphStyle('DocTitle', fontName=FONT_NAME, fontSize=18, leading=24, textColor=colors.HexColor('#1A365D'))
    subtitle_style = ParagraphStyle('DocSub', fontName=FONT_NAME, fontSize=9, leading=13, textColor=colors.HexColor('#718096'), spaceAfter=15)
    heading_style = ParagraphStyle('SecTitle', fontName=FONT_NAME, fontSize=12, leading=16, textColor=colors.HexColor('#1A365D'), spaceBefore=12, spaceAfter=8)
    body_style = ParagraphStyle('KoreanBody', fontName=FONT_NAME, fontSize=10, leading=16, textColor=colors.HexColor('#2D3748'))
    
    story = []
    story.append(Paragraph("<b>PDF 핵심 키워드 빈칸 학습지</b>", title_style))
    story.append(Paragraph(f"원문 문서: <b>{html.escape(filename)}</b> | 핵심 키워드가 빈칸 문제로 변환되었습니다.", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A365D'), spaceAfter=15))
    
    paragraphs = full_body.split('\n\n')
    for p in paragraphs:
        if p.strip():
            p_escaped = html.escape(p.strip())
            p_final = re.sub(
                r'\[\[BLANK_START_(\d+)\]\]\s*\[\[BLANK_END\]\]',
                r'<font color="#D32F2F"><b>[ \1. ____________ ]</b></font>',
                p_escaped
            )
            p_final = p_final.replace('\n', '<br/>')
            story.append(Paragraph(p_final, body_style))
            story.append(Spacer(1, 6))
            
    # Answer Key Table
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0'), spaceAfter=12))
    story.append(Paragraph("<b>정답지 (Answer Key)</b>", heading_style))
    story.append(Paragraph("빈칸 번호에 해당하는 정답 키워드 목록입니다.", subtitle_style))
    
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
    buffer.seek(0)
    return buffer.getvalue(), len(answer_key)

# ----------------------------------------------------------------------
# 6. Streamlit Web Interface
# ----------------------------------------------------------------------
def main():
    st.title("📝 PDF 빈칸 학습지 자동 생성기")
    st.markdown("PDF 파일을 업로드하면 핵심 키워드를 자동으로 빈칸 문제로 변환해 드립니다.")
    st.divider()

    uploaded_file = st.file_uploader("학습지로 만들 PDF 파일을 업로드하세요", type=["pdf"])

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        st.success(f"✅ 파일 업로드 완료: **{uploaded_file.name}**")

        mode = st.radio("키워드 설정 방식", ["자동 추출 모드", "수동 키워드 입력 모드"])

        target_keywords = []

        if mode == "자동 추출 모드":
            max_kw = st.slider("자동 추출할 키워드 개수", min_value=10, max_value=60, value=30, step=5)
            pages_text = extract_text_from_pdf_bytes(file_bytes)
            if pages_text:
                auto_kws = find_auto_keywords(pages_text, max_keywords=max_kw)
                st.info(f"🔍 자동 감지된 키워드 ({len(auto_kws)}개): " + ", ".join(auto_kws[:15]) + " ...")
                target_keywords = auto_kws
            else:
                st.warning("⚠️ PDF 문서에서 텍스트를 추출할 수 없습니다. 스캔 이미지 PDF인지 확인해 주세요.")
        else:
            user_input = st.text_area(
                "빈칸으로 만들 키워드를 쉼표(,)로 구분하여 입력하세요",
                placeholder="예: 법인세, 납세의무자, 실질적 관리장소, 익금, 손금"
            )
            if user_input:
                target_keywords = [k.strip() for k in user_input.split(",") if k.strip()]

        if st.button("🚀 빈칸 학습지 PDF 생성하기", type="primary"):
            if not target_keywords:
                st.error("⚠️ 키워드가 지정되지 않았습니다. 키워드를 입력하거나 선택해 주세요.")
            else:
                with st.spinner("PDF 학습지 생성 중..."):
                    try:
                        pages_text = extract_text_from_pdf_bytes(file_bytes)
                        if not pages_text:
                            st.error("⚠️ PDF 텍스트를 읽을 수 없습니다.")
                            return
                            
                        pdf_out_bytes, total_blanks = build_blank_pdf(
                            uploaded_file.name,
                            pages_text,
                            target_keywords
                        )
                        
                        st.balloons()
                        st.success(f"🎉 총 {total_blanks}개의 빈칸이 포함된 PDF 학습지가 생성되었습니다!")
                        
                        out_filename = f"{os.path.splitext(uploaded_file.name)[0]}_blank.pdf"
                        st.download_button(
                            label="📥 완성된 PDF 학습지 다운로드",
                            data=pdf_out_bytes,
                            file_name=out_filename,
                            mime="application/pdf"
                        )
                    except Exception as e:
                        st.error(f"❌ PDF 생성 중 오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    main()
