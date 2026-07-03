from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse


def app_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("app_user"):
            return redirect(f"{reverse('accounts:login')}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(page_name: str, action: str = "pode_acessar"):
    def decorator(view_func):
        @wraps(view_func)
        @app_login_required
        def wrapper(request, *args, **kwargs):
            permissions = request.session.get("permissions", {})
            page_perm = permissions.get(page_name, {})
            if not page_perm.get(action, False):
                if action == "pode_acessar":
                    return render(request, "accounts/403.html", {"page_name": page_name}, status=403)
                messages.error(request, "Seu perfil não tem permissão para executar esta ação.")
                return redirect(request.META.get("HTTP_REFERER") or "dashboard:index")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def can(request, page_name: str, action: str) -> bool:
    return bool(request.session.get("permissions", {}).get(page_name, {}).get(action, False))
