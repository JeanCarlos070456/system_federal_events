from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.core.models import Orcamento, OrcamentoItem


class OrcamentoService:
    PDF_BLUE = colors.HexColor("#08789C")
    PDF_NAVY = colors.HexColor("#071A39")
    PDF_PURPLE = colors.HexColor("#8B5CF6")
    PDF_LIGHT_GRAY = colors.HexColor("#F3F6F9")
    PDF_GRID = colors.HexColor("#D9DEE7")
    PDF_TEXT = colors.HexColor("#111827")
    PDF_MUTED = colors.HexColor("#555F70")

    @staticmethod
    def gerar_codigo() -> str:
        """
        Gera código anual simples para orçamento.

        Exemplos:
        - 260001 = primeiro orçamento criado em 2026
        - 260015 = décimo quinto orçamento criado em 2026
        - 270001 = primeiro orçamento criado em 2027
        """
        ano_atual = timezone.localdate().year
        prefixo = str(ano_atual)[-2:]

        orcamentos_do_ano = Orcamento.objects.filter(created_at__year=ano_atual)

        codigos_novos = (
            orcamentos_do_ano
            .filter(codigo__regex=rf"^{prefixo}[0-9]{{4}}$")
            .values_list("codigo", flat=True)
        )

        maior_sequencia_por_codigo = 0

        for codigo in codigos_novos:
            try:
                sequencia = int(str(codigo)[2:])
                maior_sequencia_por_codigo = max(maior_sequencia_por_codigo, sequencia)
            except (TypeError, ValueError):
                continue

        quantidade_orcamentos_no_ano = orcamentos_do_ano.count()

        proxima_sequencia = max(
            maior_sequencia_por_codigo,
            quantidade_orcamentos_no_ano,
        ) + 1

        while proxima_sequencia <= 9999:
            codigo = f"{prefixo}{proxima_sequencia:04d}"

            if not Orcamento.objects.filter(codigo=codigo).exists():
                return codigo

            proxima_sequencia += 1

        raise ValueError(f"Limite anual de códigos de orçamento atingido para {ano_atual}.")

    @staticmethod
    def _decimal(value) -> Decimal:
        if value is None:
            return Decimal("0.00")

        if isinstance(value, Decimal):
            return value

        text = str(value).strip()

        if not text:
            return Decimal("0.00")

        text = text.replace("R$", "").replace(" ", "")

        if "," in text:
            text = text.replace(".", "").replace(",", ".")

        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    @classmethod
    def _money(cls, value) -> str:
        value = cls._decimal(value)
        formatted = f"{value:,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"

    @staticmethod
    def _date(value) -> str:
        if not value:
            return "Não informado"

        try:
            return value.strftime("%d/%m/%Y")
        except AttributeError:
            return str(value)

    @staticmethod
    def _safe(value) -> str:
        if value is None:
            return "Não informado"

        text = str(value).strip()
        return text if text else "Não informado"

    @classmethod
    def _p(cls, value, style: ParagraphStyle) -> Paragraph:
        text = escape(cls._safe(value)).replace("\n", "<br/>")
        return Paragraph(text, style)

    @staticmethod
    def calcular_item_total(item: OrcamentoItem) -> Decimal:
        valor_diaria = OrcamentoService._decimal(item.valor_diaria)
        desconto = OrcamentoService._decimal(item.desconto)

        quantidade = item.quantidade or 1
        dias_uso = item.dias_uso or 1

        total = valor_diaria * quantidade * dias_uso
        total -= desconto

        return max(total, Decimal("0.00"))

    @classmethod
    @transaction.atomic
    def salvar_item(cls, item: OrcamentoItem) -> OrcamentoItem:
        """
        Salva item e recalcula o orçamento.

        Regra:
        - Orçamento não vincula produto físico/código.
        - Esse vínculo fica para o módulo Estoque.
        """
        if item.produto and not item.equipamento:
            item.equipamento = item.produto.nome

        if item.produto and not item.valor_diaria:
            item.valor_diaria = item.produto.valor_diaria

        item.valor_total = cls.calcular_item_total(item)
        item.save()

        cls.recalcular_orcamento(item.orcamento)

        return item

    @staticmethod
    @transaction.atomic
    def recalcular_orcamento(orcamento: Orcamento) -> Orcamento:
        total = sum(
            (item.valor_total or Decimal("0.00"))
            for item in orcamento.itens.all()
        )

        valor_desconto = orcamento.valor_desconto or Decimal("0.00")
        valor_caucao = orcamento.valor_caucao or Decimal("0.00")

        orcamento.valor_total = total
        orcamento.valor_final = max(
            total - valor_desconto + valor_caucao,
            Decimal("0.00"),
        )

        orcamento.save(
            update_fields=[
                "valor_total",
                "valor_final",
                "updated_at",
            ]
        )

        return orcamento

    @staticmethod
    def _logo_path() -> str | None:
        candidates = [
            os.path.join(settings.BASE_DIR, "static", "img", "logo_vazada.png"),
            os.path.join(settings.BASE_DIR, "static", "img", "logo.png"),
            os.path.join(settings.BASE_DIR, "static", "assets", "logo_vazada.png"),
            os.path.join(settings.BASE_DIR, "static", "assets", "logo.png"),
        ]

        for path in candidates:
            if os.path.exists(path):
                return path

        return None

    @staticmethod
    def _assinatura_path() -> str | None:
        candidates = [
            os.path.join(settings.BASE_DIR, "static", "img", "assinatura.png"),
            os.path.join(settings.BASE_DIR, "static", "assets", "assinatura.png"),
        ]

        for path in candidates:
            if os.path.exists(path):
                return path

        return None

    @classmethod
    def _assinatura_flowable(cls):
        """
        Retorna a assinatura da empresa como flowable do ReportLab.

        Tenta recortar automaticamente espaços transparentes/brancos ao redor
        da imagem para aproximar visualmente a assinatura da linha.
        """
        assinatura_path = cls._assinatura_path()

        if not assinatura_path:
            return None

        try:
            from PIL import Image as PILImage, ImageChops

            img = PILImage.open(assinatura_path).convert("RGBA")

            alpha_bbox = img.getchannel("A").getbbox()

            if alpha_bbox:
                img = img.crop(alpha_bbox)
            else:
                bg = PILImage.new(img.mode, img.size, img.getpixel((0, 0)))
                diff = ImageChops.difference(img, bg)
                bbox = diff.getbbox()
                if bbox:
                    img = img.crop(bbox)

            output = BytesIO()
            img.save(output, format="PNG")
            output.seek(0)

            assinatura = Image(
                output,
                width=48 * mm,
                height=11 * mm,
            )
            assinatura.hAlign = "CENTER"

            # Mantém o buffer vivo até o ReportLab terminar o build.
            assinatura._federal_buffer = output

            return assinatura

        except Exception:
            assinatura = Image(
                assinatura_path,
                width=48 * mm,
                height=11 * mm,
            )
            assinatura.hAlign = "CENTER"
            return assinatura

    @classmethod
    def _draw_header_footer(cls, canvas, doc) -> None:
        width, height = A4

        canvas.saveState()

        header_height = 26 * mm
        canvas.setFillColor(cls.PDF_BLUE)
        canvas.rect(0, height - header_height, width, header_height, stroke=0, fill=1)

        canvas.setFillColor(colors.white)
        canvas.setFont("Times-Bold", 16)
        canvas.drawString(3 * cm, height - 15 * mm, "Federal Eventos")

        logo_path = cls._logo_path()
        if logo_path:
            try:
                logo = ImageReader(logo_path)
                canvas.drawImage(
                    logo,
                    width - 4.2 * cm,
                    height - 22 * mm,
                    width=18 * mm,
                    height=18 * mm,
                    mask="auto",
                    preserveAspectRatio=True,
                    anchor="c",
                )
            except Exception:
                canvas.setFont("Times-Bold", 7)
                canvas.drawRightString(width - 3 * cm, height - 15 * mm, "FEDERAL")
        else:
            canvas.setFont("Times-Bold", 7)
            canvas.drawRightString(width - 3 * cm, height - 15 * mm, "FEDERAL")

        canvas.setStrokeColor(cls.PDF_PURPLE)
        canvas.setLineWidth(1.4)
        canvas.line(
            3 * cm,
            height - header_height - 3 * mm,
            width - 3 * cm,
            height - header_height - 3 * mm,
        )

        canvas.setFillColor(colors.HexColor("#8A8A8A"))
        canvas.setFont("Times-Roman", 9)
        canvas.drawCentredString(width / 2, 1.25 * cm, "Documento emitido pela Federal Eventos")
        canvas.drawRightString(width - 2 * cm, 1.25 * cm, f"Página {doc.page}")

        canvas.restoreState()

    @staticmethod
    def contrato_clausulas_padrao_lista() -> list[dict]:
        return [
            {
                "titulo": "CLÁUSULA 1 – OBJETO",
                "conteudo": "Locação de equipamentos audiovisuais, painéis de LED, sonorização, iluminação, informática, estruturas e prestação de serviços técnicos para eventos.",
            },
            {
                "titulo": "CLÁUSULA 2 – PRAZO",
                "conteudo": "Conforme cronograma definido na proposta comercial.",
            },
            {
                "titulo": "CLÁUSULA 3 – VALOR E PAGAMENTO",
                "conteudo": "Conforme orçamento aprovado.",
            },
            {
                "titulo": "CLÁUSULA 4 – OBRIGAÇÕES DA CONTRATADA",
                "conteudo": "Fornecimento, montagem, operação, suporte técnico e desmontagem.",
            },
            {
                "titulo": "CLÁUSULA 5 – OBRIGAÇÕES DO CONTRATANTE",
                "conteudo": "Disponibilizar infraestrutura adequada, acesso ao local e efetuar os pagamentos contratados.",
            },
            {
                "titulo": "CLÁUSULA 6 – DANOS E EXTRAVIOS",
                "conteudo": "O contratante responderá por danos, perdas ou extravios dos equipamentos sob sua responsabilidade.",
            },
            {
                "titulo": "CLÁUSULA 7 – CANCELAMENTO",
                "conteudo": "Aplicação das penalidades previstas conforme antecedência do cancelamento.",
            },
            {
                "titulo": "CLÁUSULA 8 – REMONTAGEM",
                "conteudo": "Sempre que houver solicitação de alteração de layout, mudança de posicionamento, desmontagem e nova montagem após a conclusão dos serviços, será cobrado valor adicional correspondente a 50% do valor total do contrato, exceto quando decorrente de erro comprovado da Federal Eventos.",
            },
            {
                "titulo": "CLÁUSULA 9 – HORAS EXTRAS",
                "conteudo": "Serviços realizados fora do cronograma contratado serão cobrados adicionalmente.",
            },
            {
                "titulo": "CLÁUSULA 10 – ACEITE ELETRÔNICO",
                "conteudo": "Aprovações por assinatura eletrônica, e-mail, WhatsApp ou sistema terão validade jurídica.",
            },
            {
                "titulo": "CLÁUSULA 11 – FORO",
                "conteudo": "Fica eleito o foro de Brasília/DF.",
            },
        ]

    @staticmethod
    def contrato_clausulas_padrao() -> str:
        """
        Compatibilidade com versões anteriores que ainda usam texto único.
        """
        clausulas = OrcamentoService.contrato_clausulas_padrao_lista()

        return "\n\n".join(
            f"{item['titulo']}\n{item['conteudo']}"
            for item in clausulas
        )

    @staticmethod
    def _clausulas_texto_para_lista(clausulas_texto: str | None) -> list[dict]:
        texto = (clausulas_texto or "").strip()

        if not texto:
            return OrcamentoService.contrato_clausulas_padrao_lista()

        texto = texto.replace("\r\n", "\n").replace("\r", "\n")

        texto = re.sub(
            r"\s+(CLÁUSULA\s+\d+\s*[–-])",
            r"\n\n\1",
            texto,
            flags=re.IGNORECASE,
        )

        padrao = re.compile(
            r"(CLÁUSULA\s+\d+\s*[–-]\s*[^\n]+)\n*(.*?)(?=\n\nCLÁUSULA\s+\d+\s*[–-]|\Z)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        matches = list(padrao.finditer(texto))

        if not matches:
            return [
                {
                    "titulo": "CLÁUSULA CONTRATUAL",
                    "conteudo": texto,
                }
            ]

        clausulas = []

        for match in matches:
            titulo = match.group(1).strip()
            conteudo = match.group(2).strip()
            conteudo = re.sub(r"\n+", " ", conteudo)
            conteudo = re.sub(r"\s{2,}", " ", conteudo).strip()

            if titulo or conteudo:
                clausulas.append(
                    {
                        "titulo": titulo,
                        "conteudo": conteudo,
                    }
                )

        return clausulas or OrcamentoService.contrato_clausulas_padrao_lista()

    @classmethod
    def gerar_pdf_orcamento(cls, orcamento: Orcamento) -> bytes:
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=3 * cm,
            rightMargin=2 * cm,
            topMargin=4 * cm,
            bottomMargin=2.2 * cm,
            title=f"Orçamento {orcamento.codigo}",
            author="Federal Eventos",
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "FederalTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=18,
            leading=22,
            textColor=cls.PDF_NAVY,
            alignment=TA_CENTER,
            spaceAfter=12,
        )

        section_style = ParagraphStyle(
            "FederalSection",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=15,
            leading=18,
            textColor=cls.PDF_PURPLE,
            alignment=TA_LEFT,
            spaceBefore=16,
            spaceAfter=8,
        )

        ambiente_style = ParagraphStyle(
            "FederalAmbiente",
            parent=styles["Heading3"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            textColor=cls.PDF_NAVY,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
        )

        normal_style = ParagraphStyle(
            "FederalNormal",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=15,
            textColor=cls.PDF_TEXT,
            alignment=TA_LEFT,
        )

        label_style = ParagraphStyle(
            "FederalLabel",
            parent=normal_style,
            fontName="Times-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.black,
        )

        table_header_style = ParagraphStyle(
            "FederalTableHeader",
            parent=normal_style,
            fontName="Times-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        center_style = ParagraphStyle(
            "FederalCenter",
            parent=normal_style,
            alignment=TA_CENTER,
        )

        right_style = ParagraphStyle(
            "FederalRight",
            parent=normal_style,
            alignment=TA_RIGHT,
        )

        right_bold_style = ParagraphStyle(
            "FederalRightBold",
            parent=right_style,
            fontName="Times-Bold",
        )

        elements = []

        elements.append(Paragraph("ORÇAMENTO COMERCIAL DE LOCAÇÃO DE EQUIPAMENTOS E SERVIÇOS", title_style))
        elements.append(Spacer(1, 4))

        cliente_nome = orcamento.cliente_nome or (
            orcamento.cliente.nome if orcamento.cliente else "Não informado"
        )
        cliente_documento = orcamento.cliente_documento or (
            orcamento.cliente.documento if orcamento.cliente else "Não informado"
        )

        periodo = f"{cls._date(orcamento.data_inicio)} a {cls._date(orcamento.data_fim)}"

        elements.append(Paragraph("DADOS CADASTRAIS DO DOCUMENTO", section_style))

        dados_table = Table(
            [
                [Paragraph("EVENTO", label_style), Paragraph("CLIENTE", label_style)],
                [cls._p(orcamento.evento_nome, normal_style), cls._p(cliente_nome, normal_style)],
                [Paragraph("DATA", label_style), Paragraph("LOCAL", label_style)],
                [cls._p(periodo, normal_style), cls._p(orcamento.local_evento, normal_style)],
                [Paragraph("VALOR DO ORÇAMENTO", label_style), Paragraph("CÓDIGO", label_style)],
                [Paragraph(cls._money(orcamento.valor_final), normal_style), cls._p(orcamento.codigo, normal_style)],
                [Paragraph("DOCUMENTO", label_style), Paragraph("RESPONSÁVEL", label_style)],
                [cls._p(cliente_documento, normal_style), cls._p(orcamento.responsavel_cliente, normal_style)],
            ],
            colWidths=[8 * cm, 8 * cm],
        )

        dados_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, cls.PDF_GRID),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, cls.PDF_GRID),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BACKGROUND", (0, 0), (-1, 0), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 2), (-1, 2), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 4), (-1, 4), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 6), (-1, 6), cls.PDF_LIGHT_GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        elements.append(dados_table)
        elements.append(Paragraph("DETALHAMENTO DO ORÇAMENTO", section_style))

        ambientes = list(orcamento.ambientes.prefetch_related("itens").all())

        if not ambientes:
            elements.append(Paragraph("Nenhum ambiente ou item cadastrado neste orçamento.", normal_style))

        for ambiente in ambientes:
            titulo_ambiente = f"{ambiente.get_tipo_display()} {ambiente.nome}"
            elements.append(Paragraph(cls._safe(titulo_ambiente), ambiente_style))

            itens = list(ambiente.itens.all())

            table_rows = [
                [
                    Paragraph("Descrição", table_header_style),
                    Paragraph("Qtd", table_header_style),
                    Paragraph("Dias", table_header_style),
                    Paragraph("Preço Unitário", table_header_style),
                    Paragraph("Preço Total", table_header_style),
                ]
            ]

            subtotal_ambiente = Decimal("0.00")

            if not itens:
                table_rows.append(
                    [
                        Paragraph("Sem itens cadastrados", normal_style),
                        Paragraph("-", center_style),
                        Paragraph("-", center_style),
                        Paragraph("-", right_style),
                        Paragraph("-", right_style),
                    ]
                )
            else:
                for item in itens:
                    total_item = item.valor_total or cls.calcular_item_total(item)
                    subtotal_ambiente += cls._decimal(total_item)

                    descricao = item.equipamento or "Item sem descrição"

                    if item.descricao:
                        descricao = (
                            f"{escape(str(descricao))}<br/>"
                            f"<font size='9' color='#555F70'>{escape(str(item.descricao))}</font>"
                        )
                    else:
                        descricao = escape(str(descricao))

                    table_rows.append(
                        [
                            Paragraph(descricao, normal_style),
                            Paragraph(str(item.quantidade or 0), center_style),
                            Paragraph(str(item.dias_uso or 0), center_style),
                            Paragraph(cls._money(item.valor_diaria), right_style),
                            Paragraph(cls._money(total_item), right_style),
                        ]
                    )

            table_rows.append(
                [
                    Paragraph("Subtotal", label_style),
                    Paragraph("", normal_style),
                    Paragraph("", normal_style),
                    Paragraph("", normal_style),
                    Paragraph(cls._money(subtotal_ambiente), right_bold_style),
                ]
            )

            itens_table = Table(
                table_rows,
                colWidths=[6.7 * cm, 1.5 * cm, 1.5 * cm, 3.0 * cm, 3.3 * cm],
                repeatRows=1,
            )

            itens_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), cls.PDF_BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.6, cls.PDF_GRID),
                        ("INNERGRID", (0, 0), (-1, -1), 0.35, cls.PDF_GRID),
                        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                        ("BACKGROUND", (0, -1), (-1, -1), cls.PDF_LIGHT_GRAY),
                        ("SPAN", (0, -1), (3, -1)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elements.append(itens_table)
            elements.append(Spacer(1, 7))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("RESUMO FINANCEIRO", section_style))

        resumo_table = Table(
            [
                [Paragraph("Subtotal dos itens", label_style), Paragraph(cls._money(orcamento.valor_total), right_style)],
                [Paragraph("Desconto", label_style), Paragraph(cls._money(orcamento.valor_desconto), right_style)],
                [Paragraph("Caução", label_style), Paragraph(cls._money(orcamento.valor_caucao), right_style)],
                [
                    Paragraph(
                        "VALOR FINAL DO ORÇAMENTO",
                        ParagraphStyle(
                            "FinalLabel",
                            parent=label_style,
                            textColor=colors.white,
                        ),
                    ),
                    Paragraph(
                        cls._money(orcamento.valor_final),
                        ParagraphStyle(
                            "FinalValue",
                            parent=right_bold_style,
                            textColor=colors.white,
                            fontSize=13,
                            leading=16,
                        ),
                    ),
                ],
            ],
            colWidths=[11 * cm, 5 * cm],
            hAlign="RIGHT",
        )

        resumo_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, cls.PDF_GRID),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, cls.PDF_GRID),
                    ("BACKGROUND", (0, 0), (-1, 2), colors.white),
                    ("BACKGROUND", (0, 3), (-1, 3), cls.PDF_BLUE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        elements.append(resumo_table)

        if orcamento.condicoes_pagamento:
            elements.append(Paragraph("CONDIÇÕES DE PAGAMENTO", section_style))
            elements.append(cls._p(orcamento.condicoes_pagamento, normal_style))

        if orcamento.observacoes:
            elements.append(Paragraph("OBSERVAÇÕES", section_style))
            elements.append(cls._p(orcamento.observacoes, normal_style))

        doc.build(
            elements,
            onFirstPage=cls._draw_header_footer,
            onLaterPages=cls._draw_header_footer,
        )

        pdf = buffer.getvalue()
        buffer.close()

        return pdf

    @classmethod
    def gerar_pdf_contrato(
        cls,
        *,
        orcamento: Orcamento,
        clausulas: list[dict] | None = None,
        clausulas_texto: str | None = None,
        assinado_empresa: bool = False,
    ) -> bytes:
        """
        Gera contrato em PDF.

        Aceita:
        - clausulas: lista de dicts com titulo/conteudo, usada pelo modal novo.
        - clausulas_texto: texto único, mantido para compatibilidade.
        """
        if clausulas is None:
            clausulas = cls._clausulas_texto_para_lista(clausulas_texto)

        clausulas_limpas = []

        for item in clausulas:
            if not isinstance(item, dict):
                continue

            titulo = str(item.get("titulo") or "").strip()
            conteudo = str(item.get("conteudo") or "").strip()

            if titulo or conteudo:
                clausulas_limpas.append(
                    {
                        "titulo": titulo,
                        "conteudo": conteudo,
                    }
                )

        if not clausulas_limpas:
            clausulas_limpas = cls.contrato_clausulas_padrao_lista()

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=3 * cm,
            rightMargin=2 * cm,
            topMargin=4 * cm,
            bottomMargin=2.2 * cm,
            title=f"Contrato {orcamento.codigo}",
            author="Federal Eventos",
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ContratoTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=16,
            leading=20,
            textColor=cls.PDF_NAVY,
            alignment=TA_CENTER,
            spaceAfter=14,
        )

        intro_style = ParagraphStyle(
            "ContratoIntro",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=15,
            textColor=cls.PDF_TEXT,
            alignment=TA_LEFT,
            spaceAfter=10,
        )

        clause_title_style = ParagraphStyle(
            "ClauseTitle",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            textColor=cls.PDF_PURPLE,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=4,
        )

        dados_section_style = ParagraphStyle(
            "ContratoDadosSection",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=15,
            leading=18,
            textColor=cls.PDF_PURPLE,
            alignment=TA_LEFT,
            spaceBefore=16,
            spaceAfter=8,
        )

        ambiente_style = ParagraphStyle(
            "ContratoAmbiente",
            parent=styles["Heading3"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            textColor=cls.PDF_NAVY,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
        )

        normal_style = ParagraphStyle(
            "ContratoNormal",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=15,
            textColor=cls.PDF_TEXT,
            alignment=TA_LEFT,
        )

        label_style = ParagraphStyle(
            "ContratoLabel",
            parent=normal_style,
            fontName="Times-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.black,
        )

        table_header_style = ParagraphStyle(
            "ContratoTableHeader",
            parent=normal_style,
            fontName="Times-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.white,
            alignment=TA_CENTER,
        )

        center_style = ParagraphStyle(
            "ContratoCenter",
            parent=normal_style,
            alignment=TA_CENTER,
        )

        right_style = ParagraphStyle(
            "ContratoRight",
            parent=normal_style,
            alignment=TA_RIGHT,
        )

        right_bold_style = ParagraphStyle(
            "ContratoRightBold",
            parent=right_style,
            fontName="Times-Bold",
        )

        elements = []

        elements.append(
            Paragraph(
                "CONTRATO PADRÃO DE LOCAÇÃO DE EQUIPAMENTOS, TECNOLOGIA E SERVIÇOS PARA EVENTOS",
                title_style,
            )
        )

        elements.append(
            Paragraph(
                "Este contrato acompanha o orçamento emitido pela Federal Eventos e passa a integrar toda proposta comercial aprovada pelo cliente.",
                intro_style,
            )
        )

        for clausula in clausulas_limpas:
            titulo = clausula.get("titulo") or ""
            conteudo = clausula.get("conteudo") or ""

            if titulo:
                elements.append(Paragraph(escape(titulo), clause_title_style))

            if conteudo:
                elements.append(Paragraph(escape(conteudo).replace("\n", "<br/>"), normal_style))

            elements.append(Spacer(1, 6))

        elements.append(PageBreak())

        cliente_nome = orcamento.cliente_nome or (
            orcamento.cliente.nome if orcamento.cliente else "Não informado"
        )
        cliente_documento = orcamento.cliente_documento or (
            orcamento.cliente.documento if orcamento.cliente else "Não informado"
        )

        periodo = f"{cls._date(orcamento.data_inicio)} a {cls._date(orcamento.data_fim)}"

        elements.append(Paragraph("DADOS CADASTRAIS DO DOCUMENTO", dados_section_style))

        dados_table = Table(
            [
                [Paragraph("EVENTO", label_style), Paragraph("CLIENTE", label_style)],
                [cls._p(orcamento.evento_nome, normal_style), cls._p(cliente_nome, normal_style)],
                [Paragraph("DATA", label_style), Paragraph("LOCAL", label_style)],
                [cls._p(periodo, normal_style), cls._p(orcamento.local_evento, normal_style)],
                [Paragraph("VALOR DO ORÇAMENTO", label_style), Paragraph("CÓDIGO", label_style)],
                [Paragraph(cls._money(orcamento.valor_final), normal_style), cls._p(orcamento.codigo, normal_style)],
                [Paragraph("DOCUMENTO", label_style), Paragraph("RESPONSÁVEL", label_style)],
                [cls._p(cliente_documento, normal_style), cls._p(orcamento.responsavel_cliente, normal_style)],
            ],
            colWidths=[8 * cm, 8 * cm],
        )

        dados_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, cls.PDF_GRID),
                    ("INNERGRID", (0, 0), (-1, -1), 0.35, cls.PDF_GRID),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BACKGROUND", (0, 0), (-1, 0), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 2), (-1, 2), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 4), (-1, 4), cls.PDF_LIGHT_GRAY),
                    ("BACKGROUND", (0, 6), (-1, 6), cls.PDF_LIGHT_GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )

        elements.append(dados_table)
        elements.append(Paragraph("DETALHAMENTO DO ORÇAMENTO", dados_section_style))

        ambientes = list(orcamento.ambientes.prefetch_related("itens").all())

        if not ambientes:
            elements.append(Paragraph("Nenhum ambiente ou item cadastrado neste orçamento.", normal_style))

        for ambiente in ambientes:
            titulo_ambiente = f"{ambiente.get_tipo_display()} {ambiente.nome}"
            elements.append(Paragraph(cls._safe(titulo_ambiente), ambiente_style))

            itens = list(ambiente.itens.all())

            table_rows = [
                [
                    Paragraph("Descrição", table_header_style),
                    Paragraph("Qtd", table_header_style),
                    Paragraph("Dias", table_header_style),
                    Paragraph("Preço Unitário", table_header_style),
                    Paragraph("Preço Total", table_header_style),
                ]
            ]

            subtotal_ambiente = Decimal("0.00")

            if not itens:
                table_rows.append(
                    [
                        Paragraph("Sem itens cadastrados", normal_style),
                        Paragraph("-", center_style),
                        Paragraph("-", center_style),
                        Paragraph("-", right_style),
                        Paragraph("-", right_style),
                    ]
                )
            else:
                for item in itens:
                    total_item = item.valor_total or cls.calcular_item_total(item)
                    subtotal_ambiente += cls._decimal(total_item)

                    descricao = item.equipamento or "Item sem descrição"

                    if item.descricao:
                        descricao = (
                            f"{escape(str(descricao))}<br/>"
                            f"<font size='9' color='#555F70'>{escape(str(item.descricao))}</font>"
                        )
                    else:
                        descricao = escape(str(descricao))

                    table_rows.append(
                        [
                            Paragraph(descricao, normal_style),
                            Paragraph(str(item.quantidade or 0), center_style),
                            Paragraph(str(item.dias_uso or 0), center_style),
                            Paragraph(cls._money(item.valor_diaria), right_style),
                            Paragraph(cls._money(total_item), right_style),
                        ]
                    )

            table_rows.append(
                [
                    Paragraph("Subtotal", label_style),
                    Paragraph("", normal_style),
                    Paragraph("", normal_style),
                    Paragraph("", normal_style),
                    Paragraph(cls._money(subtotal_ambiente), right_bold_style),
                ]
            )

            itens_table = Table(
                table_rows,
                colWidths=[6.7 * cm, 1.5 * cm, 1.5 * cm, 3.0 * cm, 3.3 * cm],
                repeatRows=1,
            )

            itens_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), cls.PDF_BLUE),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.6, cls.PDF_GRID),
                        ("INNERGRID", (0, 0), (-1, -1), 0.35, cls.PDF_GRID),
                        ("BACKGROUND", (0, 1), (-1, -2), colors.white),
                        ("BACKGROUND", (0, -1), (-1, -1), cls.PDF_LIGHT_GRAY),
                        ("SPAN", (0, -1), (3, -1)),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elements.append(itens_table)
            elements.append(Spacer(1, 8))

        elements.append(Paragraph("ASSINATURAS", dados_section_style))

        if assinado_empresa:
            assinatura_empresa = cls._assinatura_flowable()
            if assinatura_empresa is None:
                assinatura_empresa = Paragraph("", normal_style)
        else:
            assinatura_empresa = Paragraph("", normal_style)

        assinatura_table = Table(
            [
                [
                    assinatura_empresa,
                    Paragraph("", normal_style),
                ],
                [
                    Paragraph("____________________________", center_style),
                    Paragraph("____________________________", center_style),
                ],
                [
                    Paragraph("Assinatura da empresa", center_style),
                    Paragraph("Assinatura do cliente", center_style),
                ],
            ],
            colWidths=[8 * cm, 8 * cm],
            rowHeights=[
                12 * mm,
                4 * mm,
                7 * mm,
            ],
        )

        assinatura_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                    ("VALIGN", (0, 1), (-1, 1), "TOP"),
                    ("VALIGN", (0, 2), (-1, 2), "TOP"),

                    ("TOPPADDING", (0, 0), (-1, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 0),

                    ("TOPPADDING", (0, 1), (-1, 1), 0),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 0),

                    ("TOPPADDING", (0, 2), (-1, 2), 0),
                    ("BOTTOMPADDING", (0, 2), (-1, 2), 0),
                ]
            )
        )

        elements.append(Spacer(1, 10))
        elements.append(assinatura_table)

        doc.build(
            elements,
            onFirstPage=cls._draw_header_footer,
            onLaterPages=cls._draw_header_footer,
        )

        pdf = buffer.getvalue()
        buffer.close()

        return pdf