from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
import warnings
import re

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


class ExportError(Exception):
    pass


def report_filename(title, destination):
    def safe_part(value):
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', ' ', value)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip('. ')
        result = ''
        length = 0
        for character in cleaned:
            size = len(character.encode('utf-8'))
            if length + size > 80:
                break
            result += character
            length += size
        return result.rstrip('. ') or 'viagem'

    return f'{safe_part(title)} {safe_part(destination)} relatório.pdf'


def generate_expense_pdf(trip, leader, participants, rows):
    """Gera relatório da viagem e das despesas e reúne os comprovantes."""
    if len(rows) > 200:
        raise ExportError("A exportação permite até 200 despesas por vez.")
    if sum(len(expense.comprovante_conteudo) for expense, _ in rows) > 50 * 1024 * 1024:
        raise ExportError("Os comprovantes excedem o limite de 50 MB para exportação.")
    styles = getSampleStyleSheet()
    styles["BodyText"].wordWrap = "CJK"
    report = BytesIO()
    end_date = trip.data_fim.strftime('%d/%m/%Y') if trip.data_fim else "Não informada"
    created_at = trip.criado_em.strftime('%d/%m/%Y %H:%M %z').strip()
    story = [
        Paragraph("Relatório da viagem e despesas", styles["Title"]), Spacer(1, 14),
        Paragraph("Dados da viagem", styles["Heading2"]),
        Paragraph(f"Identificação: #{trip.id_viagem}", styles["BodyText"]),
        Paragraph(f"Título: {escape(trip.titulo)}", styles["BodyText"]),
        Paragraph(f"Destino: {escape(trip.destino)}", styles["BodyText"]),
        Paragraph(f"Início: {trip.data_inicio.strftime('%d/%m/%Y')} · Término: {end_date}", styles["BodyText"]),
        Paragraph(f"Descrição: {escape(trip.descricao or 'Não informada')}", styles["BodyText"]),
        Paragraph(f"Líder: {escape(leader.nome)}", styles["BodyText"]),
        Paragraph(f"Código: {escape(trip.codigo_acesso)} · Situação: {escape(trip.status)}", styles["BodyText"]),
        Paragraph(f"Criada em: {created_at}", styles["BodyText"]),
        Paragraph("Participantes:", styles["Heading3"]),
    ]
    if participants:
        story.extend(Paragraph(escape(person.nome), styles["BodyText"]) for person in participants)
    else:
        story.append(Paragraph("Nenhum técnico participante.", styles["BodyText"]))
    story.extend([Spacer(1, 14), Paragraph("Despesas dos técnicos", styles["Heading2"])])
    total = Decimal("0.00")
    for expense, name in rows:
        total += expense.valor
        safe_name = escape(name)
        safe_description = escape(expense.descricao)
        story.extend([
            Paragraph(f"<b>Despesa #{expense.id_despesa} — {safe_name}</b>", styles["Heading3"]),
            Paragraph(f"Descrição: {safe_description}", styles["BodyText"]),
            Paragraph(f"Data: {expense.data_despesa.strftime('%d/%m/%Y')} · Categoria: {escape(expense.categoria)}", styles["BodyText"]),
            Paragraph(f"Valor: R$ {expense.valor:.2f} · Situação: {escape(expense.status)}", styles["BodyText"]),
            Spacer(1, 10),
        ])
    if not rows:
        story.append(Paragraph("Nenhuma despesa registrada.", styles["BodyText"]))
    story.append(Paragraph(f"<b>Total: R$ {total:.2f}</b>", styles["Heading2"]))
    SimpleDocTemplate(report, pagesize=A4).build(story)
    report.seek(0)
    writer = PdfWriter()
    writer.append(report, import_outline=False, excluded_fields=["/Annots", "/B"])
    sources = [report]
    for expense, _ in rows:
        try:
            marker = BytesIO()
            page = canvas.Canvas(marker, pagesize=A4)
            page.setFont("Helvetica-Bold", 16)
            page.drawString(48, A4[1] - 64, f"Comprovante da despesa #{expense.id_despesa}")
            if expense.comprovante_tipo in ("image/jpeg", "image/png"):
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(expense.comprovante_conteudo), formats=["JPEG", "PNG"]) as image:
                        image.load()
                        page.drawImage(ImageReader(image), 48, 48, width=A4[0] - 96, height=A4[1] - 150, preserveAspectRatio=True, anchor="c", mask="auto")
            page.showPage()
            page.save()
            marker.seek(0)
            sources.append(marker)
            writer.append(marker, import_outline=False, excluded_fields=["/Annots", "/B"])
            if expense.comprovante_tipo == "application/pdf":
                source = BytesIO(expense.comprovante_conteudo)
                sources.append(source)
                reader = PdfReader(source, strict=True)
                if reader.is_encrypted or len(reader.pages) == 0:
                    raise ValueError("PDF protegido ou sem páginas")
                if len(writer.pages) + len(reader.pages) > 500:
                    raise ExportError("A exportação excede o limite de 500 páginas.")
                writer.append(reader, import_outline=False, excluded_fields=["/Annots", "/B"])
            elif expense.comprovante_tipo not in ("image/jpeg", "image/png"):
                raise ValueError("Formato não suportado")
            if len(writer.pages) > 500:
                raise ExportError("A exportação excede o limite de 500 páginas.")
        except ExportError:
            raise
        except Exception as exc:
            raise ExportError(f"Não foi possível processar o comprovante da despesa #{expense.id_despesa}. Verifique se o arquivo está íntegro e não possui senha.") from exc
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
