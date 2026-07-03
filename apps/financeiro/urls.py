from django.urls import path

from . import views

app_name = "financeiro"

urlpatterns = [
    path("", views.index, name="index"),
    path("novo/", views.create, name="create"),
]