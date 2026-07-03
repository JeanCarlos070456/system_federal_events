from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import LoginForm
from .services import AuthenticationError, SupabaseAuthService


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.session.get("app_user"):
        return redirect("dashboard:index")

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


def logout_view(request):
    request.session.flush()
    messages.success(request, "Sessão encerrada.")
    return redirect("accounts:login")
