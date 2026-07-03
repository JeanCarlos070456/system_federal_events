from __future__ import annotations

import io
import os
import re
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import Paragraph
    from reportlab.pdfgen import canvas
except Exception as exc:  # pragma: no cover
    canvas = None
    _REPORTLAB_IMPORT_ERROR = exc
else:
    _REPORTLAB_IMPORT_ERROR = None


# =========================================================
# CONFIGURAÇÃO VISUAL DO PDF
# =========================================================

EMPRESA_PADRAO = {
    "EMPRESA_NOME": "FEDERAL LOCAÇÃO DE EQUIPAMENTOS LTDA",
    "EMPRESA_CNPJ": "28.214.175/0001-10",
    "EMPRESA_TELEFONE": "(61) 99586-1529",
    "EMPRESA_EMAIL": "contato@federaleventos.com.br",
    "EMPRESA_SITE": "federal.eventos",
    "EMPRESA_LOCAL": "Brasília - DF",
}

VALIDADE_PADRAO_DIAS = 7
PDF_FILENAME_PADRAO = "orcamento_federal.pdf"

PAGE_SIZE = A4
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE

MARGIN_X = 20 * mm
TOP_MARGIN = 18 * mm
BOTTOM_MARGIN = 18 * mm

COR_AZUL_ESCURO = colors.HexColor("#061A36")
COR_AZUL_ESCURO_2 = colors.HexColor("#071D3C")
COR_AZUL_MEDIO = colors.HexColor("#6C2AA4")
COR_CINZA_CABECALHO = colors.HexColor("#202A33")
COR_CINZA_BORDA = colors.HexColor("#D9D9D9")
COR_CINZA_TEXTO = colors.HexColor("#2D2D2D")
COR_BRANCO = colors.white
COR_ROXO = colors.HexColor("#C94AD8")
COR_ROXO_CLARO = colors.HexColor("#B8A4E6")

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_OBLIQUE = "Helvetica-Oblique"

HEADER_TOP = PAGE_HEIGHT - TOP_MARGIN
HEADER_BOTTOM = PAGE_HEIGHT - 148
AC_BAR_TOP = HEADER_BOTTOM - 8
AC_BAR_BOTTOM = AC_BAR_TOP - 34
INFO_TOP = AC_BAR_BOTTOM - 28
INFO_BOTTOM = INFO_TOP - 116
CONTENT_TOP_FIRST = INFO_BOTTOM - 18
CONTENT_TOP_NEXT = HEADER_BOTTOM - 18
FEATURES_TOP = 176
FEATURES_BOTTOM = 74
NOTE_TOP = 52
NOTE_BOTTOM = 16
CONTENT_BOTTOM = FEATURES_TOP + 18

LOGO_CANDIDATES = [
    Path("assets/logo_vazada.png"),
    Path("assets/logo.png"),
    Path("assets/logo_white.png"),
    Path("assets/logo_federal.png"),
    Path("assets/brand/logo.png"),
]


# =========================================================
# VALIDAÇÕES / HELPERS GERAIS
# =========================================================

def _validate_reportlab_available() -> None:
    if canvas is None:
        raise RuntimeError(
            "A biblioteca reportlab não está disponível. Instale com: pip install reportlab"
        ) from _REPORTLAB_IMPORT_ERROR


def _safe_str(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null"}:
        return fallback

    return text


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback

        if isinstance(value, str):
            value = (
                value.replace("R$", "")
                .replace(" ", "")
                .replace(".", "")
                .replace(",", ".")
                .strip()
            )

        return float(value)
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return fallback


def _brl(value: Any) -> str:
    valor = _safe_float(value, 0.0)
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _parse_date(value: Any, fallback: date | None = None) -> date:
    if fallback is None:
        fallback = date.today()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = _safe_str(value)

    if not text:
        return fallback

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text)
        return parsed.date()
    except Exception:
        return fallback


def _format_date_br(value: Any) -> str:
    return _parse_date(value).strftime("%d/%m/%Y")


def _format_periodo_br(data_inicio: Any, data_fim: Any) -> str:
    inicio = _parse_date(data_inicio)
    fim = _parse_date(data_fim, inicio)

    if fim < inicio:
        fim = inicio

    if inicio == fim:
        return inicio.strftime("%d/%m/%Y")

    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"


def _dias_evento(data_inicio: Any, data_fim: Any) -> int:
    inicio = _parse_date(data_inicio)
    fim = _parse_date(data_fim, inicio)

    if fim < inicio:
        return 1

    return max((fim - inicio).days + 1, 1)


def _calcular_item(item: dict[str, Any]) -> float:
    quantidade = max(_safe_int(item.get("quantidade"), 1), 1)
    valor_diaria = max(_safe_float(item.get("valor_diaria"), 0.0), 0.0)
    dias_uso = max(_safe_int(item.get("dias_uso"), 1), 1)
    desconto = max(_safe_float(item.get("desconto"), 0.0), 0.0)

    return max((valor_diaria * quantidade * dias_uso) - desconto, 0.0)


def _calcular_sala(sala: dict[str, Any]) -> float:
    return sum(_calcular_item(item) for item in sala.get("itens", []))


def _calcular_orcamento(orcamento: dict[str, Any]) -> float:
    return sum(_calcular_sala(sala) for sala in orcamento.get("salas", []))


def _get_orcamento_codigo(orcamento: dict[str, Any]) -> str:
    codigo = _safe_str(orcamento.get("codigo"))

    if codigo:
        return codigo

    return datetime.now().strftime("ORC-%Y%m%d-%H%M%S")


def _safe_file_stem(value: Any, fallback: str = "orcamento") -> str:
    text = _safe_str(value, fallback)
    text = re.sub(r"[^A-Za-z0-9_\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def _get_data_envio(orcamento: dict[str, Any]) -> str:
    data_envio = (
        orcamento.get("data_envio")
        or orcamento.get("criado_em")
        or orcamento.get("atualizado_em")
        or date.today()
    )

    return _format_date_br(data_envio)


def _normalizar_item(item: dict[str, Any], dias_padrao: int) -> dict[str, Any]:
    item = deepcopy(item or {})
    item["equipamento"] = _safe_str(
        item.get("equipamento")
        or item.get("produto")
        or item.get("descricao")
        or item.get("nome"),
        "Equipamento",
    )
    item["quantidade"] = max(_safe_int(item.get("quantidade"), 1), 1)
    item["valor_diaria"] = max(
        _safe_float(
            item.get("valor_diaria")
            or item.get("valor_unitario")
            or item.get("preco_unitario")
            or item.get("preco")
            or item.get("valor"),
            0.0,
        ),
        0.0,
    )
    item["dias_uso"] = max(_safe_int(item.get("dias_uso"), dias_padrao), 1)
    item["desconto"] = max(_safe_float(item.get("desconto"), 0.0), 0.0)
    item["total"] = _calcular_item(item)
    return item


def _normalizar_sala(sala: dict[str, Any], idx: int, dias_padrao: int) -> dict[str, Any]:
    sala = deepcopy(sala or {})
    sala["nome"] = _safe_str(
        sala.get("nome") or sala.get("sala") or sala.get("ambiente"),
        f"Sala {idx}",
    )
    itens = sala.get("itens") or sala.get("equipamentos") or []
    sala["itens"] = [_normalizar_item(item, dias_padrao) for item in itens]
    sala["total"] = _calcular_sala(sala)
    return sala


def _normalizar_orcamento(orcamento: dict[str, Any]) -> dict[str, Any]:
    normalizado = deepcopy(orcamento or {})

    normalizado["codigo"] = _get_orcamento_codigo(normalizado)
    normalizado["data_inicio"] = _parse_date(normalizado.get("data_inicio"))
    normalizado["data_fim"] = _parse_date(
        normalizado.get("data_fim"),
        normalizado["data_inicio"],
    )

    if normalizado["data_fim"] < normalizado["data_inicio"]:
        normalizado["data_fim"] = normalizado["data_inicio"]

    dias_padrao = _dias_evento(normalizado["data_inicio"], normalizado["data_fim"])
    salas = normalizado.get("salas") or []
    normalizado["salas"] = [
        _normalizar_sala(sala, idx, dias_padrao)
        for idx, sala in enumerate(salas, start=1)
    ]
    normalizado["caucao"] = max(_safe_float(normalizado.get("caucao"), 0.0), 0.0)
    normalizado["valor"] = _calcular_orcamento(normalizado)
    normalizado["total_final"] = normalizado["valor"] + normalizado["caucao"]

    return normalizado


def _montar_contexto(orcamento: dict[str, Any]) -> dict[str, str]:
    orc = _normalizar_orcamento(orcamento)

    cliente = _safe_str(orc.get("cliente"), "Cliente não informado")
    data_inicio = orc.get("data_inicio")
    data_fim = orc.get("data_fim")

    evento_nome = _safe_str(
        orc.get("evento_nome")
        or orc.get("evento")
        or orc.get("nome_evento"),
        "Evento não informado",
    )

    responsavel = _safe_str(
        orc.get("responsavel_cliente")
        or orc.get("responsavel")
        or orc.get("ac")
        or cliente,
        cliente,
    )

    local_evento = _safe_str(
        orc.get("local_evento")
        or orc.get("local")
        or orc.get("endereco_evento"),
        "Local não informado",
    )

    data_montagem = _safe_str(
        orc.get("data_montagem") or orc.get("montagem"),
        _format_date_br(data_inicio),
    )

    validade = max(_safe_int(orc.get("validade_dias"), VALIDADE_PADRAO_DIAS), 1)
    total_servicos = _calcular_orcamento(orc)
    caucao = _safe_float(orc.get("caucao"), 0.0)
    total_final = total_servicos + caucao

    return {
        **EMPRESA_PADRAO,
        "CODIGO_ORCAMENTO": _safe_str(orc.get("codigo")),
        "DATA_ENVIO": _get_data_envio(orc),
        "RESPONSAVEL_CLIENTE": responsavel,
        "EVENTO_NOME": evento_nome,
        "EVENTO_DATA_EXTENSO": _format_periodo_br(data_inicio, data_fim),
        "CLIENTE_NOME": cliente,
        "DATA_EVENTO": _format_periodo_br(data_inicio, data_fim),
        "LOCAL_EVENTO": local_evento,
        "DATA_MONTAGEM": _format_date_br(data_montagem),
        "SUBTOTAL": _brl(total_servicos),
        "TOTAL": _brl(total_servicos),
        "TOTAL_SERVICOS": _brl(total_servicos),
        "CAUCAO": _brl(caucao),
        "TOTAL_FINAL": _brl(total_final),
        "VALIDADE_DIAS": str(validade),
    }


# =========================================================
# PRIMITIVAS DE DESENHO
# =========================================================

def _set_font(
    c: canvas.Canvas,
    font: str = FONT_REGULAR,
    size: float = 9,
    color: colors.Color = COR_CINZA_TEXTO,
) -> None:
    c.setFont(font, size)
    c.setFillColor(color)


def _draw_text(
    c: canvas.Canvas,
    text: Any,
    x: float,
    y: float,
    size: float = 9,
    font: str = FONT_REGULAR,
    color: colors.Color = COR_CINZA_TEXTO,
    align: str = "left",
) -> None:
    text = _safe_str(text)
    _set_font(c, font, size, color)

    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)


