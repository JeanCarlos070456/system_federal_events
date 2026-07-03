from django.urls import path

from . import views


app_name = "agenda"


urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
    path("eventos.json", views.eventos_json, name="eventos_json"),
    path(
        "orcamento/<uuid:orcamento_id>/relacao-evento/",
        views.baixar_relacao_evento,
        name="baixar_relacao_evento",
    ),
]