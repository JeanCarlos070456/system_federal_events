from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import RetiradaDevolucao


class MovimentoForm(FederalModelForm):
    """
    Mantido para compatibilidade com a versão antiga.

    A nova tela principal trabalha em lote diretamente no index.html.
    """
    conferir_cabos = forms.BooleanField(required=False, label="Cabos conferidos")
    conferir_cases = forms.BooleanField(required=False, label="Cases conferidos")
    conferir_limpeza = forms.BooleanField(required=False, label="Limpeza conferida")

    class Meta:
        model = RetiradaDevolucao
        fields = [
            "tipo_movimento",
            "estado",
            "acessorios_conferidos",
            "dias_atraso",
            "multa_dia",
            "observacoes",
        ]
        widgets = {
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }