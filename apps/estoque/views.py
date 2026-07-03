from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse

from apps.accounts.decorators import permission_required
from apps.core.models import EstoqueVinculo, Orcamento, OrcamentoItem, Produto, UsuarioApp
from .forms import EstoqueVinculoForm
from .services import EstoqueService


def _get_user_perfil(request) -> str:
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return ""

    if isinstance(app_user, dict):
        return str(app_user.get("perfil") or "").strip()

    return str(getattr(app_user, "perfil", "") or "").strip()


def _get_app_user_id(request):
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return None

    if isinstance(app_user, dict):
        return app_user.get("id") or app_user.get("pk") or app_user.get("usuario_id")

    return getattr(app_user, "id", None) or getattr(app_user, "pk", None)


def _produto_novo_url(codigo: str | None = None) -> str:
    url = None

    for route_name in ("produtos:create", "produtos:novo"):
        try:
            url = reverse(route_name)
            break
        except NoReverseMatch:
            continue

    if not url:
        url = "/produtos/novo/"

    codigo = str(codigo or "").strip()

    if codigo:
        separador = "&" if "?" in url else "?"
        url = f"{url}{separador}{urlencode({'codigo': codigo})}"

    return url


@permission_required("Estoque")
def verificar_cod_produto(request):
    codigo = str(request.GET.get("cod") or "").strip()

    existe = False

    if codigo:
        existe = Produto.objects.filter(codigo__iexact=codigo).exists()

    return JsonResponse(
        {
            "exists": existe,
            "codigo": codigo,
            "create_url": _produto_novo_url(codigo),
            "message": (
                "Produto encontrado."
                if existe
                else "Esse Produto não está cadastrado no sistema. Deseja cadastrar?"
            ),
        }
    )


@permission_required("Estoque")
def index(request):
    eventos = list(
        Orcamento.objects
        .filter(financeiro__in=["Parcial", "Pago", "Atrasado"])
        .exclude(status__in=["Cancelado", "Reprovado"])
        .select_related("cliente")
        .prefetch_related("itens__estoque_vinculos")
        .order_by("-created_at")[:100]
    )

    EstoqueService.aplicar_status_estoque_eventos(eventos)

    perfil = _get_user_perfil(request)
    pode_ver_valores = perfil == "admin_empresa"

    return render(
        request,
        "estoque/index.html",
        {
            "eventos": eventos,
            "page_title": "Estoque",
            "pode_ver_valores": pode_ver_valores,
        },
    )


@permission_required("Estoque")
def detail(request, orcamento_id):
    orcamento = get_object_or_404(
        Orcamento.objects
        .select_related("cliente")
        .prefetch_related(
            "ambientes__itens__estoque_vinculos",
            "itens__estoque_vinculos",
        ),
        pk=orcamento_id,
    )

    status_info = EstoqueService.calcular_status_estoque(orcamento)
    grupos_ambientes = EstoqueService.montar_grupos_por_ambiente(orcamento)

    perfil = _get_user_perfil(request)
    pode_ver_valores = perfil == "admin_empresa"

    return render(
        request,
        "estoque/detail.html",
        {
            "orcamento": orcamento,
            "status_info": status_info,
            "grupos_ambientes": grupos_ambientes,
            "page_title": f"Estoque {orcamento.codigo}",
            "pode_ver_valores": pode_ver_valores,
        },
    )


@permission_required("Estoque", "pode_criar")
def vincular(request, item_id):
    item = get_object_or_404(
        OrcamentoItem.objects.select_related("orcamento", "ambiente"),
        pk=item_id,
    )

    form = EstoqueVinculoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        patrimonio = form.cleaned_data.get("patrimonio")
        app_user_id = _get_app_user_id(request)

        usuario = None

        if app_user_id:
            usuario = UsuarioApp.objects.filter(id=app_user_id).first()

        try:
            EstoqueService.vincular_patrimonio(
                item=item,
                patrimonio=patrimonio,
                cod_patrimonio=form.cleaned_data["cod_patrimonio"],
                usuario=usuario,
                descricao=form.cleaned_data.get("descricao"),
                quantidade=form.cleaned_data.get("quantidade"),
                status=form.cleaned_data.get("status"),
                observacoes=form.cleaned_data.get("observacoes"),
            )

        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("estoque:vincular", item_id=item.id)

        messages.success(request, "Patrimônio vinculado ao evento.")
        return redirect("estoque:detail", orcamento_id=item.orcamento_id)

    return render(
        request,
        "estoque/vincular.html",
        {
            "form": form,
            "item": item,
            "page_title": "Vincular COD",
            "verificar_cod_produto_url": reverse("estoque:verificar_cod_produto"),
        },
    )


@permission_required("Estoque", "pode_editar")
def excluir_vinculo(request, vinculo_id):
    vinculo = get_object_or_404(
        EstoqueVinculo.objects.select_related("orcamento", "patrimonio"),
        pk=vinculo_id,
    )

    orcamento_id = vinculo.orcamento_id

    if request.method == "POST":
        cod = vinculo.cod_patrimonio

        EstoqueService.excluir_vinculo(vinculo)

        messages.success(
            request,
            f"COD {cod} removido do estoque. O item voltou a ficar disponível para novo vínculo.",
        )

    return redirect("estoque:detail", orcamento_id=orcamento_id)