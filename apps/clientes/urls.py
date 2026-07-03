from django.urls import path

from . import views


app_name = "clientes"


urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
    path("buscar-cnpj/", views.buscar_cnpj, name="buscar_cnpj"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/editar/", views.update, name="update"),
    path("<uuid:pk>/excluir/", views.delete, name="delete"),
]