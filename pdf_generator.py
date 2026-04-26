"""
PDF Rapor Oluşturma Modülü
Yoklama verilerini profesyonel bir PDF raporuna dönüştürür.
Türkçe karakter desteği (DejaVuSans font) içerir.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _register_fonts():
    """Türkçe karakter destekli fontları kaydet."""
    font_paths = [
        os.path.join(os.path.dirname(__file__), 'fonts', 'DejaVuSans.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('TurkishFont', path))
                return 'TurkishFont'
            except Exception:
                continue

    # Fallback: sistem fontunu kullan
    return 'Helvetica'


def generate_pdf(attendance_data, output_path=None, class_name="Sınıf"):
    """
    Yoklama verilerinden PDF rapor oluşturur.

    Args:
        attendance_data: list of dict, her biri:
            - id: öğrenci numarası
            - name: öğrenci adı
            - status: "present" veya "absent"
            - time: yoklama zamanı (opsiyonel)
        output_path: çıktı dosya yolu (None ise otomatik oluşturulur)
        class_name: sınıf adı

    Returns:
        str: oluşturulan PDF dosyasının yolu
    """
    # Çıktı dizini
    reports_dir = os.path.join(os.path.dirname(__file__), 'pdf_reports')
    os.makedirs(reports_dir, exist_ok=True)

    if output_path is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(reports_dir, f'yoklama_{timestamp}.pdf')

    # Font kayıt
    font_name = _register_fonts()

    # PDF belgesi oluştur
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm
    )

    elements = []

    # Stiller
    title_style = ParagraphStyle(
        'TitleStyle',
        fontName=font_name,
        fontSize=22,
        leading=28,
        alignment=1,  # Center
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=5 * mm
    )

    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#666666'),
        spaceAfter=8 * mm
    )

    info_style = ParagraphStyle(
        'InfoStyle',
        fontName=font_name,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#333333'),
        spaceAfter=3 * mm
    )

    # Başlık
    elements.append(Paragraph("YOKLAMA RAPORU", title_style))

    # Alt başlık
    now = datetime.now()
    date_str = now.strftime('%d.%m.%Y')
    time_str = now.strftime('%H:%M')
    elements.append(Paragraph(
        f"{class_name} | {date_str} | {time_str}",
        subtitle_style
    ))

    # Çizgi
    elements.append(HRFlowable(
        width="100%", thickness=1,
        color=colors.HexColor('#6c5ce7'),
        spaceAfter=8 * mm
    ))

    # İstatistikler
    total = len(attendance_data)
    present = sum(1 for s in attendance_data if s.get('status') == 'present')
    absent = total - present
    rate = (present / total * 100) if total > 0 else 0

    elements.append(Paragraph(
        f"Toplam: {total} | Katilan: {present} | Katilmayan: {absent} | "
        f"Katilim Orani: %{rate:.1f}",
        info_style
    ))
    elements.append(Spacer(1, 5 * mm))

    # Tablo başlıkları
    table_data = [['Sira', 'Ogrenci No', 'Ad Soyad', 'Durum', 'Saat']]

    # Tablo verileri
    for i, student in enumerate(attendance_data, 1):
        status_text = "VAR" if student.get('status') == 'present' else "YOK"
        time_text = student.get('time', '-')
        table_data.append([
            str(i),
            str(student.get('id', 'N/A')),
            str(student.get('name', '')),
            status_text,
            str(time_text)
        ])

    # Tablo stili
    table = Table(table_data, colWidths=[
        1.2 * cm, 3 * cm, 6 * cm, 2.5 * cm, 3 * cm
    ])

    style = TableStyle([
        # Başlık satırı
        ('FONTNAME', (0, 0), (-1, 0), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6c5ce7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        # Veri satırları
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),   # Sıra
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),   # No
        ('ALIGN', (3, 1), (3, -1), 'CENTER'),   # Durum
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),   # Saat
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),

        # Kenarlıklar
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#6c5ce7')),

        # Zebra striping
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

    # Zebra striping (alternatif satır renkleri)
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f8f8ff'))

    # VAR/YOK renklendirme
    for i in range(1, len(table_data)):
        if table_data[i][3] == "VAR":
            style.add('TEXTCOLOR', (3, i), (3, i), colors.HexColor('#00b894'))
        else:
            style.add('TEXTCOLOR', (3, i), (3, i), colors.HexColor('#e17055'))

    table.setStyle(style)
    elements.append(table)

    # Alt bilgi
    elements.append(Spacer(1, 10 * mm))
    footer_style = ParagraphStyle(
        'FooterStyle',
        fontName=font_name,
        fontSize=8,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#999999')
    )
    elements.append(Paragraph(
        f"Bu rapor AI Destekli Yoklama Sistemi tarafindan otomatik olusturulmustur. | {now.strftime('%d.%m.%Y %H:%M:%S')}",
        footer_style
    ))

    # PDF oluştur
    doc.build(elements)
    print(f"[PDF] Rapor oluşturuldu: {output_path}")
    return output_path
