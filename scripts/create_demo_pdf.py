from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output" / "pdf" / "regulamento_empresa_demo.pdf"

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#1565C0")
TEAL = colors.HexColor("#00A6A6")
INK = colors.HexColor("#243B53")
MUTED = colors.HexColor("#627D98")
PALE = colors.HexColor("#EAF4F4")


def register_fonts() -> tuple[str, str]:
    regular = Path("C:/Windows/Fonts/arial.ttf")
    bold = Path("C:/Windows/Fonts/arialbd.ttf")
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("AIUpSans", str(regular)))
        pdfmetrics.registerFont(TTFont("AIUpSans-Bold", str(bold)))
        return "AIUpSans", "AIUpSans-Bold"
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = register_fonts()


def draw_page(canvas, document) -> None:
    canvas.saveState()
    width, _ = A4
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT, 8)
    canvas.drawRightString(width - 20 * mm, 10 * mm, f"Pagina {document.page}")
    canvas.restoreState()


def header_table() -> Table:
    return Table(
        [["AI-UP", "Documento de demonstracao do RAG"]],
        colWidths=[55 * mm, 115 * mm],
        style=TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (0, 0), NAVY),
                ("TEXTCOLOR", (1, 0), (1, 0), MUTED),
                ("LINEBELOW", (0, 0), (-1, -1), 1.2, TEAL),
                ("FONTNAME", (0, 0), (0, 0), FONT_BOLD),
                ("FONTNAME", (1, 0), (1, 0), FONT),
                ("FONTSIZE", (0, 0), (0, 0), 13),
                ("FONTSIZE", (1, 0), (1, 0), 9),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        ),
    )


def build_pdf() -> Path:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "TitleAIUp",
        parent=styles["Title"],
        fontName=FONT_BOLD,
        fontSize=24,
        leading=30,
        textColor=NAVY,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )
    subtitle = ParagraphStyle(
        "SubtitleAIUp",
        parent=styles["Normal"],
        fontName=FONT,
        fontSize=11,
        leading=16,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=10 * mm,
    )
    heading = ParagraphStyle(
        "HeadingAIUp",
        parent=styles["Heading1"],
        fontName=FONT_BOLD,
        fontSize=18,
        leading=23,
        textColor=BLUE,
        spaceAfter=5 * mm,
    )
    body = ParagraphStyle(
        "BodyAIUp",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=11,
        leading=17,
        textColor=INK,
        spaceAfter=4 * mm,
    )
    note = ParagraphStyle(
        "NoteAIUp",
        parent=body,
        fontSize=9,
        leading=14,
        textColor=MUTED,
    )

    document = BaseDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title="Regulamento Empresa - Demonstracao AI-Up",
        author="AI-Up",
        subject="Documento ficticio para apresentacao academica de RAG",
    )
    content_frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="content",
    )
    document.addPageTemplates(
        PageTemplate(id="ai-up-document", frames=[content_frame], onPage=draw_page)
    )

    story = [
        header_table(),
        Spacer(1, 8 * mm),
        Paragraph("Regulamento Interno da Empresa", title),
        Paragraph(
            "Documento ficticio preparado para demonstrar consulta semantica, respostas fundamentadas e citacao de paginas no AI-Up.",
            subtitle,
        ),
        Table(
            [
                [Paragraph("Versao", note), Paragraph("1.0", body)],
                [Paragraph("Finalidade", note), Paragraph("Demonstracao academica local", body)],
                [Paragraph("Privacidade", note), Paragraph("Nenhum dado e enviado para APIs externas", body)],
            ],
            colWidths=[42 * mm, 100 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                    ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8D8D8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        ),
        Spacer(1, 6 * mm),
        Paragraph("1. Politica de ferias", heading),
        Paragraph(
            "Todo colaborador possui direito a <b>30 dias de ferias</b> apos completar cada periodo de 12 meses de trabalho.",
            body,
        ),
        Paragraph(
            "O pedido deve ser enviado ao gestor com antecedencia minima de <b>30 dias corridos</b>. A data depende de aprovacao do gestor e da continuidade das atividades da equipe.",
            body,
        ),
        Paragraph(
            "As ferias podem ser divididas em ate tres periodos. Um deles deve possuir no minimo 14 dias corridos e os demais nao podem ter menos de 5 dias corridos cada.",
            body,
        ),
        PageBreak(),
        header_table(),
        Spacer(1, 10 * mm),
        Paragraph("2. Seguranca da informacao", heading),
        Paragraph(
            "O acesso aos sistemas corporativos exige autenticacao multifator sempre que o recurso oferecer essa opcao.",
            body,
        ),
        Paragraph(
            "Senhas sao pessoais e intransferiveis. O compartilhamento de credenciais, inclusive com colegas da mesma equipe, e proibido.",
            body,
        ),
        Paragraph(
            "Incidentes de seguranca, mensagens suspeitas ou perda de equipamento devem ser comunicados a equipe de TI em ate <b>1 hora</b> apos a identificacao.",
            body,
        ),
        Spacer(1, 8 * mm),
        Paragraph("Exemplos de incidentes", heading),
        Paragraph(
            "Tentativas de phishing, acesso nao reconhecido, exposicao acidental de dados e comportamento anormal de dispositivos corporativos.",
            body,
        ),
        PageBreak(),
        header_table(),
        Spacer(1, 10 * mm),
        Paragraph("3. Reembolso de despesas", heading),
        Paragraph(
            "Pedidos de reembolso devem ser enviados pelo sistema interno em ate <b>10 dias corridos</b> depois da despesa.",
            body,
        ),
        Paragraph(
            "Cada solicitacao deve incluir comprovante legivel, justificativa profissional e centro de custo. O limite mensal por colaborador e de <b>R$ 1.500,00</b>.",
            body,
        ),
        Paragraph(
            "O pagamento depende da aprovacao do gestor responsavel. Despesas sem comprovante ou sem relacao com a atividade profissional podem ser recusadas.",
            body,
        ),
        Spacer(1, 15 * mm),
        Table(
            [[Paragraph("Fim do documento", ParagraphStyle("End", parent=body, alignment=TA_CENTER, textColor=TEAL))]],
            colWidths=[150 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, TEAL),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            ),
        ),
    ]

    document.build(story)
    return OUTPUT_PATH


if __name__ == "__main__":
    print(build_pdf())
