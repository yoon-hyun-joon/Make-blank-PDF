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

# ---------------------------------------------------------
# 1. 한글 폰트 설정 (Fail-proof Korean Font Setup)
# ---------------------------------------------------------
@st.cache_resource
def setup_korean_font():
    # Candidate TTF paths across Linux, Windows, macOS
    candidate_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto-cjk/NotoSansKR-Regular.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
    ]
    
    # Recursive search in system font directories
    search_dirs = ['/usr/share/fonts', '/usr/local/share/fonts', os.path.expanduser('~/.fonts'), 'C:/Windows/Fonts', '/System/Library/Fonts']
    for sdir in search_dirs:
        if os.path.exists(sdir):
            for root, dirs, files in os.walk(sdir):
                for f in files:
                    if f.lower().endswith('.ttf') and any(k in f.lower() for k in ['nanum', 'notosanskr', 'malgun', 'gothic']):
                        candidate_paths.append(os.path.join(root, f))
                        
    for path in candidate_paths:
        if os.path.exists(path) and path.lower().endswith('.ttf'):
            try:
                pdfmetrics.registerFont(TTFont("KoreanFont", path))
                return "KoreanFont"
            except Exception:
                continue
                
    # Fallback: Download NanumGothic from Google Fonts repository if online
    try:
        tmp_font_path = os.path.join(tempfile.gettempdir(), "NanumGothic.ttf")
        if not os.path.exists(tmp_font_path):
            font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
            urllib.request.urlretrieve(font_url, tmp_font_path)
        pdfmetrics.registerFont(TTFont("KoreanFont", tmp_font_path))
        return "KoreanFont"
    except Exception:
        pass

    return "Helvetica"

FONT_NAME = setup_korean_font()

# ---------------------------------------------------------
# 2. Numbered Canvas for Header & Footer
# ---------------------------------------------------------
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
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(FONT_NAME, 9)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header
        self.drawString(54, 800, "PDF 핵심 키워드 빈칸 학습지 (Auto Blank Study Guide)")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 792, 541, 792)
        
        # Footer
        self.line(54, 50, 541, 50)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(541, 36, page_text)
        self.restoreState()

