from __future__ import annotations

import base64
from decimal import Decimal
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.arquivos.services import ArquivoService
from apps.core.models import (
    EstoqueVinculo,
    Orcamento,
    Produto,
    RetiradaDevolucao,
    UsuarioApp,
)


class MovimentoOperacionalService:
    STATUS_CANCELADOS = {
        "Cancelado",
        "Cancelada",
        "Removido",
        "Removida",
        "Excluído",
        "Excluída",
    }

    STATUS_RETIRADA_ELEGIVEIS = {"Vinculado", "Separado"}
    STATUS_DEVOLUCAO_ELEGIVEIS = {"Retirado"}

    @staticmethod
    def normalizar(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def normalizar_lower(value: Any) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _status_elegiveis(cls, modo: str) -> set[str]:
        modo = cls.normalizar_lower(modo)

        if modo == "devolucao":
            return cls.STATUS_DEVOLUCAO_ELEGIVEIS

        return cls.STATUS_RETIRADA_ELEGIVEIS

    @classmethod
    def eventos_queryset(cls, modo: str):
        status_elegiveis = cls._status_elegiveis(modo)

        return (
            Orcamento.objects
            .filter(estoque_vinculos__status__in=status_elegiveis)
            .select_related("cliente")
            .prefetch_related(
                "ambientes",
                "itens",
                "estoque_vinculos__item",
                "estoque_vinculos__ambiente",
                "estoque_vinculos__produto",
                "estoque_vinculos__patrimonio",
            )
            .distinct()
            .order_by("data_inicio", "evento_nome", "codigo")
        )

    @classmethod
    def buscar_orcamento(cls, modo: str, orcamento_id: str | None = None) -> Orcamento | None:
        qs = cls.eventos_queryset(modo)

        if orcamento_id:
            obj = qs.filter(id=orcamento_id).first()

            if obj:
                return obj

            return (
                Orcamento.objects
                .select_related("cliente")
                .prefetch_related(
                    "ambientes",
                    "itens",
                    "estoque_vinculos__item",
                    "estoque_vinculos__ambiente",
                    "estoque_vinculos__produto",
                    "estoque_vinculos__patrimonio",
                )
                .filter(id=orcamento_id)
                .first()
            )

        return qs.first()

    @classmethod
    def _periodo(cls, orcamento: Orcamento) -> str:
        inicio = getattr(orcamento, "data_inicio", None)
        fim = getattr(orcamento, "data_fim", None)

        if inicio and fim:
            return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"

        if inicio:
            return inicio.strftime("%d/%m/%Y")

        return "Não informado"

    @classmethod
    def _data(cls, value) -> str:
        if not value:
            return "Não informado"

        try:
            return value.strftime("%d/%m/%Y")
        except AttributeError:
            return str(value)

    @classmethod
    def ultimo_responsavel_retirada(cls, orcamento: Orcamento) -> str:
        movimento = (
            RetiradaDevolucao.objects
            .filter(orcamento=orcamento, tipo_movimento="Retirada")
            .select_related("responsavel")
            .order_by("-created_at")
            .first()
        )

        if not movimento:
            return "Não informado"

        checklist = movimento.checklist or {}

        if isinstance(checklist, dict):
            nome_informado = checklist.get("responsavel_nome")

            if nome_informado:
                return str(nome_informado)

        if movimento.responsavel:
            return movimento.responsavel.nome

        return "Não informado"

    @classmethod
    def montar_card_evento(cls, orcamento: Orcamento | None, modo: str) -> dict:
        if not orcamento:
            return {}

        card = {
            "cliente": getattr(orcamento.cliente, "nome", None) or orcamento.cliente_nome or "Cliente não informado",
            "evento": orcamento.evento_nome,
            "periodo": cls._periodo(orcamento),
            "local": orcamento.local_evento or "Local não informado",
            "montagem": cls._data(orcamento.data_montagem),
        }

        if cls.normalizar_lower(modo) == "devolucao":
            card["quem_retirou"] = cls.ultimo_responsavel_retirada(orcamento)

        return card

    @classmethod
    def _vinculos_operacionais(cls, orcamento: Orcamento, modo: str):
        status_elegiveis = cls._status_elegiveis(modo)

        return (
            orcamento.estoque_vinculos
            .select_related("item", "ambiente", "produto", "patrimonio")
            .filter(status__in=status_elegiveis)
            .exclude(status__in=cls.STATUS_CANCELADOS)
            .order_by(
                "ambiente__ordem",
                "ambiente__created_at",
                "item__ordem",
                "item__created_at",
            )
        )

    @classmethod
    def montar_grupos_por_sala(cls, orcamento: Orcamento | None, modo: str) -> list[dict]:
        if not orcamento:
            return []

        grupos_map = {}

        for vinculo in cls._vinculos_operacionais(orcamento, modo):
            ambiente = vinculo.ambiente
            ambiente_id = str(ambiente.id) if ambiente else "sem_ambiente"

            if ambiente_id not in grupos_map:
                grupos_map[ambiente_id] = {
                    "ambiente": ambiente,
                    "nome": ambiente.nome if ambiente else "Sem ambiente definido",
                    "tipo": ambiente.get_tipo_display() if ambiente else "Geral",
                    "vinculos": [],
                }

            grupos_map[ambiente_id]["vinculos"].append(vinculo)

        return list(grupos_map.values())

    @classmethod
    def _produto_por_codigo(cls, codigo: str) -> Produto | None:
        codigo = cls.normalizar(codigo)

        if not codigo:
            return None

        return Produto.objects.filter(codigo__iexact=codigo).first()

    @classmethod
    def _produto_do_vinculo(cls, vinculo: EstoqueVinculo) -> Produto | None:
        produto = cls._produto_por_codigo(vinculo.cod_patrimonio)

        if produto:
            return produto

        return vinculo.produto

    @classmethod
    def _atualizar_produto_status(cls, vinculo: EstoqueVinculo, status: str) -> None:
        produto = cls._produto_do_vinculo(vinculo)

        if produto:
            produto.status = status

            if status == "Disponível":
                produto.quantidade_total = 1
                produto.quantidade_disponivel = 1
            else:
                produto.quantidade_total = 1
                produto.quantidade_disponivel = 0

            produto.save(
                update_fields=[
                    "status",
                    "quantidade_total",
                    "quantidade_disponivel",
                    "updated_at",
                ]
            )

        if vinculo.patrimonio:
            if status == "Manutenção":
                vinculo.patrimonio.status = "Manutenção"
            elif status == "Disponível":
                vinculo.patrimonio.status = "Disponível"
            elif status == "Locado":
                vinculo.patrimonio.status = "Locado"

            vinculo.patrimonio.save(update_fields=["status", "updated_at"])

    @staticmethod
    def _foto_camera_para_file(data_url: str | None, codigo: str | None = None):
        if not data_url:
            return None

        if not str(data_url).startswith("data:image/"):
            return None

        try:
            header, encoded = data_url.split(",", 1)
            mime_part = header.split(";")[0]
            mime_type = mime_part.replace("data:", "").strip() or "image/png"
            ext = mime_type.split("/")[-1].replace("jpeg", "jpg")

            raw = base64.b64decode(encoded)

            nome = f"defeito_{codigo or 'sem_codigo'}.{ext}"
            file_obj = ContentFile(raw, name=nome)
            file_obj.content_type = mime_type
            file_obj.size = len(raw)

            return file_obj

        except Exception:
            return None

    @classmethod
    def _obter_foto_defeito(cls, *, vinculo_id, codigo: str, files, post):
        foto = files.get(f"foto_defeito_{vinculo_id}")

        if foto:
            return foto

        return cls._foto_camera_para_file(
            post.get(f"foto_camera_{vinculo_id}"),
            codigo=codigo,
        )

    @classmethod
    def _criar_movimento(
        cls,
        *,
        vinculo: EstoqueVinculo,
        tipo: str,
        usuario: UsuarioApp | None,
        estado: str,
        checklist: dict,
        observacoes: str | None,
    ) -> RetiradaDevolucao:
        return RetiradaDevolucao.objects.create(
            orcamento=vinculo.orcamento,
            estoque_vinculo=vinculo,
            item=vinculo.item,
            produto=cls._produto_do_vinculo(vinculo),
            cod_patrimonio=vinculo.cod_patrimonio,
            tipo_movimento=tipo,
            data_movimento=timezone.now(),
            estado=estado,
            acessorios_conferidos=True,
            checklist=checklist,
            dias_atraso=0,
            multa_dia=Decimal("0.00"),
            valor_multa=Decimal("0.00"),
            responsavel=usuario,
            observacoes=observacoes,
        )

    @classmethod
    def _salvar_foto_defeito(
        cls,
        *,
        movimento: RetiradaDevolucao,
        vinculo: EstoqueVinculo,
        foto,
        usuario: Any,
    ) -> None:
        try:
            ArquivoService.upload_e_registrar(
                entidade="retirada_devolucao",
                entidade_id=movimento.id,
                file_obj=foto,
                usuario=usuario,
                tipo="imagem",
                codigo_referencia=vinculo.cod_patrimonio,
            )

        except Exception as exc:
            raise ValueError(f"Não foi possível salvar a foto do defeito no bucket: {exc}") from exc

    @classmethod
    def _validar_conferencia(cls, *, vinculo: EstoqueVinculo, post) -> None:
        campo = f"conferido_{vinculo.id}"
        codigo_lido = cls.normalizar(post.get(campo))
        codigo_esperado = cls.normalizar(vinculo.cod_patrimonio)

        if not codigo_lido:
            raise ValueError(f"O COD {codigo_esperado} ainda não foi conferido por QR Code ou Código de Barras.")

        if codigo_lido != codigo_esperado:
            raise ValueError(
                f"O COD conferido ({codigo_lido}) não bate com o COD vinculado ({codigo_esperado})."
            )

    @classmethod
    def _validar_checklist(cls, *, vinculo: EstoqueVinculo, post) -> str:
        campo = f"checklist_{vinculo.id}"
        valor = cls.normalizar_lower(post.get(campo))

        if valor not in {"avaliado", "defeito"}:
            raise ValueError(f"Selecione o checklist do COD {vinculo.cod_patrimonio}.")

        return valor

    @classmethod
    @transaction.atomic
    def registrar_lote(
        cls,
        *,
        modo: str,
        orcamento: Orcamento,
        responsavel_nome: str,
        usuario: UsuarioApp | None,
        request_user: Any,
        post,
        files,
    ) -> int:
        modo_normalizado = cls.normalizar_lower(modo)

        if modo_normalizado not in {"retirada", "devolucao"}:
            raise ValueError("Tipo de operação inválido.")

        responsavel_nome = cls.normalizar(responsavel_nome)

        if not responsavel_nome:
            if modo_normalizado == "retirada":
                raise ValueError("Informe o nome de quem retirou o produto.")

            raise ValueError("Informe o nome de quem devolveu o produto.")

        tipo_movimento = "Retirada" if modo_normalizado == "retirada" else "Devolução"

        vinculos = list(cls._vinculos_operacionais(orcamento, modo_normalizado))

        if not vinculos:
            raise ValueError("Não há equipamentos elegíveis para esta operação.")

        total = 0

        for vinculo in vinculos:
            checklist_status = cls._validar_checklist(vinculo=vinculo, post=post)

            if checklist_status != "defeito":
                cls._validar_conferencia(vinculo=vinculo, post=post)

            observacoes = cls.normalizar(post.get(f"defeito_obs_{vinculo.id}"))

            codigo_conferido = (
                cls.normalizar(post.get(f"conferido_{vinculo.id}"))
                or cls.normalizar(vinculo.cod_patrimonio)
            )

            checklist = {
                "responsavel_nome": responsavel_nome,
                "checklist": checklist_status,
                "conferido": True,
                "codigo_conferido": codigo_conferido,
                "ambiente": vinculo.ambiente.nome if vinculo.ambiente else None,
                "item": vinculo.item.equipamento if vinculo.item else None,
            }

            if checklist_status == "defeito":
                if not observacoes:
                    raise ValueError(f"Descreva o defeito do COD {vinculo.cod_patrimonio}.")

                foto = cls._obter_foto_defeito(
                    vinculo_id=vinculo.id,
                    codigo=vinculo.cod_patrimonio,
                    files=files,
                    post=post,
                )

                if not foto:
                    raise ValueError(f"A foto do defeito é obrigatória para o COD {vinculo.cod_patrimonio}.")

                movimento = cls._criar_movimento(
                    vinculo=vinculo,
                    tipo=tipo_movimento,
                    usuario=usuario,
                    estado="Danificado",
                    checklist=checklist,
                    observacoes=observacoes,
                )

                cls._salvar_foto_defeito(
                    movimento=movimento,
                    vinculo=vinculo,
                    foto=foto,
                    usuario=request_user,
                )

                vinculo.status = "Danificado"
                vinculo.save(update_fields=["status", "updated_at"])

                cls._atualizar_produto_status(vinculo, "Manutenção")

            else:
                cls._criar_movimento(
                    vinculo=vinculo,
                    tipo=tipo_movimento,
                    usuario=usuario,
                    estado="Bom",
                    checklist=checklist,
                    observacoes=None,
                )

                if modo_normalizado == "retirada":
                    vinculo.status = "Retirado"
                    vinculo.save(update_fields=["status", "updated_at"])
                    cls._atualizar_produto_status(vinculo, "Locado")

                else:
                    vinculo.status = "Devolvido"
                    vinculo.save(update_fields=["status", "updated_at"])
                    cls._atualizar_produto_status(vinculo, "Disponível")

            total += 1

        return total

    @staticmethod
    @transaction.atomic
    def registrar_movimento(
        vinculo: EstoqueVinculo,
        tipo: str,
        usuario: UsuarioApp | None,
        estado="Bom",
        acessorios_conferidos=False,
        checklist=None,
        dias_atraso=0,
        multa_dia=Decimal("0.00"),
        observacoes=None,
    ) -> RetiradaDevolucao:
        valor_multa = Decimal(str(dias_atraso or 0)) * Decimal(str(multa_dia or 0))

        movimento = RetiradaDevolucao.objects.create(
            orcamento=vinculo.orcamento,
            estoque_vinculo=vinculo,
            item=vinculo.item,
            produto=vinculo.produto,
            cod_patrimonio=vinculo.cod_patrimonio,
            tipo_movimento=tipo,
            data_movimento=timezone.now(),
            estado=estado,
            acessorios_conferidos=acessorios_conferidos,
            checklist=checklist or {},
            dias_atraso=dias_atraso or 0,
            multa_dia=multa_dia or Decimal("0.00"),
            valor_multa=valor_multa,
            responsavel=usuario,
            observacoes=observacoes,
        )

        if tipo == "Retirada":
            vinculo.status = "Retirado"

            if vinculo.patrimonio:
                vinculo.patrimonio.status = "Locado"
                vinculo.patrimonio.save(update_fields=["status", "updated_at"])

        else:
            if estado in {"Danificado", "Extraviado"}:
                vinculo.status = "Danificado"

                if vinculo.patrimonio:
                    vinculo.patrimonio.status = estado
                    vinculo.patrimonio.save(update_fields=["status", "updated_at"])

            else:
                vinculo.status = "Devolvido"

                if vinculo.patrimonio:
                    vinculo.patrimonio.status = "Disponível"
                    vinculo.patrimonio.save(update_fields=["status", "updated_at"])

        vinculo.save(update_fields=["status", "updated_at"])

        return movimento