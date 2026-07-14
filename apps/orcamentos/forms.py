from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import Cliente, Orcamento, OrcamentoAmbiente, OrcamentoItem


AMBIENTE_TIPO_SUGESTOES = [
    "Sala",
    "Auditório",
    "Credenciamento",
    "Outro",
    "Garagem",
    "Camarim",
    "Palco",
    "Área externa",
    "Recepção",
    "Depósito",
    "Sala VIP",
    "Foyer",
    "Hall",
]


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
    """
    Ambiente do orçamento.

    Regra:
    - O usuário pode escolher uma sugestão pronta.
    - O usuário também pode digitar livremente um novo tipo, como Garagem,
      Camarim, Palco, Área externa etc.
    """

    tipo = forms.CharField(
        label="Tipo",
        required=True,
        max_length=40,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex: Sala, Auditório, Garagem...",
                "list": "tipo-ambiente-sugestoes",
                "autocomplete": "off",
            }
        ),
    )

    nome = forms.CharField(
        label="Nome do ambiente",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex: Auditório Vermelho, Sala VIP, Garagem principal...",
                "autocomplete": "off",
            }
        ),
    )

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

    def clean_tipo(self):
        tipo = (self.cleaned_data.get("tipo") or "").strip()

        if not tipo:
            raise forms.ValidationError("Informe o tipo do ambiente.")

        legacy_labels = {
            "sala": "Sala",
            "auditorio": "Auditório",
            "auditório": "Auditório",
            "credenciamento": "Credenciamento",
            "outro": "Outro",
        }

        normalized_key = tipo.lower()

        return legacy_labels.get(normalized_key, tipo[:40])

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        return nome[:255]


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