# ---------------------------------------------------------
# 3. Core Text Processing & PDF Generator
# ---------------------------------------------------------
def extract_text_from_pdf(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
    return pages_text

def extract_auto_keywords(pages_text, max_keywords=30):
    full_text = " ".join(pages_text)
    raw_words = re.findall(r'\b[가-힣a-zA-Z0-9]{2,12}\b', full_text)
    
    stop_words = {
        '그리고', '하지만', '또한', '따라서', '이에', '때문에', '통해', '위해',
        '경우', '대한', '통한', '관한', '의해', '속에', '아래', '위의', '모든',
        '있다', '없다', '한다', '된다', '이다', '것이다', '수', '등', '및',
        '내용', '방법', '특징', '의미', '구분', '원칙', '기준', '사항', '역할',
        '페이지', '학습지', '학습', '학문', '실제', '활동', '계획'
    }

    josa_list = ['의', '은', '는', '이', '가', '을', '를', '에', '에서', '로', '으로', '과', '와', '도', '만', '까지', '부터']
    
    freq = {}
    for w in raw_words:
        cleaned = w
        for j in sorted(josa_list, key=len, reverse=True):
            if cleaned.endswith(j) and len(cleaned) - len(j) >= 2:
                cleaned = cleaned[:-len(j)]
                break
        if cleaned not in stop_words and len(cleaned) >= 2:
            freq[cleaned] = freq.get(cleaned, 0) + 1
            
    sorted_words = sorted(freq.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    return [w[0] for w in sorted_words[:max_keywords]]

def generate_blank_pdf(filename, pages_text, target_keywords, max_occurrences_per_kw=2):
    answer_key = []
    blank_counter = 1
    
    sorted_keywords = sorted(list(set(target_keywords)), key=len, reverse=True)
    kw_counts = {kw: 0 for kw in sorted_keywords}
    
    processed_pages = []
    for page_text in pages_text:
        escaped_page = html.escape(page_text)
        token_map = {}
        
        for kw in sorted_keywords:
            if kw_counts[kw] >= max_occurrences_per_kw:
                continue
                
            escaped_kw = html.escape(kw)
            if escaped_kw in escaped_page:
                pattern = re.escape(escaped_kw)
                
                def replacer(match):
                    nonlocal blank_counter
                    current_kw = kw
                    if kw_counts[current_kw] >= max_occurrences_per_kw:
                        return match.group(0)
                        
                    token = f"___BLANK_TOKEN_{blank_counter}___"
                    blank_html = f'<font color="#D32F2F"><b>[ {blank_counter}. ____________ ]</b></font>'
                    token_map[token] = blank_html
                    answer_key.append((blank_counter, current_kw))
                    blank_counter += 1
                    kw_counts[current_kw] += 1
                    return token
                    
                escaped_page = re.sub(pattern, replacer, escaped_page)
                
        for token, blank_html in token_map.items():
            escaped_page = escaped_page.replace(token, blank_html)
            
        processed_pages.append(escaped_page)
        
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
        fontName=FONT_NAME,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor('#1A365D'),
        spaceAfter=10
    )
    heading_style = ParagraphStyle(
        'SecHeading',
        fontName=FONT_NAME,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2B6CB0'),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'BodyKorean',
        fontName=FONT_NAME,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor('#2D3748'),
        spaceAfter=6
    )
    
    story = []
    story.append(Paragraph("📄 PDF 핵심 키워드 빈칸 학습지", title_style))
    story.append(Paragraph(f"원문 파일: <b>{html.escape(filename)}</b> | 주요 핵심 개념이 빈칸 문제로 재구성되었습니다.", body_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0'), spaceAfter=12))
    
    for idx, page_content in enumerate(processed_pages, 1):
        story.append(Paragraph(f"<b>[ Page {idx} ]</b>", heading_style))
        lines = page_content.split('\n')
        for line in lines:
            if line.strip():
                story.append(Paragraph(line.strip(), body_style))
        story.append(Spacer(1, 8))
        
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#2B6CB0'), spaceBefore=15, spaceAfter=12))
    story.append(Paragraph("🗝️ 정답지 (Answer Key)", title_style))
    
    if answer_key:
        table_data = [["번호", "정답 키워드", "번호", "정답 키워드"]]
        for i in range(0, len(answer_key), 2):
            k1, v1 = answer_key[i]
            r1 = [f"{k1}.", v1]
            if i + 1 < len(answer_key):
                k2, v2 = answer_key[i+1]
                r2 = [f"{k2}.", v2]
            else:
                r2 = ["", ""]
            table_data.append(r1 + r2)
            
        t = Table(table_data, colWidths=[40, 200, 40, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EDF2F7')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#2D3748')),
            ('FONTNAME', (0,0), (-1,-1), FONT_NAME),
            ('FONTSIZE', (0,0), (-1,-1), 9.5),
            ('ALIGN', (0,0), (0,-1), 'CENTER'),
            ('ALIGN', (2,0), (2,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E0')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t)
        
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer, len(answer_key), answer_key

# ---------------------------------------------------------
# 4. Streamlit UI App
# ---------------------------------------------------------
def main():
    st.set_page_config(
        page_title="PDF 빈칸 학습지 생성기",
        page_icon="✏️",
        layout="wide"
    )
    
    st.title("✏️ PDF 빈칸 학습지 자동 생성기")
    st.markdown("임의의 PDF 문서를 업로드하면 핵심 키워드를 추출하여 **빈칸 문제 + 정답지 PDF 학습지**로 만들어 드립니다.")
    st.divider()
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("1. PDF 파일 업로드")
        uploaded_file = st.file_uploader("학습지로 만들 PDF 파일을 업로드하세요", type=["pdf"])
        
        if uploaded_file is not None:
            pdf_bytes = uploaded_file.read()
            pages_text = extract_text_from_pdf(pdf_bytes)
            total_chars = sum(len(p) for p in pages_text)
            
            if total_chars == 0:
                st.error("⚠️ 업로드된 PDF에서 텍스트를 읽을 수 없습니다. (스캔된 이미지 PDF이거나 보안 설정이 적용된 문서일 수 있습니다.)")
            else:
                st.success(f"📄 총 **{len(pages_text)}페이지** (총 {total_chars:,}자) 텍스트 추출 완료")
                
                st.subheader("2. 키워드 설정")
                mode = st.radio("키워드 선정 방식", ["자동 추출 모드", "수동 키워드 입력 모드"])
                
                target_keywords = []
                if mode == "자동 추출 모드":
                    max_kw_num = st.slider("자동 추출할 핵심 키워드 개수", min_value=5, max_value=60, value=25, step=5)
                    max_occ = st.slider("키워드당 최대 빈칸 생성 횟수", min_value=1, max_value=5, value=2, step=1)
                    target_keywords = extract_auto_keywords(pages_text, max_keywords=max_kw_num)
                    
                    with st.expander("🔍 자동 추출된 핵심 키워드 목록 보기", expanded=True):
                        st.write(", ".join(f"`{kw}`" for kw in target_keywords))
                else:
                    kw_input = st.text_area("빈칸으로 만들 키워드를 쉼표(,)로 구분하여 입력하세요", "교육과정, 타일러, 경험중심, 학문중심")
                    max_occ = st.slider("키워드당 최대 빈칸 생성 횟수", min_value=1, max_value=5, value=2, step=1)
                    target_keywords = [k.strip() for k in kw_input.split(",") if k.strip()]
                    st.info(f"🎯 지정된 키워드 ({len(target_keywords)}개): " + ", ".join(f"`{k}`" for k in target_keywords))

    with col2:
        st.subheader("3. 결과 미리보기 및 PDF 생성")
        if uploaded_file is not None and total_chars > 0 and target_keywords:
            if st.button("🚀 빈칸 학습지 PDF 생성하기", type="primary", use_container_width=True):
                with st.spinner("PDF 학습지를 생성하는 중입니다..."):
                    out_buffer, total_blanks, answer_key = generate_blank_pdf(
                        uploaded_file.name,
                        pages_text,
                        target_keywords,
                        max_occurrences_per_kw=max_occ
                    )
                    
                st.balloons()
                st.success(f"🎉 총 **{total_blanks}개**의 빈칸이 포함된 학습지 PDF가 성공적으로 완성되었습니다!")
                
                st.download_button(
                    label="📥 빈칸 학습지 PDF 다운로드",
                    data=out_buffer.getvalue(),
                    file_name=f"blank_study_guide_{uploaded_file.name}",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
                
                with st.expander("🗝️ 정답지 (Answer Key) 미리보기", expanded=True):
                    if answer_key:
                        st.dataframe(
                            [{"번호": f"{k}.", "정답 키워드": v} for k, v in answer_key],
                            use_container_width=True
                        )
        else:
            st.info("👈 왼쪽에서 PDF 파일을 업로드하고 키워드를 확인한 후 생성 버튼을 눌러주세요.")

if __name__ == "__main__":
    main()
