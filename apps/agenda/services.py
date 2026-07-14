from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO
import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db.models import Q
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.models import Orcamento, OrcamentoItem


class AgendaService:
    PDF_NAVY = colors.HexColor("#071A39")
    PDF_BLUE = colors.HexColor("#08789C")
    PDF_PURPLE = colors.HexColor("#9A66FF")
    PDF_LIGHT = colors.HexColor("#F3F6F9")
    PDF_GRID = colors.HexColor("#D9DEE7")
    PDF_TEXT = colors.HexColor("#111827")

    STATUS_VINCULO_CANCELADO = {
        "Cancelado",
        "Cancelada",
        "Removido",
        "Removida",
        "Excluído",
        "Excluída",
    }

    MESES = {
        1: "JANEIRO",
        2: "FEVEREIRO",
        3: "MARÇO",
        4: "ABRIL",
        5: "MAIO",
        6: "JUNHO",
        7: "JULHO",
        8: "AGOSTO",
        9: "SETEMBRO",
        10: "OUTUBRO",
        11: "NOVEMBRO",
        12: "DEZEMBRO",
    }

    @staticmethod
    def _safe(value, default: str = "-") -> str:
        text = str(value or "").strip()
        return text if text else default

    @staticmethod
    def _date(value) -> str:
        if not value:
            return "Não informado"

        try:
            return value.strftime("%d/%m/%Y")
        except AttributeError:
            return str(value)

    @staticmethod
    def _periodo(inicio, fim) -> str:
        if inicio and fim:
            return f"{AgendaService._date(inicio)} a {AgendaService._date(fim)}"

        if inicio:
            return AgendaService._date(inicio)

        return "Não informado"

    @staticmethod
    def _to_int(value, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def eventos_queryset(cls):
        """
        Eventos da agenda baseados em orçamentos.

        Prioriza eventos atuais/futuros. Se não houver nenhum, retorna os últimos
        orçamentos com data para evitar tela vazia.
        """
        hoje = timezone.localdate()

        base = (
            Orcamento.objects
            .filter(data_inicio__isnull=False)
            .select_related("cliente")
            .prefetch_related(
                "ambientes__itens__estoque_vinculos",
                "itens__estoque_vinculos",
            )
            .order_by("data_inicio", "evento_nome")
        )

        futuros = base.filter(
            Q(data_fim__gte=hoje)
            | Q(data_fim__isnull=True, data_inicio__gte=hoje)
        )

        if futuros.exists():
            return futuros

        return base.order_by("-data_inicio", "evento_nome")

    @classmethod
    def buscar_orcamento(cls, orcamento_id=None):
        qs = cls.eventos_queryset()

        if orcamento_id:
            found = qs.filter(id=orcamento_id).first()
            if found:
                return found

            return (
                Orcamento.objects
                .select_related("cliente")
                .prefetch_related(
                    "ambientes__itens__estoque_vinculos",
                    "itens__estoque_vinculos",
                )
                .filter(id=orcamento_id)
                .first()
            )

        return qs.first()

    @classmethod
    def month_name(cls, month: int) -> str:
        return cls.MESES.get(month, str(month))

    @staticmethod
    def previous_month(year: int, month: int) -> dict:
        if month == 1:
            return {"year": year - 1, "month": 12}

        return {"year": year, "month": month - 1}

    @staticmethod
    def next_month(year: int, month: int) -> dict:
        if month == 12:
            return {"year": year + 1, "month": 1}

        return {"year": year, "month": month + 1}

    @classmethod
    def eventos_por_dia(cls, eventos) -> dict:
        eventos_map = defaultdict(list)

        for evento in eventos:
            if not evento.data_inicio:
                continue

            start = evento.data_inicio
            end = evento.data_fim or evento.data_inicio

            if end < start:
                end = start

            current = start

            while current <= end:
                eventos_map[current].append(
                    {
                        "id": str(evento.id),
                        "codigo": evento.codigo,
                        "titulo": evento.evento_nome,
                        "local": evento.local_evento or "Local não informado",
                    }
                )

                current += timedelta(days=1)

        return eventos_map

    @classmethod
    def montar_calendario(cls, *, year: int, month: int, eventos) -> list[list[dict]]:
        hoje = timezone.localdate()
        cal = calendar.Calendar(firstweekday=0)
        eventos_map = cls.eventos_por_dia(eventos)

        weeks = []

        for week in cal.monthdatescalendar(year, month):
            week_data = []

            for day in week:
                week_data.append(
                    {
                        "date": day,
                        "day": day.day,
                        "in_month": day.month == month,
                        "is_today": day == hoje,
                        "eventos": eventos_map.get(day, []),
                    }
                )

            weeks.append(week_data)

        return weeks

    @classmethod
    def _vinculos_ativos_item(cls, item: OrcamentoItem):
        vinculos = getattr(item, "estoque_vinculos", None)

        if vinculos is None:
            return []

        ativos = []

        for vinculo in vinculos.all():
            status = (getattr(vinculo, "status", "") or "").strip()

            if status in cls.STATUS_VINCULO_CANCELADO:
                continue

            ativos.append(vinculo)

        return ativos

    @classmethod
    def _qtd_vinculo(cls, vinculo) -> int:
        qtd = cls._to_int(getattr(vinculo, "quantidade", None), 1)
        return max(qtd, 1)

    @classmethod
    def _qtd_item(cls, item: OrcamentoItem) -> int:
        qtd = cls._to_int(getattr(item, "quantidade", None), 1)
        return max(qtd, 1)

    @classmethod
    def _rows_item_relacao(cls, item: OrcamentoItem) -> list[list[str]]:
        rows = []

        qtd_solicitada = cls._qtd_item(item)
        dias_uso = max(cls._to_int(getattr(item, "dias_uso", None), 1), 1)
        descricao = cls._safe(item.equipamento, "Item sem descrição")

        vinculos = cls._vinculos_ativos_item(item)

        qtd_vinculada = 0

        for vinculo in vinculos:
            qtd_vinculo = cls._qtd_vinculo(vinculo)
            qtd_vinculada += qtd_vinculo

            rows.append(
                [
                    cls._safe(vinculo.cod_patrimonio, "NÃO VINCULADO"),
                    descricao,
                    str(qtd_vinculo),
                    f"{dias_uso} dia(s)",
                ]
            )

        pendente = max(qtd_solicitada - qtd_vinculada, 0)

        if pendente > 0:
            rows.append(
                [
                    "NÃO VINCULADO",
                    descricao,
                    str(pendente),
                    f"{dias_uso} dia(s)",
                ]
            )

        return rows

    @classmethod
    def _logo_path(cls) -> str:
        """
        Localiza a logo institucional usada nos PDFs.

        A busca é tolerante para funcionar tanto em ambiente local quanto
        no Render, onde os arquivos estáticos podem estar coletados.
        """
        static_name = "img/logo_vazada.png"

        try:
            found = finders.find(static_name)
            if found and os.path.exists(found):
                return found
        except Exception:
            pass

        candidates = [
            os.path.join(getattr(settings, "BASE_DIR", ""), "static", "img", "logo_vazada.png"),
            os.path.join(getattr(settings, "BASE_DIR", ""), "assets", "img", "logo_vazada.png"),
            os.path.join(getattr(settings, "STATIC_ROOT", ""), "img", "logo_vazada.png"),
        ]

        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate

        return ""

    @classmethod
    def _draw_pdf_header_footer(cls, canvas, doc):
        """
        Cabeçalho e rodapé padronizados com orçamento/contrato:
        faixa azul, logo institucional, nome Federal Eventos e linha roxa.
        """
        width, height = A4

        canvas.saveState()

        # Cabeçalho institucional
        header_height = 2.45 * cm
        header_y = height - header_height

        canvas.setFillColor(cls.PDF_BLUE)
        canvas.rect(0, header_y, width, header_height, fill=1, stroke=0)

        logo_path = cls._logo_path()
        if logo_path:
            try:
                canvas.drawImage(
                    logo_path,
                    2.25 * cm,
                    header_y + 0.45 * cm,
                    width=1.25 * cm,
                    height=1.25 * cm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        canvas.setFillColor(colors.white)
        canvas.setFont("Times-Bold", 15)
        canvas.drawRightString(width - 2.45 * cm, header_y + 1.15 * cm, "Federal Eventos")

        # Linha roxa abaixo da faixa azul
        canvas.setStrokeColor(cls.PDF_PURPLE)
        canvas.setLineWidth(1.2)
        canvas.line(2.45 * cm, header_y - 0.30 * cm, width - 2.45 * cm, header_y - 0.30 * cm)

        # Rodapé
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.setFont("Times-Roman", 8)
        canvas.drawCentredString(width / 2, 1.2 * cm, "Relação de evento emitida pela Federal Eventos")
        canvas.drawRightString(width - 2 * cm, 1.2 * cm, f"Página {doc.page}")

        canvas.restoreState()

    @classmethod
    def gerar_pdf_relacao_evento(cls, orcamento: Orcamento) -> bytes:
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=1.6 * cm,
            rightMargin=1.6 * cm,
            topMargin=3.6 * cm,
            bottomMargin=2 * cm,
            title=f"Relação do Evento {orcamento.codigo}",
            author="Federal Eventos",
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "AgendaTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            textColor=cls.PDF_NAVY,
            alignment=TA_CENTER,
            spaceAfter=10,
        )

        normal_style = ParagraphStyle(
            "AgendaNormal",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            textColor=cls.PDF_TEXT,
            alignment=TA_LEFT,
        )

        label_style = ParagraphStyle(
            "AgendaLabel",
            parent=normal_style,
            fontName="Times-Bold",
        )

        header_style = ParagraphStyle(
            "AgendaTableHeader",
            parent=normal_style,
            fontName="Times-Bold",
            alignment=TA_CENTER,
            textColor=colors.white,
        )

        center_style = ParagraphStyle(
            "AgendaCenter",
            parent=normal_style,
            alignment=TA_CENTER,
        )

        elements = []

        elements.append(Paragraph("RELAÇÃO DO EVENTO", title_style))

        dados = [
            [
                Paragraph("Nome do Evento:", label_style),
                Paragraph(escape(cls._safe(orcamento.evento_nome)), normal_style),
            ],
            [
                Paragraph("Data do Evento:", label_style),
                Paragraph(cls._periodo(orcamento.data_inicio, orcamento.data_fim), normal_style),
            ],
            [
                Paragraph("Local:", label_style),
                Paragraph(escape(cls._safe(orcamento.local_evento, "Local não informado")), normal_style),
            ],
            [
                Paragraph("Data de montagem:", label_style),
                Paragraph(cls._date(orcamento.data_montagem), normal_style),
            ],
        ]

        dados_table = Table(
            dados,
            colWidths=[4 * cm, 13 * cm],
            hAlign="LEFT",
        )

        dados_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.4, cls.PDF_GRID),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, cls.PDF_GRID),
                    ("BACKGROUND", (0, 0), (0, -1), cls.PDF_LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        elements.append(dados_table)
        elements.append(Spacer(1, 12))

        ambientes = list(orcamento.ambientes.prefetch_related("itens__estoque_vinculos").all())

        itens_sem_ambiente = list(
            orcamento.itens
            .filter(ambiente__isnull=True)
            .prefetch_related("estoque_vinculos")
        )

        if not ambientes and not itens_sem_ambiente:
            elements.append(Paragraph("Nenhum item cadastrado para este evento.", normal_style))

        grupos = []

        for ambiente in ambientes:
            grupos.append(
                {
                    "titulo": ambiente.nome,
                    "itens": list(ambiente.itens.all()),
                }
            )

        if itens_sem_ambiente:
            grupos.append(
                {
                    "titulo": "SEM AMBIENTE DEFINIDO",
                    "itens": itens_sem_ambiente,
                }
            )

        for grupo in grupos:
            titulo = str(grupo["titulo"] or "AMBIENTE").upper()

            ambiente_header = Table(
                [[Paragraph(escape(titulo), header_style)]],
                colWidths=[17 * cm],
            )

            ambiente_header.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), cls.PDF_BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elements.append(ambiente_header)

            rows = [
                [
                    Paragraph("COD", label_style),
                    Paragraph("DESCRIÇÃO", label_style),
                    Paragraph("Qtd", label_style),
                    Paragraph("DIAS", label_style),
                ]
            ]

            for item in grupo["itens"]:
                item_rows = cls._rows_item_relacao(item)

                if item_rows:
                    for row in item_rows:
                        rows.append(
                            [
                                Paragraph(escape(row[0]), normal_style),
                                Paragraph(escape(row[1]), normal_style),
                                Paragraph(escape(row[2]), center_style),
                                Paragraph(escape(row[3]), center_style),
                            ]
                        )

            if len(rows) == 1:
                rows.append(
                    [
                        Paragraph("NÃO VINCULADO", normal_style),
                        Paragraph("Nenhum item neste ambiente", normal_style),
                        Paragraph("-", center_style),
                        Paragraph("-", center_style),
                    ]
                )

            table = Table(
                rows,
                colWidths=[3.3 * cm, 8.1 * cm, 2.2 * cm, 3.4 * cm],
                repeatRows=1,
            )

            table.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.45, cls.PDF_GRID),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, cls.PDF_GRID),
                        ("BACKGROUND", (0, 0), (-1, 0), cls.PDF_LIGHT),
                        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elements.append(table)
            elements.append(Spacer(1, 13))

        doc.build(elements, onFirstPage=cls._draw_pdf_header_footer, onLaterPages=cls._draw_pdf_header_footer)

        pdf = buffer.getvalue()
        buffer.close()

        return pdf