def _draw_rect(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    fill_color: colors.Color,
    stroke_color: colors.Color | None = None,
    stroke_width: float = 0.5,
) -> None:
    c.saveState()
    c.setFillColor(fill_color)
    c.setStrokeColor(stroke_color or fill_color)
    c.setLineWidth(stroke_width)
    c.rect(x, y, w, h, fill=1, stroke=1 if stroke_color else 0)
    c.restoreState()


def _paragraph_style(
    name: str,
    font: str = FONT_REGULAR,
    size: float = 8,
    color: colors.Color = COR_CINZA_TEXTO,
    align: int = TA_LEFT,
    leading: float | None = None,
) -> ParagraphStyle:
    return ParagraphStyle(
        name=name,
        fontName=font,
        fontSize=size,
        leading=leading or size * 1.18,
        textColor=color,
        alignment=align,
        wordWrap="LTR",
    )


def _draw_paragraph(
    c: canvas.Canvas,
    text: Any,
    x: float,
    y_top: float,
    w: float,
    h: float,
    size: float = 8,
    font: str = FONT_REGULAR,
    color: colors.Color = COR_CINZA_TEXTO,
    align: int = TA_LEFT,
) -> None:
    text = _safe_str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    style = _paragraph_style("cell", font, size, color, align)
    paragraph = Paragraph(text.replace("\n", "<br/>"), style)
    _, used_h = paragraph.wrap(w, h)
    y = y_top - min(used_h, h)
    paragraph.drawOn(c, x, y)


def _split_text_to_lines(
    text: str,
    max_width: float,
    font: str,
    size: float,
    max_lines: int = 2,
) -> list[str]:
    words = _safe_str(text).split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"

        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

            if len(lines) >= max_lines:
                break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if words and not lines:
        lines = [_safe_str(text)[:40]]

    if len(lines) == max_lines and stringWidth(" ".join(words), font, size) > max_width * max_lines:
        lines[-1] = lines[-1].rstrip(".") + "..."

    return lines


