from __future__ import annotations

from django import forms

from apps.core.forms import FederalModelForm
from apps.core.models import Cliente


class ClienteForm(FederalModelForm):
    class Meta:
        model = Cliente
        fields = [
            "nome",
            "tipo_pessoa",
            "documento",
            "inscricao_estadual",
            "responsavel_nome",
            "responsavel_cargo",
            "telefone",
            "whatsapp",
            "email",
            "cep",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "status",
            "origem",
            "observacoes",
        ]
        widgets = {
            "nome": forms.TextInput(
                attrs={
                    "placeholder": "Nome completo ou razão social",
                    "autocomplete": "off",
                }
            ),
            "documento": forms.TextInput(
                attrs={
                    "placeholder": "CPF ou CNPJ",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "inscricao_estadual": forms.TextInput(
                attrs={
                    "placeholder": "Inscrição estadual, se houver",
                    "autocomplete": "off",
                }
            ),
            "responsavel_nome": forms.TextInput(
                attrs={
                    "placeholder": "Nome do responsável",
                    "autocomplete": "off",
                }
            ),
            "responsavel_cargo": forms.TextInput(
                attrs={
                    "placeholder": "Cargo do responsável",
                    "autocomplete": "off",
                }
            ),
            "telefone": forms.TextInput(
                attrs={
                    "placeholder": "(00) 0000-0000",
                    "autocomplete": "off",
                    "inputmode": "tel",
                }
            ),
            "whatsapp": forms.TextInput(
                attrs={
                    "placeholder": "(00) 00000-0000",
                    "autocomplete": "off",
                    "inputmode": "tel",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "email@empresa.com.br",
                    "autocomplete": "off",
                }
            ),
            "cep": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "endereco": forms.TextInput(
                attrs={
                    "placeholder": "Logradouro",
                    "autocomplete": "off",
                }
            ),
            "numero": forms.TextInput(
                attrs={
                    "placeholder": "Número",
                    "autocomplete": "off",
                }
            ),
            "complemento": forms.TextInput(
                attrs={
                    "placeholder": "Complemento",
                    "autocomplete": "off",
                }
            ),
            "bairro": forms.TextInput(
                attrs={
                    "placeholder": "Bairro",
                    "autocomplete": "off",
                }
            ),
            "cidade": forms.TextInput(
                attrs={
                    "placeholder": "Cidade",
                    "autocomplete": "off",
                }
            ),
            "uf": forms.TextInput(
                attrs={
                    "placeholder": "UF",
                    "maxlength": "2",
                    "autocomplete": "off",
                }
            ),
            "origem": forms.TextInput(
                attrs={
                    "placeholder": "Ex.: Indicação, Site, BrasilAPI, Cliente antigo",
                    "autocomplete": "off",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Observações internas sobre o cliente",
                }
            ),
        }