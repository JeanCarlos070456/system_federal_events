from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, PasswordResetRequestForm
from .services import AuthenticationError, SupabaseAuthService


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.session.get("app_user"):
        return redirect("dashboard:index")

    if request.GET.get("password_reset") == "success":
        messages.success(request, "Senha atualizada com sucesso. Entre novamente com sua nova senha.")

    form = LoginForm(request.POST or None)
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("dashboard:index")

    if request.method == "POST" and form.is_valid():
        try:
            payload = SupabaseAuthService.sign_in(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
        except AuthenticationError as exc:
            messages.error(request, str(exc))
        else:
            request.session.flush()
            request.session["sb_access_token"] = payload["access_token"]
            request.session["sb_refresh_token"] = payload["refresh_token"]
            request.session["supabase_user_id"] = payload["supabase_user_id"]
            request.session["app_user"] = payload["app_user"]
            request.session["permissions"] = payload["permissions"]
            request.session["navigation"] = payload["navigation"]
            request.session.set_expiry(60 * 60 * 8)
            messages.success(request, "Login realizado com sucesso.")
            return redirect(next_url)

    return render(request, "accounts/login.html", {"form": form, "next": next_url})


@require_http_methods(["GET", "POST"])
def password_reset_request_view(request):
    if request.session.get("app_user"):
        return redirect("dashboard:index")

    form = PasswordResetRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        redirect_to = request.build_absolute_uri(reverse("accounts:redefinir_senha"))

        try:
            SupabaseAuthService.request_password_reset(
                email=email,
                redirect_to=redirect_to,
            )
        except AuthenticationError:
            messages.error(
                request,
                "Não foi possível enviar a recuperação agora. Tente novamente em alguns minutos.",
            )
        else:
            messages.success(
                request,
                "Se este e-mail estiver cadastrado, enviaremos as instruções de recuperação.",
            )
            return redirect("accounts:esqueci_senha")

    return render(request, "accounts/esqueci_senha.html", {"form": form})


@require_http_methods(["GET"])
def password_reset_confirm_view(request):
    """
    Página pública que recebe o link do Supabase e permite definir nova senha.
    A atualização da senha é feita pelo Supabase Auth no navegador com supabase-js.
    """
    if request.session.get("app_user"):
        request.session.flush()

    return render(
        request,
        "accounts/redefinir_senha.html",
        {
            "supabase_url": settings.SUPABASE_URL,
            "supabase_anon_key": settings.SUPABASE_ANON_KEY,
            "login_url": reverse("accounts:login"),
        },
    )


def logout_view(request):
    request.session.flush()
    messages.success(request, "Sessão encerrada.")
    return redirect("accounts:login")