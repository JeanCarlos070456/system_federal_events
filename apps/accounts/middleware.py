from __future__ import annotations

from types import SimpleNamespace

from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse


class SupabaseSessionMiddleware:
    """
    Injeta o usuário operacional do Supabase/Django em request.app_user
    e redireciona o colaborador para Produtos quando ele tentar cair no Dashboard.
    """

    ROTAS_LIVRES_PREFIXOS = (
        "/static/",
        "/media/",
        "/admin/",
        "/accounts/",
        "/login/",
        "/logout/",
    )

    DASHBOARD_PATHS = (
        "/",
        "/dashboard/",
        "/dashboard",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        data = request.session.get("app_user")

        request.app_user = SimpleNamespace(**data) if data else None
        request.app_permissions = request.session.get("permissions", {})
        request.app_navigation = request.session.get("navigation", [])

        redirect_response = self._redirect_colaborador_dashboard(request)

        if redirect_response:
            return redirect_response

        return self.get_response(request)

    @classmethod
    def _normalizar_perfil(cls, request) -> str:
        app_user = getattr(request, "app_user", None)

        if not app_user:
            return ""

        perfil = getattr(app_user, "perfil", "") or ""
        return str(perfil).strip().lower()

    @classmethod
    def _is_rota_livre(cls, path: str) -> bool:
        return any(path.startswith(prefixo) for prefixo in cls.ROTAS_LIVRES_PREFIXOS)

    @classmethod
    def _is_dashboard_path(cls, path: str) -> bool:
        if path in cls.DASHBOARD_PATHS:
            return True

        return path.startswith("/dashboard/")

    @classmethod
    def _produtos_url(cls) -> str:
        try:
            return reverse("produtos:index")
        except NoReverseMatch:
            return "/produtos/"

    def _redirect_colaborador_dashboard(self, request):
        path = request.path or "/"

        if self._is_rota_livre(path):
            return None

        perfil = self._normalizar_perfil(request)

        if perfil != "colaborador":
            return None

        if self._is_dashboard_path(path):
            return redirect(self._produtos_url())

        return None
