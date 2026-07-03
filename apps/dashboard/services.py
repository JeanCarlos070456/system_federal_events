from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum

from apps.core.models import (
    Cliente,
    EstoqueVinculo,
    FinanceiroMovimento,
    Orcamento,
    OrcamentoItem,
    Produto,
    ProdutoPatrimonio,
)


MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


STATUS_BLOQUEADOS = [
    "Manutenção",
    "manutenção",
    "MANUTENÇÃO",
    "Danificado",
    "danificado",
    "DANIFICADO",
    "Extraviado",
    "extraviado",
    "EXTRAVIADO",
    "Bloqueado",
    "bloqueado",
    "BLOQUEADO",
]


def _money(value) -> float:
    if value is None:
        return 0.0

    if isinstance(value, Decimal):
        return float(value)

    return float(value or 0)


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0.00")

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0.00")


def _month_label(value) -> str:
    if not value:
        return "Sem data"

    return f"{MESES_PT.get(value.month, value.month)}/{value.year}"


def _status_label(value) -> str:
    if not value:
        return "Sem status"

    return str(value).strip() or "Sem status"


class DashboardService:
    """
    Dashboard analítico do Federal Eventos.

    Regras principais:
    1. O Dashboard lê dados reais do Supabase/PostgreSQL via Django ORM.
    2. Para valores de orçamento, usa:
       - orcamentos.valor_final;
       - se zerado, orcamentos.valor_total;
       - se zerado, soma orcamento_itens.valor_total.
    3. Para ocupação de estoque, usa:
       - produto_patrimonios, quando houver dados;
       - se estiver vazio, usa estoque_vinculos.
    """

    @staticmethod
    def _orcamentos_base():
        return Orcamento.objects.all().order_by("-created_at")

    @staticmethod
    def _valor_orcamento_real(orcamento: Orcamento) -> Decimal:
        valor_final = _decimal(getattr(orcamento, "valor_final", None))
        valor_total = _decimal(getattr(orcamento, "valor_total", None))

        if valor_final > 0:
            return valor_final

        if valor_total > 0:
            return valor_total

        itens_total = (
            OrcamentoItem.objects
            .filter(orcamento_id=orcamento.id)
            .aggregate(total=Sum("valor_total"))
            .get("total")
        )

        return _decimal(itens_total)

    @staticmethod
    def _usar_produto_patrimonios() -> bool:
        return ProdutoPatrimonio.objects.exists()

    @staticmethod
    def _patrimonios_disponiveis() -> int:
        """
        Métrica superior do Dashboard.

        Se produto_patrimonios estiver vazio, usa estoque_vinculos como fonte
        operacional atual, porque é onde o banco real possui dados neste momento.
        """
        if DashboardService._usar_produto_patrimonios():
            return ProdutoPatrimonio.objects.filter(
                status__iexact="Disponível"
            ).count()

        return EstoqueVinculo.objects.filter(
            status__iexact="Vinculado"
        ).count()

    @staticmethod
    def _itens_retirados() -> int:
        return EstoqueVinculo.objects.filter(
            status__iexact="Retirado"
        ).count()

    @staticmethod
    def get_metrics() -> dict:
        orcamentos = list(DashboardService._orcamentos_base())

        valor_orcamentos = sum(
            (
                DashboardService._valor_orcamento_real(orcamento)
                for orcamento in orcamentos
            ),
            Decimal("0.00"),
        )

        valor_pago = sum(
            (
                DashboardService._valor_orcamento_real(orcamento)
                for orcamento in orcamentos
                if (orcamento.financeiro or "").strip().lower() == "pago"
            ),
            Decimal("0.00"),
        )

        valor_parcial = sum(
            (
                DashboardService._valor_orcamento_real(orcamento)
                for orcamento in orcamentos
                if (orcamento.financeiro or "").strip().lower() == "parcial"
            ),
            Decimal("0.00"),
        )

        financeiro_pago_real = (
            FinanceiroMovimento.objects
            .filter(status__iexact="Pago")
            .aggregate(total=Sum("valor"))
            .get("total")
        )

        financeiro_parcial_real = (
            FinanceiroMovimento.objects
            .filter(status__iexact="Parcial")
            .aggregate(total=Sum("valor"))
            .get("total")
        )

        if _decimal(financeiro_pago_real) > 0:
            valor_pago = _decimal(financeiro_pago_real)

        if _decimal(financeiro_parcial_real) > 0:
            valor_parcial = _decimal(financeiro_parcial_real)

        return {
            "clientes": Cliente.objects.count(),
            "produtos": Produto.objects.count(),
            "patrimonios_disponiveis": DashboardService._patrimonios_disponiveis(),
            "orcamentos": Orcamento.objects.count(),
            "orcamentos_aprovados": Orcamento.objects.filter(
                status__iexact="Aprovado"
            ).count(),
            "estoque_retirado": DashboardService._itens_retirados(),
            "valor_orcamentos": _money(valor_orcamentos),
            "valor_pago": _money(valor_pago),
            "valor_parcial": _money(valor_parcial),
            "valor_operacional": _money(valor_pago + valor_parcial),
        }

    @staticmethod
    def status_orcamentos() -> list[dict]:
        return list(
            Orcamento.objects
            .values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )

    @staticmethod
    def receita_operacional_por_mes() -> dict:
        """
        Receita operacional por mês.

        Considera orçamentos com financeiro Pago ou Parcial.
        Usa data_inicio como referência operacional.
        """
        orcamentos = (
            Orcamento.objects
            .filter(financeiro__in=["Pago", "Parcial", "pago", "parcial"])
            .exclude(data_inicio__isnull=True)
            .order_by("data_inicio")
        )

        acumulado: dict[str, Decimal] = {}
        quantidades: dict[str, int] = {}

        for orcamento in orcamentos:
            label = _month_label(orcamento.data_inicio)
            valor = DashboardService._valor_orcamento_real(orcamento)

            acumulado[label] = acumulado.get(label, Decimal("0.00")) + valor
            quantidades[label] = quantidades.get(label, 0) + 1

        labels = list(acumulado.keys())

        return {
            "labels": labels,
            "values": [_money(acumulado[label]) for label in labels],
            "counts": [quantidades.get(label, 0) for label in labels],
        }

    @staticmethod
    def patrimonios_por_status() -> dict:
        """
        Gráfico de ocupação do estoque.

        Regra:
        1. Se produto_patrimonios tiver dados, usa status dos patrimônios.
        2. Se produto_patrimonios estiver vazio, usa estoque_vinculos.
        """
        if DashboardService._usar_produto_patrimonios():
            rows = (
                ProdutoPatrimonio.objects
                .values("status")
                .annotate(total=Count("id"))
                .order_by("status")
            )
        else:
            rows = (
                EstoqueVinculo.objects
                .values("status")
                .annotate(total=Count("id"))
                .order_by("status")
            )

        labels = []
        valores = []

        for row in rows:
            labels.append(_status_label(row.get("status")))
            valores.append(row.get("total") or 0)

        return {
            "labels": labels,
            "values": valores,
        }

    @staticmethod
    def financeiro_por_status() -> dict:
        """
        Primeiro tenta usar FinanceiroMovimento.
        Se não houver movimentos financeiros com valor, usa o status financeiro
        dos orçamentos.
        """
        rows_movimentos = list(
            FinanceiroMovimento.objects
            .values("status")
            .annotate(
                total=Sum("valor"),
                quantidade=Count("id"),
            )
            .order_by("status")
        )

        movimentos_tem_valor = any(
            _decimal(row.get("total")) > 0
            for row in rows_movimentos
        )

        if rows_movimentos and movimentos_tem_valor:
            labels = []
            valores = []
            quantidades = []

            for row in rows_movimentos:
                labels.append(_status_label(row.get("status")))
                valores.append(_money(row.get("total")))
                quantidades.append(row.get("quantidade") or 0)

            return {
                "labels": labels,
                "values": valores,
                "counts": quantidades,
            }

        acumulado: dict[str, Decimal] = {}
        qtd: dict[str, int] = {}

        for orcamento in Orcamento.objects.all():
            status = _status_label(orcamento.financeiro)
            valor = DashboardService._valor_orcamento_real(orcamento)

            acumulado[status] = acumulado.get(status, Decimal("0.00")) + valor
            qtd[status] = qtd.get(status, 0) + 1

        labels = list(acumulado.keys())

        return {
            "labels": labels,
            "values": [_money(acumulado[label]) for label in labels],
            "counts": [qtd.get(label, 0) for label in labels],
        }

    @staticmethod
    def orcamentos_recentes(limit: int = 8) -> list[dict]:
        qs = (
            Orcamento.objects
            .select_related("cliente")
            .order_by("-created_at")[:limit]
        )

        registros = []

        for obj in qs:
            cliente_nome = "—"

            if obj.cliente:
                cliente_nome = obj.cliente.nome
            elif obj.cliente_nome:
                cliente_nome = obj.cliente_nome

            if obj.data_inicio and obj.data_fim:
                periodo = (
                    f"{obj.data_inicio.strftime('%d/%m/%Y')} "
                    f"a {obj.data_fim.strftime('%d/%m/%Y')}"
                )
            elif obj.data_inicio:
                periodo = obj.data_inicio.strftime("%d/%m/%Y")
            else:
                periodo = "—"

            valor = DashboardService._valor_orcamento_real(obj)

            registros.append({
                "codigo": obj.codigo or "—",
                "cliente": cliente_nome,
                "evento": obj.evento_nome or "—",
                "periodo": periodo,
                "local": obj.local_evento or "—",
                "status": obj.status or "—",
                "financeiro": obj.financeiro or "—",
                "valor": _money(valor),
            })

        return registros

    @staticmethod
    def alertas_operacionais() -> dict:
        orcamentos_atrasados = Orcamento.objects.filter(
            financeiro__iexact="Atrasado"
        )

        financeiro_atrasado_qtd = orcamentos_atrasados.count()

        financeiro_atrasado_valor = sum(
            (
                DashboardService._valor_orcamento_real(orcamento)
                for orcamento in orcamentos_atrasados
            ),
            Decimal("0.00"),
        )

        if DashboardService._usar_produto_patrimonios():
            equipamentos_bloqueados = ProdutoPatrimonio.objects.filter(
                status__in=STATUS_BLOQUEADOS
            ).count()
        else:
            equipamentos_bloqueados = EstoqueVinculo.objects.filter(
                status__in=STATUS_BLOQUEADOS
            ).count()

        devolucoes_pendentes = EstoqueVinculo.objects.filter(
            status__iexact="Retirado"
        ).count()

        return {
            "financeiro_atrasado_qtd": financeiro_atrasado_qtd,
            "financeiro_atrasado_valor": _money(financeiro_atrasado_valor),
            "equipamentos_bloqueados": equipamentos_bloqueados,
            "devolucoes_pendentes": devolucoes_pendentes,
        }

    @staticmethod
    def get_context() -> dict:
        return {
            "metrics": DashboardService.get_metrics(),
            "status_orcamentos": DashboardService.status_orcamentos(),
            "receita_chart": DashboardService.receita_operacional_por_mes(),
            "patrimonios_chart": DashboardService.patrimonios_por_status(),
            "financeiro_chart": DashboardService.financeiro_por_status(),
            "orcamentos_recentes": DashboardService.orcamentos_recentes(),
            "alertas": DashboardService.alertas_operacionais(),
        }