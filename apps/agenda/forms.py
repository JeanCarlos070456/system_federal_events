from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import AgendaEvento


class AgendaEventoForm(FederalModelForm):
    class Meta:
        model = AgendaEvento
        fields = ["orcamento", "titulo", "tipo_evento", "data_inicio", "data_fim", "horario_inicio", "horario_fim", "local_evento", "status", "observacoes"]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
            "horario_inicio": forms.TimeInput(attrs={"type": "time"}),
            "horario_fim": forms.TimeInput(attrs={"type": "time"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }
