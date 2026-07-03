from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from apps.accounts.decorators import permission_required
from apps.core.models import FinanceiroMovimento

from .forms import FinanceiroPagamentoForm
from .services import FinanceiroService


def _get_app_user_id(request):
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return None

    if isinstance(app_user, dict):
        return app_user.get("id") or app_user.get("pk") or app_user.get("usuario_id")

    return getattr(app_user, "id", None) or getattr(app_user, "pk", None)


@permission_required("Financeiro")
def index(request):
    q = request.GET.get("q", "").strip()
    financeiro = request.GET.get("financeiro", "").strip()

    qs = FinanceiroService.orcamentos_queryset(q=q)

    linhas = FinanceiroService.montar_linhas_orcamentos(
        qs,
        status_filter=financeiro,
    )

    resumo = FinanceiroService.resumo_geral(linhas)

    page_obj = Paginator(linhas, 20).get_page(request.GET.get("page"))

    movimentos_recentes = (
        FinanceiroMovimento.objects
        .select_related("orcamento", "cliente")
        .order_by("-created_at")[:10]
    )

    context = {
        "page_obj": page_obj,
        "resumo": resumo,
        "q": q,
        "financeiro": financeiro,
        "status_options": FinanceiroService.STATUS_OPTIONS,
        "movimentos_recentes": movimentos_recentes,
        "page_title": "Financeiro",
    }

    return render(request, "financeiro/index.html", context)


@permission_required("Financeiro", "pode_criar")
def create(request):
    orcamento_id = request.POST.get("orcamento") or request.GET.get("orcamento")

    form = FinanceiroPagamentoForm(
        request.POST or None,
        orcamento_id=orcamento_id,
    )

    if request.method == "POST" and form.is_valid():
        try:
            movimento = FinanceiroService.registrar_pagamento(
                orcamento=form.cleaned_data["orcamento"],
                valor=form.cleaned_data["valor"],
                forma_pagamento=form.cleaned_data.get("forma_pagamento"),
                data_pagamento=form.cleaned_data.get("data_pagamento"),
                descricao=form.cleaned_data.get("descricao"),
                comprovante_url=form.cleaned_data.get("comprovante_url"),
                observacoes=form.cleaned_data.get("observacoes"),
                usuario_id=_get_app_user_id(request),
            )

            messages.success(
                request,
                f"Pagamento lançado com sucesso: {FinanceiroService.money(movimento.valor)}.",
            )

            return redirect("financeiro:index")

        except ValueError as exc:
            form.add_error(None, str(exc))
            messages.error(request, str(exc))

    context = {
        "form": form,
        "page_title": "Lançar Pagamento",
    }

    return render(request, "financeiro/form.html", context)