from __future__ import annotations

from django import forms


class FederalModelForm(forms.ModelForm):
    """
    Form base do sistema Federal Eventos.

    Responsabilidades:
    - Aplicar classe visual padrão nos campos Django.
    - Aceitar argumentos extras usados pelas views sem quebrar o ModelForm.
    - Guardar permissões/contexto para forms filhos.
    """

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        self.app_user = kwargs.pop("app_user", None)

        # Usado especialmente em Produtos:
        # admin_empresa pode ver/editar valores;
        # colaborador não deve gerenciar valores.
        self.can_manage_values = kwargs.pop("can_manage_values", True)

        # Reserva para telas que controlam mídia/imagem/vídeo/documento.
        self.can_manage_media = kwargs.pop("can_manage_media", True)

        # Reserva genérica para permissões futuras.
        self.permissions = kwargs.pop("permissions", None)

        super().__init__(*args, **kwargs)

        self._apply_federal_classes()

    def _apply_federal_classes(self) -> None:
        """
        Aplica classes CSS padrão nos campos sem apagar classes existentes.
        """
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")

            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = self._join_classes(
                    css,
                    "form-check-input",
                )

            elif isinstance(field.widget, forms.RadioSelect):
                field.widget.attrs["class"] = self._join_classes(
                    css,
                    "form-check-input",
                )

            elif isinstance(field.widget, forms.ClearableFileInput):
                field.widget.attrs["class"] = self._join_classes(
                    css,
                    "form-control",
                )

            else:
                field.widget.attrs["class"] = self._join_classes(
                    css,
                    "form-control",
                )

    @staticmethod
    def _join_classes(*classes: str) -> str:
        """
        Junta classes CSS evitando duplicidade.
        """
        result = []

        for value in classes:
            for css_class in str(value or "").split():
                if css_class and css_class not in result:
                    result.append(css_class)

        return " ".join(result)