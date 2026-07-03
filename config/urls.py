from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path


def health_check(request):
    """
    Rota leve para monitoramento externo.
    Usada pelo GitHub Actions/Render para manter o app ativo na fase de testes.
    """
    return JsonResponse({"status": "ok"})


def root_redirect(request):
    app_user = request.session.get("app_user")

    if not app_user:
        return redirect("accounts:login")

    perfil = str(app_user.get("perfil", "")).strip().lower()

    if perfil == "colaborador":
        return redirect("produtos:index")

    return redirect("dashboard:index")


urlpatterns = [
    path("health/", health_check, name="health_check"),

    path("", root_redirect, name="root"),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("produtos/", include("apps.produtos.urls")),
    path("orcamentos/", include("apps.orcamentos.urls")),
    path("estoque/", include("apps.estoque.urls")),
    path("agenda/", include("apps.agenda.urls")),
    path("financeiro/", include("apps.financeiro.urls")),
    path("retirada-devolucao/", include("apps.retirada_devolucao.urls")),
    path("relatorios/", include("apps.relatorios.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)