from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounts.decorators import permission_required
from apps.core.models import EstoqueVinculo, Orcamento, UsuarioApp
from .services import MovimentoOperacionalService


def _get_app_user_id(request):
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return None

    if isinstance(app_user, dict):
        return app_user.get("id") or app_user.get("pk") or app_user.get("usuario_id")

    return getattr(app_user, "id", None) or getattr(app_user, "pk", None)


def _get_usuario_app(request):
    app_user_id = _get_app_user_id(request)

    if not app_user_id:
        return None

    return UsuarioApp.objects.filter(id=app_user_id).first()


def _redirect_index_with_params(tab: str, orcamento_id=None):
    url = reverse("retirada_devolucao:index")

    if orcamento_id:
        param = "retirada_orcamento" if tab == "retirada" else "devolucao_orcamento"
        return f"{url}?tab={tab}&{param}={orcamento_id}"

    return f"{url}?tab={tab}"


@permission_required("Retirada e Devolução")
def index(request):
    active_tab = request.GET.get("tab", "retirada")

    if active_tab not in {"retirada", "devolucao"}:
        active_tab = "retirada"

    if request.method == "POST":
        modo = request.POST.get("modo", "retirada")

        if modo not in {"retirada", "devolucao"}:
            modo = "retirada"

        orcamento_id = request.POST.get("orcamento_id")
        responsavel_nome = request.POST.get("responsavel_nome")

        orcamento = get_object_or_404(Orcamento, pk=orcamento_id)
        usuario = _get_usuario_app(request)

        try:
            total = MovimentoOperacionalService.registrar_lote(
                modo=modo,
                orcamento=orcamento,
                responsavel_nome=responsavel_nome,
                usuario=usuario,
                request_user=getattr(request, "app_user", None),
                post=request.POST,
                files=request.FILES,
            )

            if modo == "retirada":
                messages.success(request, f"Retirada salva com sucesso. {total} equipamento(s) registrado(s).")
            else:
                messages.success(request, f"Devolução salva com sucesso. {total} equipamento(s) registrado(s).")

            return redirect(_redirect_index_with_params(modo, orcamento.id))

        except ValueError as exc:
            messages.error(request, str(exc))
            active_tab = modo

    retirada_eventos = list(MovimentoOperacionalService.eventos_queryset("retirada")[:300])
    devolucao_eventos = list(MovimentoOperacionalService.eventos_queryset("devolucao")[:300])

    retirada_id = request.GET.get("retirada_orcamento")
    devolucao_id = request.GET.get("devolucao_orcamento")

    retirada_orcamento = MovimentoOperacionalService.buscar_orcamento("retirada", retirada_id)
    devolucao_orcamento = MovimentoOperacionalService.buscar_orcamento("devolucao", devolucao_id)

    retirada_card = MovimentoOperacionalService.montar_card_evento(retirada_orcamento, "retirada")
    devolucao_card = MovimentoOperacionalService.montar_card_evento(devolucao_orcamento, "devolucao")

    retirada_grupos = MovimentoOperacionalService.montar_grupos_por_sala(retirada_orcamento, "retirada")
    devolucao_grupos = MovimentoOperacionalService.montar_grupos_por_sala(devolucao_orcamento, "devolucao")

    return render(
        request,
        "retirada_devolucao/index.html",
        {
            "active_tab": active_tab,
            "retirada_eventos": retirada_eventos,
            "devolucao_eventos": devolucao_eventos,
            "retirada_orcamento": retirada_orcamento,
            "devolucao_orcamento": devolucao_orcamento,
            "retirada_card": retirada_card,
            "devolucao_card": devolucao_card,
            "retirada_grupos": retirada_grupos,
            "devolucao_grupos": devolucao_grupos,
            "page_title": "Retirada e Devolução",
        },
    )


@permission_required("Retirada e Devolução", "pode_criar")
def movimentar(request, vinculo_id):
    """
    Compatibilidade com links antigos da tabela anterior.
    Redireciona para a nova tela por abas.
    """
    vinculo = get_object_or_404(EstoqueVinculo.objects.select_related("orcamento"), pk=vinculo_id)

    tab = "devolucao" if vinculo.status == "Retirado" else "retirada"

    return redirect(_redirect_index_with_params(tab, vinculo.orcamento_id))