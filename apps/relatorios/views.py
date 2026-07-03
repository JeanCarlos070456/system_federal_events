from __future__ import annotations

from django.db.models import Count, Sum
from django.shortcuts import render

from apps.accounts.decorators import permission_required
from apps.core.models import Cliente, EstoqueVinculo, FinanceiroMovimento, Orcamento, ProdutoPatrimonio


@permission_required("Relatórios")
def index(request):
    data = {
        "orcamentos_status": Orcamento.objects.values("status").annotate(total=Count("id"), valor=Sum("valor_final")).order_by("status"),
        "financeiro_status": FinanceiroMovimento.objects.values("status").annotate(total=Count("id"), valor=Sum("valor")).order_by("status"),
        "patrimonios_status": ProdutoPatrimonio.objects.values("status").annotate(total=Count("id")).order_by("status"),
        "clientes_status": Cliente.objects.values("status").annotate(total=Count("id")).order_by("status"),
        "estoque_status": EstoqueVinculo.objects.values("status").annotate(total=Count("id")).order_by("status"),
    }
    return render(request, "relatorios/index.html", {"data": data, "page_title": "Relatórios"})
