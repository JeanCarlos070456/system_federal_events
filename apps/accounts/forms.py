from __future__ import annotations

from django import forms


class LoginForm(forms.Form):
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"placeholder": "seu@email.com", "autocomplete": "email"}))
    password = forms.CharField(label="Senha", widget=forms.PasswordInput(attrs={"placeholder": "Sua senha", "autocomplete": "current-password"}))
