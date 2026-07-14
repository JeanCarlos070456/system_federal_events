from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import permission_required
from apps.core.logging import log_action
from apps.core.models import EstoqueVinculo, Orcamento, OrcamentoAmbiente, OrcamentoItem, Produto
from .forms import AmbienteForm, ItemForm, OrcamentoForm
from .services import OrcamentoService


def _get_app_user_id(request):
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return None

    if isinstance(app_user, dict):
        return app_user.get("id") or app_user.get("pk") or app_user.get("usuario_id")

    return getattr(app_user, "id", None) or getattr(app_user, "pk", None)


def _decimal_from_post(value) -> Decimal:
    if value is None:
        return Decimal("0.00")

    text = str(value).strip().replace("R$", "").replace(" ", "")

    if not text:
        return Decimal("0.00")

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _produto_catalogo_descricao(produto: Produto) -> str:
    partes = []

    if produto.categoria:
        partes.append(produto.categoria)

    if produto.marca:
        partes.append(produto.marca)

    if produto.modelo:
        partes.append(produto.modelo)

    return " · ".join(partes)


def _ambiente_titulo_oficial(tipo: str | None, nome: str | None = None) -> str:
    """
    Define o título oficial do ambiente.

    Regra:
    - Se o usuário informou "Nome do ambiente", esse nome é o título oficial.
    - Se não informou nome, o título oficial será o tipo selecionado/digitado.

    Evita duplicações como "Auditório Auditório" ou "Outro SUBLOCACAO".
    """
    nome_raw = (nome or "").strip()

    if nome_raw:
        return nome_raw[:255]

    tipo_raw = (tipo or "").strip()

    tipos_padrao = {
        "sala": "Sala",
        "auditorio": "Auditório",
        "auditório": "Auditório",
        "credenciamento": "Credenciamento",
        "outro": "Outro",
    }

    tipo_label = tipos_padrao.get(tipo_raw.lower(), tipo_raw.title() if tipo_raw else "Ambiente")

    return tipo_label[:255]


STATUS_ANALISE_VALUES = [
    "Em análise",
    "Em analise",
    "Rascunho",
    "Enviado",
    "Reprovado",
    "Cancelado",
    "",
]

STATUS_APROVADO_VALUES = [
    "Aprovado",
    "Concluído",
    "Concluido",
    "Finalizado",
]


def normalizar_status_orcamento(status: str | None) -> str:
    status = (status or "").strip()

    if status in STATUS_APROVADO_VALUES:
        return "Aprovado"

    return "Em análise"


@permission_required("Orçamento")
def produtos_autocomplete(request):
    q = (request.GET.get("q") or "").strip()

    if len(q) < 2:
        return JsonResponse({"results": []})

    produtos = (
        Produto.objects
        .filter(
            Q(nome__icontains=q)
            | Q(categoria__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(descricao__icontains=q)
        )
        .order_by("nome", "categoria", "marca", "modelo")
    )

    results = []
    vistos = set()

    for produto in produtos[:80]:
        key = (
            (produto.nome or "").strip().lower(),
            (produto.categoria or "").strip().lower(),
            (produto.marca or "").strip().lower(),
            (produto.modelo or "").strip().lower(),
        )

        if key in vistos:
            continue

        vistos.add(key)

        descricao_catalogo = _produto_catalogo_descricao(produto)

        results.append({
            "nome": produto.nome,
            "descricao": descricao_catalogo,
            "categoria": produto.categoria or "",
            "marca": produto.marca or "",
            "modelo": produto.modelo or "",
            "valor_diaria": str(produto.valor_diaria or Decimal("0.00")),
        })

        if len(results) >= 12:
            break

    return JsonResponse({"results": results})


@permission_required("Orçamento")
def index(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    qs = Orcamento.objects.select_related("cliente").all()

    if q:
        qs = qs.filter(
            Q(codigo__icontains=q)
            | Q(evento_nome__icontains=q)
            | Q(cliente_nome__icontains=q)
            | Q(cliente__nome__icontains=q)
        )

    if status == "Em análise":
        qs = qs.filter(status__in=STATUS_ANALISE_VALUES)
    elif status == "Aprovado":
        qs = qs.filter(status__in=STATUS_APROVADO_VALUES)

    status_options = [
        "Em análise",
        "Aprovado",
    ]

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))

    for orcamento in page_obj.object_list:
        orcamento.status_visual = normalizar_status_orcamento(orcamento.status)

    context = {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "status_options": status_options,
        "page_title": "Orçamentos",
    }

    return render(request, "orcamentos/index.html", context)


@permission_required("Orçamento", "pode_criar")
def create(request):
    form = OrcamentoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.codigo = OrcamentoService.gerar_codigo()
        obj.status = normalizar_status_orcamento(obj.status)

        if obj.cliente:
            obj.cliente_nome = obj.cliente.nome
            obj.cliente_documento = obj.cliente.documento

        app_user_id = _get_app_user_id(request)

        if app_user_id:
            obj.criado_por_id = app_user_id
            obj.atualizado_por_id = app_user_id

        obj.save()

        log_action(
            request,
            "orcamentos",
            "criar",
            "orcamento",
            obj.id,
            "Orçamento criado",
        )

        messages.success(request, "Orçamento criado com sucesso.")
        return redirect("orcamentos:detail", pk=obj.pk)

    return render(
        request,
        "orcamentos/form.html",
        {
            "form": form,
            "page_title": "Novo Orçamento",
        },
    )


@permission_required("Orçamento")
def detail(request, pk):
    orcamento = get_object_or_404(
        Orcamento.objects.prefetch_related("ambientes__itens", "itens"),
        pk=pk,
    )

    ambiente_form = AmbienteForm()
    item_form = ItemForm()

    context = {
        "orcamento": orcamento,
        "ambiente_form": ambiente_form,
        "item_form": item_form,
        "produtos_autocomplete_url": "orcamentos:produtos_autocomplete",
        "contrato_clausulas_padrao": OrcamentoService.contrato_clausulas_padrao_lista(),
        "status_visual": normalizar_status_orcamento(orcamento.status),
        "page_title": orcamento.codigo,
    }

    return render(request, "orcamentos/detail.html", context)


@permission_required("Orçamento", "pode_editar")
def update(request, pk):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    form = OrcamentoForm(request.POST or None, instance=orcamento)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.status = normalizar_status_orcamento(obj.status)

        if obj.cliente:
            obj.cliente_nome = obj.cliente.nome
            obj.cliente_documento = obj.cliente.documento

        app_user_id = _get_app_user_id(request)

        if app_user_id:
            obj.atualizado_por_id = app_user_id

        obj.save()
        OrcamentoService.recalcular_orcamento(obj)

        messages.success(request, "Orçamento atualizado com sucesso.")
        return redirect("orcamentos:detail", pk=obj.pk)

    return render(
        request,
        "orcamentos/form.html",
        {
            "form": form,
            "orcamento": orcamento,
            "page_title": "Editar Orçamento",
        },
    )


@permission_required("Orçamento")
def baixar_orcamento_pdf(request, pk):
    orcamento = get_object_or_404(
        Orcamento.objects
        .select_related("cliente")
        .prefetch_related("ambientes__itens"),
        pk=pk,
    )

    pdf_bytes = OrcamentoService.gerar_pdf_orcamento(orcamento)

    filename = f"orcamento_{orcamento.codigo}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@permission_required("Orçamento")
def baixar_contrato_pdf(request, pk):
    orcamento = get_object_or_404(
        Orcamento.objects
        .select_related("cliente")
        .prefetch_related("ambientes__itens"),
        pk=pk,
    )

    titulos = request.POST.getlist("clausula_titulo[]")
    conteudos = request.POST.getlist("clausula_conteudo[]")

    clausulas = []
    for titulo, conteudo in zip(titulos, conteudos):
        titulo = (titulo or "").strip()
        conteudo = (conteudo or "").strip()

        if titulo or conteudo:
            clausulas.append({
                "titulo": titulo,
                "conteudo": conteudo,
            })

    if not clausulas:
        clausulas = OrcamentoService.contrato_clausulas_padrao_lista()

    assinado_empresa = request.POST.get("assinado_empresa") == "1"

    pdf_bytes = OrcamentoService.gerar_pdf_contrato(
        orcamento=orcamento,
        clausulas=clausulas,
        assinado_empresa=assinado_empresa,
    )

    filename = f"contrato_orcamento_{orcamento.codigo}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@permission_required("Orçamento", "pode_editar")
def add_ambiente(request, pk):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    form = AmbienteForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ambiente = form.save(commit=False)
        ambiente.orcamento = orcamento
        ambiente.tipo = (ambiente.tipo or "").strip()
        ambiente.nome = _ambiente_titulo_oficial(
            tipo=ambiente.tipo,
            nome=ambiente.nome,
        )
        ambiente.save()

        messages.success(request, f"Ambiente '{ambiente.nome}' adicionado.")

    elif request.method == "POST":
        messages.error(request, "Não foi possível adicionar o ambiente. Verifique os campos obrigatórios.")

    return redirect("orcamentos:detail", pk=orcamento.pk)


@permission_required("Orçamento", "pode_editar")
@transaction.atomic
def delete_ambiente(request, pk, ambiente_id):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    ambiente = get_object_or_404(
        OrcamentoAmbiente,
        pk=ambiente_id,
        orcamento=orcamento,
    )

    if request.method == "POST":
        vinculos_estoque = (
            EstoqueVinculo.objects
            .filter(orcamento=orcamento, ambiente=ambiente)
            .exclude(status__in=["Cancelado", "Devolvido"])
            .exists()
        )

        if vinculos_estoque:
            messages.error(
                request,
                "Este ambiente já possui códigos vinculados no Estoque. Remova os vínculos no Estoque antes de excluir o ambiente.",
            )
            return redirect("orcamentos:detail", pk=orcamento.pk)

        nome_ambiente = _ambiente_titulo_oficial(ambiente.tipo, ambiente.nome)
        total_itens = ambiente.itens.count()

        ambiente.delete()
        OrcamentoService.recalcular_orcamento(orcamento)

        if total_itens:
            messages.success(
                request,
                f"Ambiente '{nome_ambiente}' removido com {total_itens} item(ns).",
            )
        else:
            messages.success(request, f"Ambiente '{nome_ambiente}' removido.")

    return redirect("orcamentos:detail", pk=orcamento.pk)


@permission_required("Orçamento", "pode_editar")
def add_item(request, pk, ambiente_id):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    ambiente = get_object_or_404(
        OrcamentoAmbiente,
        pk=ambiente_id,
        orcamento=orcamento,
    )

    form = ItemForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)

        item.orcamento = orcamento
        item.ambiente = ambiente

        item.produto = None

        catalogo_descricao = (request.POST.get("catalogo_descricao") or "").strip()
        catalogo_valor_diaria = _decimal_from_post(request.POST.get("catalogo_valor_diaria"))

        if not item.descricao and catalogo_descricao:
            item.descricao = catalogo_descricao

        if (item.valor_diaria is None or item.valor_diaria <= 0) and catalogo_valor_diaria > 0:
            item.valor_diaria = catalogo_valor_diaria

        OrcamentoService.salvar_item(item)

        messages.success(request, "Item adicionado ao orçamento.")

    else:
        messages.error(request, "Não foi possível adicionar o item. Verifique os campos obrigatórios.")

    return redirect("orcamentos:detail", pk=orcamento.pk)


@permission_required("Orçamento", "pode_editar")
@transaction.atomic
def update_item(request, pk, item_id):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    item = get_object_or_404(
        OrcamentoItem,
        pk=item_id,
        orcamento=orcamento,
    )

    if request.method == "POST":
        vinculos_estoque = (
            EstoqueVinculo.objects
            .filter(orcamento=orcamento, item=item)
            .exclude(status__in=["Cancelado", "Devolvido"])
            .exists()
        )

        if vinculos_estoque:
            messages.error(
                request,
                "Este item já possui código vinculado no Estoque. Remova o vínculo no Estoque antes de editar o equipamento.",
            )
            return redirect("orcamentos:detail", pk=orcamento.pk)

        equipamento = (request.POST.get("equipamento") or "").strip()
        descricao = (request.POST.get("descricao") or "").strip()

        try:
            quantidade = int(request.POST.get("quantidade") or 1)
        except (TypeError, ValueError):
            quantidade = 1

        try:
            dias_uso = int(request.POST.get("dias_uso") or 1)
        except (TypeError, ValueError):
            dias_uso = 1

        try:
            ordem = int(request.POST.get("ordem") or 0)
        except (TypeError, ValueError):
            ordem = 0

        valor_diaria = _decimal_from_post(request.POST.get("valor_diaria"))
        desconto = _decimal_from_post(request.POST.get("desconto"))

        if not equipamento:
            messages.error(request, "Informe o nome do equipamento.")
            return redirect("orcamentos:detail", pk=orcamento.pk)

        if quantidade < 1:
            quantidade = 1

        if dias_uso < 1:
            dias_uso = 1

        if valor_diaria < Decimal("0.00"):
            valor_diaria = Decimal("0.00")

        if desconto < Decimal("0.00"):
            desconto = Decimal("0.00")

        item.produto = None
        item.orcamento = orcamento
        item.equipamento = equipamento
        item.descricao = descricao
        item.quantidade = quantidade
        item.dias_uso = dias_uso
        item.valor_diaria = valor_diaria
        item.desconto = desconto
        item.ordem = ordem

        OrcamentoService.salvar_item(item)

        messages.success(request, "Item atualizado com sucesso.")

    return redirect("orcamentos:detail", pk=orcamento.pk)

@permission_required("Orçamento", "pode_editar")
def delete_item(request, pk, item_id):
    orcamento = get_object_or_404(Orcamento, pk=pk)
    item = get_object_or_404(OrcamentoItem, pk=item_id, orcamento=orcamento)

    if request.method == "POST":
        item.delete()
        OrcamentoService.recalcular_orcamento(orcamento)

        messages.success(request, "Item removido.")

    return redirect("orcamentos:detail", pk=orcamento.pk)