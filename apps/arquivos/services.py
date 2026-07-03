from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils.text import slugify
from supabase import create_client

from apps.core.models import Arquivo, UsuarioApp


IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTS = {"mp4", "mov", "webm", "avi", "mkv"}
DOC_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "txt"}


class ArquivoService:
    """
    Serviço centralizado para upload no Supabase Storage + registro na tabela arquivos.

    Uso em Produtos:
    - entidade = "produto"
    - entidade_id = produto.id
    - tipo_arquivo = "imagem"
    """

    @staticmethod
    def _get_supabase_client():
        supabase_url = getattr(settings, "SUPABASE_URL", None) or os.getenv("SUPABASE_URL")

        supabase_key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)
            or getattr(settings, "SUPABASE_ANON_KEY", None)
            or os.getenv("SUPABASE_ANON_KEY")
        )

        if not supabase_url or not supabase_key:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY precisam estar configurados."
            )

        return create_client(supabase_url, supabase_key)

    @staticmethod
    def _bucket_name() -> str:
        bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", None) or os.getenv("SUPABASE_STORAGE_BUCKET")

        if not bucket:
            bucket = "produtos"

        return bucket

    @staticmethod
    def _resolver_usuario(usuario: Any) -> UsuarioApp | None:
        """
        O middleware pode entregar request.app_user como:
        - instância de UsuarioApp;
        - dict com id/nome/email/perfil;
        - None.

        O campo Arquivo.enviado_por exige uma instância UsuarioApp.
        """
        if not usuario:
            return None

        if isinstance(usuario, UsuarioApp):
            return usuario

        usuario_id = None

        if isinstance(usuario, dict):
            usuario_id = usuario.get("id") or usuario.get("pk") or usuario.get("usuario_id")
        else:
            usuario_id = getattr(usuario, "id", None) or getattr(usuario, "pk", None)

        if not usuario_id:
            return None

        try:
            return UsuarioApp.objects.filter(id=usuario_id).first()
        except Exception:
            return None

    @staticmethod
    def _normalizar_extensao(file_obj, fallback: str = "bin") -> str:
        nome = getattr(file_obj, "name", "") or ""
        ext = Path(nome).suffix.lower().replace(".", "")

        if ext:
            return ext

        mime_type = getattr(file_obj, "content_type", "") or ""

        if mime_type == "image/jpeg":
            return "jpg"

        if mime_type == "image/png":
            return "png"

        if mime_type == "image/webp":
            return "webp"

        if mime_type == "video/mp4":
            return "mp4"

        return fallback

    @staticmethod
    def _nome_seguro(nome: str) -> str:
        nome_base = Path(nome or "arquivo").stem
        nome_base = slugify(nome_base) or "arquivo"
        nome_base = re.sub(r"[^a-zA-Z0-9_-]", "-", nome_base)
        return nome_base[:80]

    @staticmethod
    def _tipo_por_arquivo(file_obj, tipo: str | None = None) -> str:
        if tipo:
            return tipo

        ext = ArquivoService._normalizar_extensao(file_obj)
        mime_type = (getattr(file_obj, "content_type", "") or "").lower()

        if ext in IMAGE_EXTS or mime_type.startswith("image/"):
            return "imagem"

        if ext in VIDEO_EXTS or mime_type.startswith("video/"):
            return "video"

        if ext in DOC_EXTS:
            return "documento"

        return "outro"

    @staticmethod
    def _validar_upload(file_obj, tipo: str) -> None:
        tamanho = getattr(file_obj, "size", None)
        ext = ArquivoService._normalizar_extensao(file_obj)
        mime_type = (getattr(file_obj, "content_type", "") or "").lower()

        limite = 10 * 1024 * 1024 if tipo == "imagem" else 80 * 1024 * 1024

        if tamanho and tamanho > limite:
            raise ValueError("Arquivo muito grande para upload.")

        if tipo == "imagem":
            if ext not in IMAGE_EXTS and not mime_type.startswith("image/"):
                raise ValueError("O arquivo enviado não parece ser uma imagem válida.")

    @staticmethod
    def upload_e_registrar(
        *,
        entidade: str,
        entidade_id,
        file_obj,
        usuario: Any = None,
        tipo: str | None = None,
        codigo_referencia: str | None = None,
    ) -> Arquivo:
        tipo_arquivo = ArquivoService._tipo_por_arquivo(file_obj, tipo)
        ArquivoService._validar_upload(file_obj, tipo_arquivo)

        bucket = ArquivoService._bucket_name()
        client = ArquivoService._get_supabase_client()

        ext = ArquivoService._normalizar_extensao(file_obj)
        nome_original = getattr(file_obj, "name", "arquivo") or "arquivo"
        nome_seguro = ArquivoService._nome_seguro(nome_original)

        codigo_seguro = slugify(str(codigo_referencia or entidade_id)) or str(entidade_id)
        nome_armazenado = f"{codigo_seguro}_{nome_seguro}_{uuid.uuid4().hex[:10]}.{ext}"

        storage_path = f"{entidade}/{entidade_id}/{tipo_arquivo}/{nome_armazenado}"

        file_obj.seek(0)
        file_bytes = file_obj.read()

        mime_type = getattr(file_obj, "content_type", None) or "application/octet-stream"

        client.storage.from_(bucket).upload(
            storage_path,
            file_bytes,
            file_options={
                "content-type": mime_type,
                "upsert": "false",
            },
        )

        public_url = client.storage.from_(bucket).get_public_url(storage_path)
        usuario_instance = ArquivoService._resolver_usuario(usuario)

        return Arquivo.objects.create(
            entidade=entidade,
            entidade_id=entidade_id,
            tipo_arquivo=tipo_arquivo,
            nome_original=nome_original,
            nome_armazenado=nome_armazenado,
            extensao=ext,
            mime_type=mime_type,
            tamanho_bytes=getattr(file_obj, "size", None),
            storage_provider="supabase",
            bucket=bucket,
            path=storage_path,
            public_url=public_url,
            enviado_por=usuario_instance,
        )

    @staticmethod
    def registrar_metadado(
        entidade: str,
        entidade_id,
        file_obj,
        usuario: Any = None,
        tipo="documento",
    ) -> Arquivo:
        usuario_instance = ArquivoService._resolver_usuario(usuario)

        return Arquivo.objects.create(
            entidade=entidade,
            entidade_id=entidade_id,
            tipo_arquivo=tipo,
            nome_original=getattr(file_obj, "name", "arquivo"),
            extensao=Path(getattr(file_obj, "name", "")).suffix.lower().replace(".", ""),
            mime_type=getattr(file_obj, "content_type", None),
            tamanho_bytes=getattr(file_obj, "size", None),
            storage_provider="supabase",
            bucket=ArquivoService._bucket_name(),
            enviado_por=usuario_instance,
        )