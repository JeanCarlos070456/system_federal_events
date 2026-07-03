from __future__ import annotations

from apps.core.models import LogSistema, UsuarioApp
from apps.core.utils import get_client_ip


def log_action(request, modulo: str, acao: str, entidade: str | None = None, entidade_id=None, mensagem: str | None = None, dados: dict | None = None, nivel="INFO") -> None:
    try:
        usuario = None
        if getattr(request, "app_user", None):
            usuario = UsuarioApp.objects.filter(id=request.app_user.id).first()
        LogSistema.objects.create(
            usuario=usuario,
            nivel=nivel,
            modulo=modulo,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            mensagem=mensagem,
            dados=dados or {},
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
    except Exception:
        # Log nunca pode derrubar fluxo operacional.
        pass
