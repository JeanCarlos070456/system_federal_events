from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import Produto, ProdutoPatrimonio


class ProdutoForm(FederalModelForm):
    class Meta:
        model = Produto
        fields = [
            "codigo",
            "nome",
            "categoria",
            "subcategoria",
            "marca",
            "modelo",
            "descricao",
            "especificacoes",
            "valor_diaria",
            "valor_semanal",
            "valor_mensal",
            "status",
            "localizacao",
            "observacoes",
        ]
        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "id": "id_codigo",
                    "placeholder": "Digite, escaneie QR Code ou código de barras",
                    "autocomplete": "off",
                }
            ),
            "nome": forms.TextInput(attrs={"placeholder": "Nome do produto"}),
            "categoria": forms.TextInput(attrs={"placeholder": "Categoria"}),
            "subcategoria": forms.TextInput(attrs={"placeholder": "Subcategoria"}),
            "marca": forms.TextInput(attrs={"placeholder": "Marca"}),
            "modelo": forms.TextInput(attrs={"placeholder": "Modelo"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "especificacoes": forms.Textarea(attrs={"rows": 3}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }


class ProdutoPatrimonioForm(FederalModelForm):
    class Meta:
        model = ProdutoPatrimonio
        fields = [
            "cod_patrimonio",
            "numero_serie",
            "status",
            "localizacao",
            "observacoes",
        ]
        widgets = {
            "cod_patrimonio": forms.TextInput(
                attrs={
                    "id": "id_cod_patrimonio",
                    "placeholder": "Digite ou escaneie o COD/patrimônio",
                    "autocomplete": "off",
                }
            ),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }