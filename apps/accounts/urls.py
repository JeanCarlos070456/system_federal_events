from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("esqueci-senha/", views.password_reset_request_view, name="esqueci_senha"),
    path("redefinir-senha/", views.password_reset_confirm_view, name="redefinir_senha"),
]