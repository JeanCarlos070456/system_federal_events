from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path


def root_redirect(request):
    if request.session.get("app_user"):
        return redirect("dashboard:index")
    return redirect("accounts:login")

urlpatterns = [
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
