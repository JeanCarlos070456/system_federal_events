from django.urls import path

from . import views


app_name = "orcamentos"


urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
    path("produtos-autocomplete/", views.produtos_autocomplete, name="produtos_autocomplete"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/editar/", views.update, name="update"),
    path("<uuid:pk>/baixar-pdf/", views.baixar_orcamento_pdf, name="baixar_pdf"),
    path("<uuid:pk>/baixar-contrato/", views.baixar_contrato_pdf, name="baixar_contrato"),
    path("<uuid:pk>/ambientes/adicionar/", views.add_ambiente, name="add_ambiente"),
    path("<uuid:pk>/ambientes/<uuid:ambiente_id>/excluir/", views.delete_ambiente, name="delete_ambiente"),
    path("<uuid:pk>/ambientes/<uuid:ambiente_id>/itens/adicionar/", views.add_item, name="add_item"),
    path("<uuid:pk>/itens/<uuid:item_id>/excluir/", views.delete_item, name="delete_item"),
]