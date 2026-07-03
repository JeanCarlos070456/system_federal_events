from django.urls import path

from . import views


app_name = "retirada_devolucao"


urlpatterns = [
    path("", views.index, name="index"),

    # Mantém compatibilidade com links antigos
    path("<uuid:vinculo_id>/movimentar/", views.movimentar, name="movimentar"),
]