"""Yoklama listesinden Türkçe karakter destekli, çok sayfalı PDF üretir."""

import os
from datetime import datetime
from uuid import uuid4
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _register_fonts():
    """Türkçe karakter destekli fontları kaydet."""
    font_paths = [
        os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf"),
        os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSans.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("TurkishFont", path))
                return "TurkishFont"
            except Exception:
                continue

    raise RuntimeError("Türkçe PDF fontu bulunamadı: DejaVuSans.ttf gereklidir.")


def _attendance_table(attendance_data, font_name, table_width):
    """Adları güvenli metne çevir; uzun listelerde başlığı her sayfada tekrarla."""
    table_data = [["Sıra", "Öğrenci No", "Ad Soyad", "Durum", "Saat"]]
    cell_style = ParagraphStyle("CellStyle", fontName=font_name, fontSize=9, leading=12)

    for i, student in enumerate(attendance_data, 1):
        status_text = "VAR" if student.get("status") == "present" else "YOK"
        time_text = student.get("time") or "-"
        table_data.append(
            [
                str(i),
                Paragraph(escape(str(student.get("id", "N/A"))), cell_style),
                Paragraph(escape(str(student.get("name", ""))), cell_style),
                status_text,
                str(time_text),
            ]
        )

    table = Table(
        table_data,
        colWidths=[table_width * ratio / 17 for ratio in [1.2, 3, 7.1, 2.5, 3.2]],
        repeatRows=1,
        hAlign="LEFT",
    )

    style = TableStyle(
        [
            # Başlık satırı
            ("FONTNAME", (0, 0), (-1, 0), font_name),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6c5ce7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            # Veri satırları
            ("FONTNAME", (0, 1), (-1, -1), font_name),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),  # Sıra
            ("ALIGN", (1, 1), (1, -1), "CENTER"),  # No
            ("ALIGN", (3, 1), (3, -1), "CENTER"),  # Durum
            ("ALIGN", (4, 1), (4, -1), "CENTER"),  # Saat
            ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
            ("TOPPADDING", (0, 1), (-1, -1), 6),
            # Kenarlıklar
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
            ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor("#6c5ce7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
    )

    # Uzun listelerde satır takibini kolaylaştır.
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8f8ff"))

    # VAR/YOK renklendirme
    for i in range(1, len(table_data)):
        if table_data[i][3] == "VAR":
            style.add("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#00b894"))
        else:
            style.add("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#e17055"))

    table.setStyle(style)
    return table


def generate_pdf(attendance_data, output_path=None, class_name="Sınıf", session_date=None):
    """Verilen yoklama kopyasını dosyaya veya BytesIO akışına yaz.

    attendance_data: id, name, status ve time alanlarını içeren öğrenci listesi.
    output_path: yol veya yazılabilir akış; verilmezse pdf_reports altında oluşturulur.
    session_date: yoklamanın YYYY-MM-DD tarihi; rapor indirme tarihinden ayrı tutulur.
    Dönüş değeri, kullanılan çıktı yolu veya akıştır.
    """
    if output_path is None:
        reports_dir = os.path.join(os.path.dirname(__file__), "pdf_reports")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = os.path.join(reports_dir, f"yoklama_{timestamp}_{uuid4().hex[:8]}.pdf")

    font_name = _register_fonts()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    elements = []

    title_style = ParagraphStyle(
        "TitleStyle",
        fontName=font_name,
        fontSize=22,
        leading=28,
        alignment=1,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=5 * mm,
    )

    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#666666"),
        spaceAfter=8 * mm,
    )

    info_style = ParagraphStyle(
        "InfoStyle",
        fontName=font_name,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#333333"),
        spaceAfter=3 * mm,
    )

    elements.append(Paragraph("YOKLAMA RAPORU", title_style))

    now = datetime.now()
    date_str = (
        datetime.strptime(session_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        if session_date
        else now.strftime("%d.%m.%Y")
    )
    time_str = now.strftime("%H:%M")
    elements.append(Paragraph(f"{escape(class_name)} | {date_str} | {time_str}", subtitle_style))

    elements.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#6c5ce7"), spaceAfter=8 * mm)
    )

    total = len(attendance_data)
    present = sum(1 for s in attendance_data if s.get("status") == "present")
    absent = total - present
    rate = (present / total * 100) if total > 0 else 0

    elements.append(
        Paragraph(
            f"Toplam: {total} | Katılan: {present} | Katılmayan: {absent} | "
            f"Katılım Oranı: %{rate:.1f}",
            info_style,
        )
    )
    elements.append(Spacer(1, 5 * mm))

    # ReportLab çerçevesinin iki yanındaki 6 punto boşluğu hesaba kat.
    elements.append(_attendance_table(attendance_data, font_name, doc.width - 12))

    elements.append(Spacer(1, 10 * mm))
    footer_style = ParagraphStyle(
        "FooterStyle",
        fontName=font_name,
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor("#999999"),
    )
    elements.append(
        Paragraph(
            f"Bu rapor YoklamaX tarafından oluşturulmuştur. | {now.strftime('%d.%m.%Y %H:%M:%S')}",
            footer_style,
        )
    )

    def page_number(canvas, document):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(A4[0] / 2, cm, f"Sayfa {document.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=page_number, onLaterPages=page_number)
    return output_path