def _find_existing_path(candidates: Iterable[Path]) -> Path | None:
    for path in candidates:
        try:
            if path.exists() and path.is_file():
                return path
        except Exception:
            continue
    return None


# =========================================================
# CABEÇALHO / RODAPÉ / DADOS DO EVENTO
# =========================================================

def _draw_brand_fallback(c: canvas.Canvas, x: float, y: float) -> None:
    c.saveState()
    c.setStrokeColor(COR_BRANCO)
    c.setFillColor(COR_BRANCO)
    c.circle(x + 27, y + 40, 22, stroke=1, fill=0)

    for offset in range(-16, 18, 8):
        c.line(x + 7, y + 40 + offset, x + 47, y + 40 + offset)
        c.line(x + 27 + offset, y + 20, x + 27 + offset, y + 60)

    _draw_text(c, "FEDERAL LOCAÇÃO", x + 62, y + 54, 13, FONT_BOLD, COR_BRANCO)
    _draw_text(c, "DE EQUIPAMENTOS", x + 62, y + 37, 13, FONT_BOLD, COR_BRANCO)
    _draw_text(c, "LTDA", x + 62, y + 20, 13, FONT_BOLD, COR_BRANCO)
    _draw_text(c, "CNPJ: 28.214.175/0001-10", x + 62, y + 4, 7.5, FONT_REGULAR, COR_BRANCO)
    c.restoreState()


