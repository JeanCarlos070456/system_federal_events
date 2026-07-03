from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import Cliente, Orcamento, OrcamentoAmbiente, OrcamentoItem


class OrcamentoForm(FederalModelForm):
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.order_by("nome"),
        required=False,
        label="Cliente cadastrado",
    )

    class Meta:
        model = Orcamento
        fields = [
            "cliente",
            "cliente_nome",
            "cliente_documento",
            "responsavel_cliente",
            "evento_nome",
            "local_evento",
            "data_envio",
            "validade_dias",
            "data_montagem",
            "data_inicio",
            "data_fim",
            "status",
            "financeiro",
            "valor_desconto",
            "valor_caucao",
            "observacoes",
            "condicoes_pagamento",
        ]
        widgets = {
            "data_envio": forms.DateInput(attrs={"type": "date"}),
            "data_montagem": forms.DateInput(attrs={"type": "date"}),
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "condicoes_pagamento": forms.Textarea(attrs={"rows": 3}),
        }


class AmbienteForm(FederalModelForm):
    class Meta:
        model = OrcamentoAmbiente
        fields = [
            "tipo",
            "nome",
            "ordem",
            "observacoes",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 2}),
        }


class ItemForm(FederalModelForm):
    """
    Item do orçamento.

    Regra:
    - Não vincula Produto físico nesta etapa.
    - O usuário informa/seleciona apenas o nome do equipamento.
    - O vínculo com código/COD real fica para o módulo Estoque.
    """

    class Meta:
        model = OrcamentoItem
        fields = [
            "equipamento",
            "descricao",
            "quantidade",
            "dias_uso",
            "valor_diaria",
            "desconto",
            "ordem",
        ]
        widgets = {
            "equipamento": forms.TextInput(
                attrs={
                    "placeholder": "Digite o nome do equipamento",
                    "autocomplete": "off",
                    "class": "orcamento-equipment-input",
                }
            ),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Descrição técnica, marca, modelo ou observação do item",
                }
            ),
            "quantidade": forms.NumberInput(
                attrs={
                    "min": "1",
                    "value": "1",
                }
            ),
            "dias_uso": forms.NumberInput(
                attrs={
                    "min": "1",
                    "value": "1",
                }
            ),
        }