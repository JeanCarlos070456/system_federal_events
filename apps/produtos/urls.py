from django.urls import path
from . import views

app_name = "produtos"
urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/editar/", views.update, name="update"),
    path("<uuid:produto_id>/patrimonios/novo/", views.patrimonio_create, name="patrimonio_create"),
]