def _draw_logo_or_fallback(c: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    logo_path = _find_existing_path(LOGO_CANDIDATES)

    if logo_path:
        try:
            c.drawImage(
                str(logo_path),
                x,
                y,
                width=w,
                height=h,
                mask="auto",
                preserveAspectRatio=True,
                anchor="w",
            )
            return
        except Exception:
            pass

    _draw_brand_fallback(c, x, y)


def _draw_page_header(c: canvas.Canvas, contexto: dict[str, str], page_no: int = 1) -> None:
    _draw_rect(
        c,
        MARGIN_X,
        HEADER_BOTTOM,
        PAGE_WIDTH - (2 * MARGIN_X),
        HEADER_TOP - HEADER_BOTTOM,
        COR_AZUL_ESCURO,
    )

    _draw_logo_or_fallback(c, MARGIN_X + 12, HEADER_BOTTOM + 18, 205, 72)

    center_x = PAGE_WIDTH / 2
    _draw_text(c, "ORÇAMENTO", center_x, HEADER_TOP - 23, 17, FONT_BOLD, COR_BRANCO, "center")
    _draw_text(c, contexto["CODIGO_ORCAMENTO"], center_x, HEADER_TOP - 45, 12, FONT_BOLD, COR_ROXO_CLARO, "center")
    _draw_text(c, f"ENVIADA EM {contexto['DATA_ENVIO']}", center_x, HEADER_TOP - 72, 9, FONT_BOLD, COR_ROXO, "center")

    right_x = PAGE_WIDTH - MARGIN_X - 160
    base_y = HEADER_TOP - 30
    contato = [
        ("☎", contexto["EMPRESA_TELEFONE"]),
        ("✉", contexto["EMPRESA_EMAIL"]),
        ("◎", contexto["EMPRESA_SITE"]),
        ("⌖", contexto["EMPRESA_LOCAL"]),
    ]

    for idx, (icon, value) in enumerate(contato):
        _draw_text(c, icon, right_x, base_y - (idx * 13), 8, FONT_BOLD, COR_ROXO if idx == 0 else COR_BRANCO)
        _draw_text(c, value, right_x + 14, base_y - (idx * 13), 8.5, FONT_REGULAR, COR_BRANCO)

    if page_no > 1:
        _draw_text(
            c,
            f"Continuação - página {page_no}",
            PAGE_WIDTH - MARGIN_X - 8,
            HEADER_BOTTOM + 10,
            7.5,
            FONT_REGULAR,
            COR_BRANCO,
            "right",
        )


def _draw_ac_bar(c: canvas.Canvas, contexto: dict[str, str]) -> None:
    _draw_rect(
        c,
        MARGIN_X,
        AC_BAR_BOTTOM,
        PAGE_WIDTH - (2 * MARGIN_X),
        AC_BAR_TOP - AC_BAR_BOTTOM,
        COR_AZUL_ESCURO,
    )

    icon_x = MARGIN_X + 11
    icon_y = AC_BAR_BOTTOM + 8
    c.saveState()
    c.setStrokeColor(COR_BRANCO)
    c.setLineWidth(1.2)
    c.circle(icon_x + 8, icon_y + 10, 6, stroke=1, fill=0)
    c.arc(icon_x, icon_y - 2, icon_x + 16, icon_y + 14, 0, 180)
    c.restoreState()

    _draw_text(
        c,
        f"AC: {contexto['RESPONSAVEL_CLIENTE']}",
        MARGIN_X + 34,
        AC_BAR_BOTTOM + 12,
        10.5,
        FONT_BOLD,
        COR_BRANCO,
    )


def _draw_info_cell(
    c: canvas.Canvas,
    label: str,
    value: str,
    x: float,
    y_top: float,
    w: float,
    header_fill: colors.Color = COR_CINZA_CABECALHO,
) -> None:
    header_h = 15
    _draw_rect(c, x, y_top - header_h, w, header_h, header_fill)
    _draw_text(c, label.upper(), x + 4, y_top - 11, 9, FONT_BOLD, COR_BRANCO)
    _draw_paragraph(c, value, x + 4, y_top - header_h - 5, w - 8, 32, 9, FONT_REGULAR, COR_CINZA_TEXTO)


def _draw_event_info(c: canvas.Canvas, contexto: dict[str, str]) -> None:
    full_w = PAGE_WIDTH - (2 * MARGIN_X)
    col_w = full_w / 2
    row_gap = 45

    y = INFO_TOP
    _draw_info_cell(c, "EVENTO", contexto["EVENTO_NOME"], MARGIN_X, y, col_w)
    _draw_info_cell(c, "CLIENTE", contexto["CLIENTE_NOME"], MARGIN_X + col_w, y, col_w)

    y -= row_gap
    _draw_info_cell(c, "DATA", contexto["DATA_EVENTO"], MARGIN_X, y, col_w)
    _draw_info_cell(c, "LOCAL", contexto["LOCAL_EVENTO"], MARGIN_X + col_w, y, col_w)

    y -= row_gap
    _draw_info_cell(c, "MONTAGEM", contexto["DATA_MONTAGEM"], MARGIN_X, y, col_w)
    _draw_info_cell(c, "VALOR DO ORÇAMENTO", contexto["TOTAL"], MARGIN_X + col_w, y, col_w, COR_AZUL_MEDIO)


def _draw_feature_icon(c: canvas.Canvas, kind: str, x: float, y: float) -> None:
    c.saveState()
    c.setStrokeColor(COR_BRANCO)
    c.setFillColor(COR_BRANCO)
    c.setLineWidth(1.2)

    if kind == "shield":
        p = c.beginPath()
        p.moveTo(x, y + 27)
        p.lineTo(x + 18, y + 34)
        p.lineTo(x + 36, y + 27)
        p.lineTo(x + 31, y + 6)
        p.lineTo(x + 18, y)
        p.lineTo(x + 5, y + 6)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
        c.circle(x + 18, y + 17, 5, stroke=1, fill=0)
    elif kind == "headset":
        c.arc(x + 4, y + 8, x + 32, y + 36, 0, 180)
        c.rect(x + 2, y + 10, 6, 12, stroke=1, fill=0)
        c.rect(x + 28, y + 10, 6, 12, stroke=1, fill=0)
        c.line(x + 29, y + 9, x + 20, y + 3)
    elif kind == "checklist":
        for i in range(3):
            yy = y + 26 - (i * 10)
            c.rect(x, yy - 4, 5, 5, stroke=1, fill=0)
            c.line(x + 9, yy, x + 35, yy)
            c.line(x + 1, yy - 1, x + 3, yy - 3)
            c.line(x + 3, yy - 3, x + 7, yy + 3)
    else:
        c.circle(x + 18, y + 18, 18, stroke=1, fill=0)
        c.circle(x + 18, y + 18, 12, stroke=1, fill=0)
        c.line(x + 18, y + 7, x + 18, y + 2)
        c.line(x + 18, y + 34, x + 18, y + 39)
        c.line(x + 7, y + 18, x + 2, y + 18)
        c.line(x + 34, y + 18, x + 39, y + 18)

    c.restoreState()


def _draw_footer(c: canvas.Canvas, contexto: dict[str, str]) -> None:
    full_w = PAGE_WIDTH - (2 * MARGIN_X)
    _draw_rect(c, MARGIN_X, FEATURES_BOTTOM, full_w, FEATURES_TOP - FEATURES_BOTTOM, COR_AZUL_ESCURO)

    features = [
        ("shield", "EQUIPAMENTOS\nDE ALTO PADRÃO", "Tecnologia moderna\ne confiável."),
        ("headset", "SUPORTE TÉCNICO\nESPECIALIZADO", "Equipe dedicada\ndurante todo\no evento."),
        ("checklist", "INSTALAÇÃO E\nDESINSTALAÇÃO", "Serviço completo\ncom segurança\ne eficiência."),
        ("quality", "COMPROMISSO\nCOM QUALIDADE", "Soluções sob medida\npara o sucesso\ndo seu evento."),
    ]

    feature_w = full_w * 0.58 / 4
    start_x = MARGIN_X + 10

    for idx, (kind, title, desc) in enumerate(features):
        x = start_x + (idx * feature_w)
        _draw_feature_icon(c, kind, x + 22, FEATURES_BOTTOM + 54)
        _draw_paragraph(c, title, x, FEATURES_BOTTOM + 48, feature_w - 4, 28, 7, FONT_BOLD, COR_BRANCO, TA_CENTER)
        _draw_paragraph(c, desc, x, FEATURES_BOTTOM + 22, feature_w - 4, 26, 6.2, FONT_REGULAR, COR_BRANCO, TA_CENTER)

    total_x = MARGIN_X + full_w * 0.68
    _draw_text(c, "SUBTOTAL", total_x, FEATURES_BOTTOM + 70, 9, FONT_REGULAR, COR_BRANCO)
    _draw_text(c, contexto["SUBTOTAL"], PAGE_WIDTH - MARGIN_X - 55, FEATURES_BOTTOM + 70, 9, FONT_REGULAR, COR_BRANCO, "right")
    _draw_text(c, "TOTAL SERVIÇOS", total_x, FEATURES_BOTTOM + 46, 9, FONT_REGULAR, COR_BRANCO)
    _draw_text(c, contexto["TOTAL"], total_x, FEATURES_BOTTOM + 24, 13, FONT_BOLD, COR_ROXO)

    _draw_rect(c, MARGIN_X, NOTE_BOTTOM, full_w, NOTE_TOP - NOTE_BOTTOM, COR_AZUL_ESCURO)
    _draw_text(c, "Obrigado pela confiança!", MARGIN_X + 8, NOTE_BOTTOM + 25, 7.5, FONT_BOLD, COR_BRANCO)
    _draw_text(
        c,
        "Estamos à disposição para transformar seu evento em uma experiência inesquecível.",
        MARGIN_X + 8,
        NOTE_BOTTOM + 13,
        6.2,
        FONT_REGULAR,
        COR_BRANCO,
    )

    cal_x = PAGE_WIDTH / 2 + 10
    c.saveState()
    c.setStrokeColor(COR_BRANCO)
    c.rect(cal_x, NOTE_BOTTOM + 13, 17, 17, stroke=1, fill=0)
    c.line(cal_x, NOTE_BOTTOM + 25, cal_x + 17, NOTE_BOTTOM + 25)
    c.restoreState()

    _draw_text(c, f"Orçamento válido por {contexto['VALIDADE_DIAS']} dias.", cal_x + 28, NOTE_BOTTOM + 25, 7.5, FONT_REGULAR, COR_BRANCO)
    _draw_text(c, "Valores sujeitos a alterações sem aviso prévio.", cal_x + 28, NOTE_BOTTOM + 13, 6.2, FONT_REGULAR, COR_BRANCO)


def _draw_page_base(c: canvas.Canvas, contexto: dict[str, str], page_no: int, first_page: bool) -> None:
    _draw_page_header(c, contexto, page_no)

    if first_page:
        _draw_ac_bar(c, contexto)
        _draw_event_info(c, contexto)

    _draw_footer(c, contexto)


# =========================================================
# TABELAS DO ORÇAMENTO
# =========================================================

def _item_descricao(item: dict[str, Any]) -> str:
    equipamento = _safe_str(item.get("equipamento"), "Equipamento")
    dias_uso = max(_safe_int(item.get("dias_uso"), 1), 1)
    desconto = max(_safe_float(item.get("desconto"), 0.0), 0.0)

    detalhes = []

    if dias_uso > 1:
        detalhes.append(f"{dias_uso} dias")

    if desconto > 0:
        detalhes.append(f"desconto {_brl(desconto)}")

    if detalhes:
        return f"{equipamento} ({' | '.join(detalhes)})"

    return equipamento


def _draw_table_cell(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    text: Any,
    fill: colors.Color = colors.white,
    text_color: colors.Color = COR_CINZA_TEXTO,
    font: str = FONT_REGULAR,
    size: float = 7.8,
    align: str = "left",
    stroke: colors.Color = COR_CINZA_BORDA,
) -> None:
    _draw_rect(c, x, y, w, h, fill, stroke)
    align_map = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}
    pad_x = 4
    pad_top = 4.2
    _draw_paragraph(c, text, x + pad_x, y + h - pad_top, w - (2 * pad_x), h - 4, size, font, text_color, align_map.get(align, TA_LEFT))


