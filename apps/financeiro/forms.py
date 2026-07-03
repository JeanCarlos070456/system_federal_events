from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from apps.core.forms import FederalModelForm
from apps.core.models import FinanceiroMovimento, Orcamento

from .services import FinanceiroService


class OrcamentoFinanceiroChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Orcamento) -> str:
        cliente = getattr(obj.cliente, "nome", None) or obj.cliente_nome or "Cliente não informado"
        valor = FinanceiroService.money(obj.valor_final)

        return f"{obj.codigo} - {obj.evento_nome} | {cliente} | {valor}"


class FinanceiroPagamentoForm(forms.Form):
    FORMA_PAGAMENTO_CHOICES = [
        ("", "Selecione"),
        ("PIX", "PIX"),
        ("Transferência", "Transferência"),
        ("Cartão de crédito", "Cartão de crédito"),
        ("Cartão de débito", "Cartão de débito"),
        ("Boleto", "Boleto"),
        ("Dinheiro", "Dinheiro"),
        ("Outro", "Outro"),
    ]

    orcamento = OrcamentoFinanceiroChoiceField(
        queryset=Orcamento.objects.none(),
        label="Orçamento / Evento",
        required=True,
    )

    valor = forms.CharField(
        label="Valor pago",
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex.: 1500,00",
                "autocomplete": "off",
            }
        ),
    )

    forma_pagamento = forms.ChoiceField(
        label="Forma de pagamento",
        choices=FORMA_PAGAMENTO_CHOICES,
        required=False,
    )

    data_pagamento = forms.DateField(
        label="Data do pagamento",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    descricao = forms.CharField(
        label="Descrição",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ex.: Pagamento parcial / Sinal / Quitação",
            }
        ),
    )

    comprovante_url = forms.URLField(
        label="URL do comprovante",
        required=False,
        widget=forms.URLInput(
            attrs={
                "placeholder": "https://...",
            }
        ),
    )

    observacoes = forms.CharField(
        label="Observações",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        orcamento_id = kwargs.pop("orcamento_id", None)

        super().__init__(*args, **kwargs)

        qs = (
            Orcamento.objects
            .select_related("cliente")
            .exclude(financeiro="Cancelado")
            .order_by("-created_at")
        )

        self.fields["orcamento"].queryset = qs

        if not self.is_bound:
            self.fields["data_pagamento"].initial = timezone.localdate()

            if orcamento_id:
                self.fields["orcamento"].initial = orcamento_id

                orcamento = qs.filter(pk=orcamento_id).first()

                if orcamento:
                    linha = FinanceiroService.montar_linha_orcamento(
                        orcamento,
                        sincronizar=False,
                    )

                    saldo = linha["saldo"]

                    if saldo > Decimal("0.00"):
                        self.fields["valor"].initial = f"{saldo:.2f}".replace(".", ",")

        self._apply_classes()

    def _apply_classes(self) -> None:
        for field in self.fields.values():
            widget = field.widget
            current_class = widget.attrs.get("class", "")

            if isinstance(widget, forms.CheckboxInput):
                css_class = "form-check-input"
            else:
                css_class = "form-control"

            widget.attrs["class"] = f"{current_class} {css_class}".strip()

    def clean_valor(self):
        raw = self.cleaned_data.get("valor")
        text = str(raw or "").strip().replace("R$", "").replace(" ", "")

        if not text:
            raise forms.ValidationError("Informe o valor pago.")

        if "," in text:
            text = text.replace(".", "").replace(",", ".")

        try:
            valor = Decimal(text)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Informe um valor válido. Exemplo: 1500,00.")

        if valor <= Decimal("0.00"):
            raise forms.ValidationError("O valor precisa ser maior que zero.")

        return valor

    def clean(self):
        cleaned = super().clean()

        orcamento = cleaned.get("orcamento")
        valor = cleaned.get("valor")

        if not orcamento or not valor:
            return cleaned

        linha = FinanceiroService.montar_linha_orcamento(
            orcamento,
            sincronizar=False,
        )

        saldo = linha["saldo"]

        if saldo > Decimal("0.00") and valor > saldo:
            raise forms.ValidationError(
                f"O valor informado é maior que o saldo em aberto. Saldo atual: {linha['saldo_fmt']}."
            )

        return cleaned


class FinanceiroMovimentoForm(FederalModelForm):
    class Meta:
        model = FinanceiroMovimento
        fields = [
            "orcamento",
            "cliente",
            "tipo",
            "categoria",
            "descricao",
            "valor",
            "forma_pagamento",
            "status",
            "data_vencimento",
            "data_pagamento",
            "comprovante_url",
            "observacoes",
        ]
        widgets = {
            "data_vencimento": forms.DateInput(attrs={"type": "date"}),
            "data_pagamento": forms.DateInput(attrs={"type": "date"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }