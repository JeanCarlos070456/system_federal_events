from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import FinanceiroMovimento, Orcamento


class FinanceiroService:
    STATUS_OPTIONS = [
        "Pendente",
        "Parcial",
        "Pago",
        "Atrasado",
        "Cancelado",
    ]

    STATUS_PAGAMENTO_VALIDOS = {"Pago", "Parcial"}

    @staticmethod
    def normalizar(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def normalizar_lower(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0.00")

        if isinstance(value, Decimal):
            return value

        text = str(value).strip().replace("R$", "").replace(" ", "")

        if not text:
            return Decimal("0.00")

        if "," in text:
            text = text.replace(".", "").replace(",", ".")

        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    @classmethod
    def money(cls, value: Any) -> str:
        value = cls._decimal(value)
        formatted = f"{value:,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"

    @staticmethod
    def date(value) -> str:
        if not value:
            return "-"

        try:
            return value.strftime("%d/%m/%Y")
        except AttributeError:
            return str(value)

    @staticmethod
    def status_slug(status: str) -> str:
        mapa = {
            "Pendente": "pendente",
            "Parcial": "parcial",
            "Pago": "pago",
            "Atrasado": "atrasado",
            "Cancelado": "cancelado",
        }

        return mapa.get(status, "pendente")

    @classmethod
    def orcamentos_queryset(cls, q: str | None = None):
        qs = (
            Orcamento.objects
            .select_related("cliente")
            .prefetch_related("financeiro_movimentos")
            .all()
            .order_by("-created_at")
        )

        q = cls.normalizar(q)

        if q:
            qs = qs.filter(
                Q(codigo__icontains=q)
                | Q(evento_nome__icontains=q)
                | Q(cliente_nome__icontains=q)
                | Q(cliente__nome__icontains=q)
                | Q(local_evento__icontains=q)
            )

        return qs

    @classmethod
    def _movimentos_do_orcamento(cls, orcamento: Orcamento):
        try:
            return list(orcamento.financeiro_movimentos.all())
        except Exception:
            return list(
                FinanceiroMovimento.objects
                .filter(orcamento=orcamento)
                .select_related("orcamento", "cliente")
            )

    @classmethod
    def _vencimento_orcamento(cls, orcamento: Orcamento, movimentos: list[FinanceiroMovimento]):
        vencimentos = []

        for movimento in movimentos:
            if movimento.status == "Cancelado":
                continue

            if movimento.tipo != "Receita":
                continue

            if movimento.data_vencimento:
                vencimentos.append(movimento.data_vencimento)

        if vencimentos:
            return min(vencimentos)

        return orcamento.data_inicio or orcamento.data_fim

    @classmethod
    def calcular_status_financeiro(
        cls,
        *,
        orcamento: Orcamento,
        valor_final: Decimal,
        recebido: Decimal,
        saldo: Decimal,
        vencimento,
    ) -> str:
        if orcamento.financeiro == "Cancelado":
            return "Cancelado"

        if valor_final <= Decimal("0.00"):
            return "Pendente"

        if saldo <= Decimal("0.00") and recebido >= valor_final:
            return "Pago"

        hoje = timezone.localdate()

        if vencimento and vencimento < hoje and saldo > Decimal("0.00"):
            return "Atrasado"

        if recebido > Decimal("0.00"):
            return "Parcial"

        return "Pendente"

    @classmethod
    def calcular_resumo_orcamento(cls, orcamento: Orcamento) -> dict:
        movimentos = cls._movimentos_do_orcamento(orcamento)

        valor_final = cls._decimal(orcamento.valor_final)
        recebido = Decimal("0.00")
        estornado = Decimal("0.00")

        ultimo_pagamento = None

        for movimento in movimentos:
            status = movimento.status
            tipo = movimento.tipo
            valor = cls._decimal(movimento.valor)

            if status == "Cancelado":
                continue

            if tipo == "Receita" and status in cls.STATUS_PAGAMENTO_VALIDOS:
                recebido += valor

                if movimento.data_pagamento:
                    if not ultimo_pagamento or movimento.data_pagamento > ultimo_pagamento:
                        ultimo_pagamento = movimento.data_pagamento

            elif tipo == "Estorno" and status in cls.STATUS_PAGAMENTO_VALIDOS:
                estornado += valor

        recebido = max(recebido - estornado, Decimal("0.00"))
        saldo = max(valor_final - recebido, Decimal("0.00"))
        vencimento = cls._vencimento_orcamento(orcamento, movimentos)

        status = cls.calcular_status_financeiro(
            orcamento=orcamento,
            valor_final=valor_final,
            recebido=recebido,
            saldo=saldo,
            vencimento=vencimento,
        )

        return {
            "valor_final": valor_final,
            "recebido": recebido,
            "saldo": saldo,
            "vencimento": vencimento,
            "ultimo_pagamento": ultimo_pagamento,
            "status": status,
            "movimentos_count": len(movimentos),
        }

    @classmethod
    def sincronizar_status_orcamento(cls, orcamento: Orcamento, status: str) -> None:
        if not orcamento:
            return

        if orcamento.financeiro == status:
            return

        orcamento.financeiro = status
        orcamento.save(update_fields=["financeiro", "updated_at"])

    @classmethod
    def montar_linha_orcamento(cls, orcamento: Orcamento, sincronizar: bool = True) -> dict:
        resumo = cls.calcular_resumo_orcamento(orcamento)

        if sincronizar and orcamento.financeiro != "Cancelado":
            cls.sincronizar_status_orcamento(orcamento, resumo["status"])

        cliente_nome = (
            getattr(orcamento.cliente, "nome", None)
            or orcamento.cliente_nome
            or "Cliente não informado"
        )

        return {
            "orcamento": orcamento,
            "codigo": orcamento.codigo,
            "evento": orcamento.evento_nome,
            "cliente": cliente_nome,
            "data_evento": cls.date(orcamento.data_inicio),
            "vencimento": cls.date(resumo["vencimento"]),
            "ultimo_pagamento": cls.date(resumo["ultimo_pagamento"]),
            "valor_final": resumo["valor_final"],
            "recebido": resumo["recebido"],
            "saldo": resumo["saldo"],
            "valor_final_fmt": cls.money(resumo["valor_final"]),
            "recebido_fmt": cls.money(resumo["recebido"]),
            "saldo_fmt": cls.money(resumo["saldo"]),
            "status": resumo["status"],
            "status_slug": cls.status_slug(resumo["status"]),
            "movimentos_count": resumo["movimentos_count"],
        }

    @classmethod
    def montar_linhas_orcamentos(cls, qs, status_filter: str | None = None) -> list[dict]:
        linhas = []

        status_filter = cls.normalizar(status_filter)

        for orcamento in qs:
            linha = cls.montar_linha_orcamento(orcamento)

            if status_filter and linha["status"] != status_filter:
                continue

            linhas.append(linha)

        return linhas

    @classmethod
    def resumo_geral(cls, linhas: list[dict]) -> dict:
        total_receber = sum((linha["valor_final"] for linha in linhas), Decimal("0.00"))
        total_recebido = sum((linha["recebido"] for linha in linhas), Decimal("0.00"))
        total_aberto = sum((linha["saldo"] for linha in linhas), Decimal("0.00"))
        total_atrasado = sum(
            (linha["saldo"] for linha in linhas if linha["status"] == "Atrasado"),
            Decimal("0.00"),
        )

        qtd_pendente = len([linha for linha in linhas if linha["status"] == "Pendente"])
        qtd_parcial = len([linha for linha in linhas if linha["status"] == "Parcial"])
        qtd_pago = len([linha for linha in linhas if linha["status"] == "Pago"])
        qtd_atrasado = len([linha for linha in linhas if linha["status"] == "Atrasado"])

        return {
            "total_receber": total_receber,
            "total_recebido": total_recebido,
            "total_aberto": total_aberto,
            "total_atrasado": total_atrasado,
            "total_receber_fmt": cls.money(total_receber),
            "total_recebido_fmt": cls.money(total_recebido),
            "total_aberto_fmt": cls.money(total_aberto),
            "total_atrasado_fmt": cls.money(total_atrasado),
            "qtd_pendente": qtd_pendente,
            "qtd_parcial": qtd_parcial,
            "qtd_pago": qtd_pago,
            "qtd_atrasado": qtd_atrasado,
            "qtd_orcamentos": len(linhas),
        }

    @classmethod
    @transaction.atomic
    def registrar_pagamento(
        cls,
        *,
        orcamento: Orcamento,
        valor: Decimal,
        forma_pagamento: str | None = None,
        data_pagamento=None,
        descricao: str | None = None,
        comprovante_url: str | None = None,
        observacoes: str | None = None,
        usuario_id=None,
    ) -> FinanceiroMovimento:
        if not orcamento:
            raise ValueError("Selecione um orçamento para lançar o pagamento.")

        valor = cls._decimal(valor)

        if valor <= Decimal("0.00"):
            raise ValueError("Informe um valor de pagamento maior que zero.")

        orcamento = (
            Orcamento.objects
            .select_for_update()
            .select_related("cliente")
            .get(pk=orcamento.pk)
        )

        if orcamento.financeiro == "Cancelado":
            raise ValueError("Não é possível lançar pagamento em orçamento cancelado.")

        resumo_atual = cls.calcular_resumo_orcamento(orcamento)
        saldo_atual = resumo_atual["saldo"]

        if saldo_atual > Decimal("0.00") and valor > saldo_atual:
            raise ValueError(
                f"O valor informado é maior que o saldo em aberto. Saldo atual: {cls.money(saldo_atual)}."
            )

        descricao = cls.normalizar(descricao)

        if not descricao:
            descricao = f"Pagamento do orçamento {orcamento.codigo} - {orcamento.evento_nome}"

        data_pagamento = data_pagamento or timezone.localdate()

        movimento = FinanceiroMovimento.objects.create(
            orcamento=orcamento,
            cliente=orcamento.cliente,
            tipo="Receita",
            categoria="Pagamento de orçamento",
            descricao=descricao,
            valor=valor,
            forma_pagamento=cls.normalizar(forma_pagamento),
            status="Pago",
            data_vencimento=orcamento.data_inicio or orcamento.data_fim,
            data_pagamento=data_pagamento,
            comprovante_url=cls.normalizar(comprovante_url),
            observacoes=cls.normalizar(observacoes),
            criado_por_id=usuario_id,
            atualizado_por_id=usuario_id,
        )

        resumo_novo = cls.calcular_resumo_orcamento(orcamento)
        cls.sincronizar_status_orcamento(orcamento, resumo_novo["status"])

        return movimento