def _row_height_for_text(text: str, width: float, min_h: float = 19, max_h: float = 36) -> float:
    size = 7.6
    lines = _split_text_to_lines(text, width - 8, FONT_REGULAR, size, max_lines=3)
    return min(max(min_h, 10 + (len(lines) * 8)), max_h)


def _draw_sala_table(
    c: canvas.Canvas,
    sala: dict[str, Any],
    y_top: float,
) -> float:
    x = MARGIN_X
    full_w = PAGE_WIDTH - (2 * MARGIN_X)
    col_desc = full_w * 0.48
    col_qtd = full_w * 0.09
    col_unit = full_w * 0.215
    col_total = full_w - col_desc - col_qtd - col_unit
    cols = [col_desc, col_qtd, col_unit, col_total]

    title_h = 18
    header_h = 17
    total_h = 19

    y = y_top - title_h
    _draw_table_cell(
        c,
        x,
        y,
        full_w,
        title_h,
        _safe_str(sala.get("nome"), "Sala sem nome"),
        fill=COR_AZUL_ESCURO,
        text_color=COR_BRANCO,
        font=FONT_BOLD,
        size=8.5,
        align="center",
        stroke=COR_AZUL_ESCURO,
    )

    y -= header_h
    headers = ["Descrição", "Qtd", "Preço Unitário", "Preço Total"]
    current_x = x

    for idx, header in enumerate(headers):
        _draw_table_cell(
            c,
            current_x,
            y,
            cols[idx],
            header_h,
            header,
            fill=colors.HexColor("#DDE5F3"),
            text_color=colors.black,
            font=FONT_BOLD,
            size=7.6,
            align="center",
        )
        current_x += cols[idx]

    itens = sala.get("itens") or []

    if not itens:
        itens = [
            {
                "equipamento": "Nenhum equipamento informado",
                "quantidade": 0,
                "valor_diaria": 0,
                "dias_uso": 1,
                "desconto": 0,
            }
        ]

    for item in itens:
        desc = _item_descricao(item)
        row_h = _row_height_for_text(desc, col_desc)
        y -= row_h
        values = [
            desc,
            str(max(_safe_int(item.get("quantidade"), 1), 0)),
            _brl(item.get("valor_diaria")),
            _brl(_calcular_item(item)),
        ]
        aligns = ["left", "right", "right", "right"]
        current_x = x

        for idx, value in enumerate(values):
            _draw_table_cell(
                c,
                current_x,
                y,
                cols[idx],
                row_h,
                value,
                fill=colors.white,
                text_color=COR_CINZA_TEXTO,
                font=FONT_REGULAR,
                size=7.4,
                align=aligns[idx],
            )
            current_x += cols[idx]

    y -= total_h
    label_w = col_desc + col_qtd + col_unit
    _draw_table_cell(
        c,
        x,
        y,
        label_w,
        total_h,
        "Total da Sala:",
        fill=COR_AZUL_ESCURO,
        text_color=COR_BRANCO,
        font=FONT_BOLD,
        size=8,
        align="right",
        stroke=COR_AZUL_ESCURO,
    )
    _draw_table_cell(
        c,
        x + label_w,
        y,
        col_total,
        total_h,
        _brl(_calcular_sala(sala)),
        fill=COR_AZUL_ESCURO,
        text_color=COR_BRANCO,
        font=FONT_BOLD,
        size=8,
        align="right",
        stroke=COR_AZUL_ESCURO,
    )

    return y


