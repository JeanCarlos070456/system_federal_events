from django.urls import path

from . import views


app_name = "estoque"


urlpatterns = [
    path("", views.index, name="index"),
    path("orcamento/<uuid:orcamento_id>/", views.detail, name="detail"),
    path("item/<uuid:item_id>/vincular/", views.vincular, name="vincular"),
    path("vinculo/<uuid:vinculo_id>/excluir/", views.excluir_vinculo, name="excluir_vinculo"),

    # API usada pelo leitor de QR Code / Código de Barras
    path("api/verificar-cod-produto/", views.verificar_cod_produto, name="verificar_cod_produto"),
]