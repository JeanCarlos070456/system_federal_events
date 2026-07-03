from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import EstoqueVinculo, ProdutoPatrimonio


class EstoqueVinculoForm(FederalModelForm):
    patrimonio = forms.ModelChoiceField(queryset=ProdutoPatrimonio.objects.filter(status="Disponível").order_by("cod_patrimonio"), required=False)

    class Meta:
        model = EstoqueVinculo
        fields = ["patrimonio", "cod_patrimonio", "descricao", "quantidade", "status", "observacoes"]
        widgets = {"observacoes": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        cleaned = super().clean()
        patrimonio = cleaned.get("patrimonio")
        cod = cleaned.get("cod_patrimonio")
        if patrimonio and not cod:
            cleaned["cod_patrimonio"] = patrimonio.cod_patrimonio
        if not cleaned.get("cod_patrimonio"):
            raise forms.ValidationError("Informe um COD ou selecione um patrimônio.")
        return cleaned