def _estimate_sala_height(sala: dict[str, Any]) -> float:
    full_w = PAGE_WIDTH - (2 * MARGIN_X)
    col_desc = full_w * 0.48
    itens = sala.get("itens") or [{}]
    rows_h = sum(_row_height_for_text(_item_descricao(item), col_desc) for item in itens)
    return 18 + 17 + rows_h + 19 + 10


def _draw_total_orcamento_table(c: canvas.Canvas, orcamento: dict[str, Any], y_top: float) -> float:
    x = MARGIN_X
    full_w = PAGE_WIDTH - (2 * MARGIN_X)
    h = 21
    label_w = full_w * 0.75
    y = y_top - h

    _draw_table_cell(
        c,
        x,
        y,
        label_w,
        h,
        "Valor do Orçamento:",
        fill=COR_AZUL_ESCURO,
        text_color=COR_BRANCO,
        font=FONT_BOLD,
        size=9,
        align="right",
        stroke=COR_AZUL_ESCURO,
    )
    _draw_table_cell(
        c,
        x + label_w,
        y,
        full_w - label_w,
        h,
        _brl(_calcular_orcamento(orcamento)),
        fill=COR_AZUL_ESCURO,
        text_color=COR_BRANCO,
        font=FONT_BOLD,
        size=9,
        align="right",
        stroke=COR_AZUL_ESCURO,
    )

    return y


def _draw_budget_tables(c: canvas.Canvas, orcamento: dict[str, Any], contexto: dict[str, str]) -> None:
    page_no = 1
    y = CONTENT_TOP_FIRST
    min_y = CONTENT_BOTTOM

    salas = orcamento.get("salas") or []

    if not salas:
        _draw_text(c, "Nenhuma sala/equipamento informado neste orçamento.", MARGIN_X, y - 10, 9, FONT_OBLIQUE, COR_CINZA_TEXTO)
        return

    for sala in salas:
        needed = _estimate_sala_height(sala)

        if y - needed < min_y:
            c.showPage()
            page_no += 1
            _draw_page_base(c, contexto, page_no, first_page=False)
            y = CONTENT_TOP_NEXT
            min_y = CONTENT_BOTTOM

        y = _draw_sala_table(c, sala, y)
        y -= 10

    total_needed = 34

    if y - total_needed < min_y:
        c.showPage()
        page_no += 1
        _draw_page_base(c, contexto, page_no, first_page=False)
        y = CONTENT_TOP_NEXT

    _draw_total_orcamento_table(c, orcamento, y)


# =========================================================
# API PÚBLICA - PDF DIRETO NO CÓDIGO
# =========================================================

def gerar_orcamento_pdf_bytes(
    orcamento: dict[str, Any],
    template_path: str | Path | None = None,
) -> bytes:
    """Gera o orçamento 100% em PDF, sem DOCX e sem conversão externa."""
    _validate_reportlab_available()

    orcamento_normalizado = _normalizar_orcamento(orcamento)
    contexto = _montar_contexto(orcamento_normalizado)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    c.setTitle(f"Orçamento {contexto['CODIGO_ORCAMENTO']}")
    c.setAuthor(contexto["EMPRESA_NOME"])
    c.setSubject("Orçamento de locação de equipamentos")

    _draw_page_base(c, contexto, page_no=1, first_page=True)
    _draw_budget_tables(c, orcamento_normalizado, contexto)

    c.save()
    buffer.seek(0)
    return buffer.read()


def salvar_orcamento_pdf(
    orcamento: dict[str, Any],
    output_path: str | Path,
    template_path: str | Path | None = None,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    pdf_bytes = gerar_orcamento_pdf_bytes(
        orcamento=orcamento,
        template_path=template_path,
    )

    output.write_bytes(pdf_bytes)
    return output


def gerar_orcamento_documentos(
    orcamento: dict[str, Any],
    template_path: str | Path | None = None,
) -> dict[str, Any]:
    pdf_bytes = gerar_orcamento_pdf_bytes(orcamento=orcamento, template_path=template_path)

    return {
        "docx_bytes": None,
        "pdf_bytes": pdf_bytes,
        "docx_filename": None,
        "pdf_filename": PDF_FILENAME_PADRAO,
        "docx_mime": None,
        "pdf_mime": "application/pdf",
    }


def gerar_orcamento_docx_bytes(*args: Any, **kwargs: Any) -> bytes:
    raise RuntimeError(
        "A geração DOCX foi desativada neste fluxo. Use gerar_orcamento_pdf_bytes para baixar somente PDF."
    )


def salvar_orcamento_docx(*args: Any, **kwargs: Any) -> Path:
    raise RuntimeError(
        "A geração DOCX foi desativada neste fluxo. Use salvar_orcamento_pdf."
    )