from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.core.models import PaginaSistema, PerfilPermissao, UsuarioApp


@dataclass(slots=True)
class AppUserContext:
    id: str
    nome: str
    email: str
    perfil: str
    telefone: str | None = None
    cargo: str | None = None


class AuthenticationError(Exception):
    pass


class SupabaseAuthService:
    @staticmethod
    def _client():
        if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
            raise AuthenticationError("SUPABASE_URL ou SUPABASE_ANON_KEY não configurado no .env.")
        try:
            from supabase import create_client
        except Exception as exc:
            raise AuthenticationError("Pacote supabase não instalado. Rode: pip install -r requirements.txt") from exc
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

    @classmethod
    def sign_in(cls, email: str, password: str) -> dict[str, Any]:
        client = cls._client()
        try:
            response = client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as exc:
            raise AuthenticationError("E-mail ou senha inválidos, ou Supabase indisponível.") from exc

        user = getattr(response, "user", None)
        session = getattr(response, "session", None)
        if not user or not session:
            raise AuthenticationError("Supabase não retornou uma sessão válida.")

        user_id = getattr(user, "id", None) or user.get("id")
        access_token = getattr(session, "access_token", None) or session.get("access_token")
        refresh_token = getattr(session, "refresh_token", None) or session.get("refresh_token")

        app_user = UserAccessService.get_app_user(user_id=user_id, email=email)
        UserAccessService.touch_last_login(app_user.id)
        permissions = UserAccessService.get_permissions(app_user.perfil)
        navigation = UserAccessService.get_navigation(app_user.perfil)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "supabase_user_id": user_id,
            "app_user": asdict(app_user),
            "permissions": permissions,
            "navigation": navigation,
        }


class UserAccessService:
    @staticmethod
    def get_app_user(user_id: str | None, email: str | None = None) -> AppUserContext:
        qs = UsuarioApp.objects.all()
        usuario = None
        if user_id:
            usuario = qs.filter(id=user_id).first()
        if usuario is None and email:
            usuario = qs.filter(email__iexact=email).first()
        if usuario is None:
            raise AuthenticationError("Usuário autenticado no Supabase, mas não cadastrado em usuarios_app.")
        if not usuario.ativo:
            raise AuthenticationError("Usuário inativo no sistema Federal Eventos.")
        return AppUserContext(
            id=str(usuario.id),
            nome=usuario.nome,
            email=usuario.email,
            perfil=usuario.perfil,
            telefone=usuario.telefone,
            cargo=usuario.cargo,
        )

    @staticmethod
    def touch_last_login(user_id: str) -> None:
        UsuarioApp.objects.filter(id=user_id).update(ultimo_login=timezone.now())

    @staticmethod
    def get_permissions(perfil: str) -> dict[str, dict[str, bool]]:
        data: dict[str, dict[str, bool]] = {}
        qs = PerfilPermissao.objects.filter(perfil=perfil)
        for perm in qs:
            data[perm.pagina] = {
                "pode_acessar": bool(perm.pode_acessar),
                "pode_criar": bool(perm.pode_criar),
                "pode_editar": bool(perm.pode_editar),
                "pode_excluir": bool(perm.pode_excluir),
                "pode_exportar": bool(perm.pode_exportar),
            }
        return data

    @staticmethod
    def get_navigation(perfil: str) -> list[dict[str, str]]:
        permissions = PerfilPermissao.objects.filter(perfil=perfil, pode_acessar=True)
        allowed_pages = [p.pagina for p in permissions]
        pages = PaginaSistema.objects.filter(nome__in=allowed_pages, ativo=True).order_by("ordem")
        url_names = {
            "dashboard": "dashboard:index",
            "produtos": "produtos:index",
            "clientes": "clientes:index",
            "orcamento": "orcamentos:index",
            "estoque": "estoque:index",
            "agenda": "agenda:index",
            "retirada_devolucao": "retirada_devolucao:index",
            "financeiro": "financeiro:index",
            "relatorios": "relatorios:index",
        }
        icons = {
            "dashboard": "navegacao/painel_controle.png",
            "produtos": "navegacao/produtos.png",
            "clientes": "navegacao/cliente.png",
            "orcamento": "navegacao/locacoes.png",
            "estoque": "navegacao/reservas.png",
            "agenda": "navegacao/agenda.png",
            "retirada_devolucao": "navegacao/retirada_devolucao.png",
            "financeiro": "navegacao/financeiro.png",
            "relatorios": "navegacao/relatorios.png",
        }
        return [
            {
                "nome": page.nome,
                "slug": page.slug,
                "url_name": url_names.get(page.slug, "dashboard:index"),
                "icon": icons.get(page.slug, "logo_vazada.png"),
            }
            for page in pages
        ]
