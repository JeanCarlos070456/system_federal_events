from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import (
    EstoqueVinculo,
    Orcamento,
    OrcamentoItem,
    Produto,
    ProdutoPatrimonio,
    UsuarioApp,
)


class EstoqueService:
    STATUS_VINCULO_CANCELADO = {
        "Cancelado",
        "Cancelada",
        "Removido",
        "Removida",
        "Excluído",
        "Excluída",
    }

    @staticmethod
    def _to_int(value, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def normalizar_cod(cod: str | None) -> str:
        return str(cod or "").strip()

    @classmethod
    def _quantidade_item(cls, item: OrcamentoItem) -> int:
        qtd = cls._to_int(getattr(item, "quantidade", None), 1)
        return max(qtd, 1)

    @classmethod
    def _quantidade_vinculo(cls, vinculo: EstoqueVinculo) -> int:
        qtd = cls._to_int(getattr(vinculo, "quantidade", None), 1)
        return max(qtd, 1)

    @classmethod
    def codigo_produto_cadastrado(cls, cod_patrimonio: str) -> bool:
        cod = cls.normalizar_cod(cod_patrimonio)

        if not cod:
            return False

        return Produto.objects.filter(codigo__iexact=cod).exists()

    @classmethod
    def validar_produto_cadastrado(cls, cod_patrimonio: str) -> str:
        cod = cls.normalizar_cod(cod_patrimonio)

        if not cod:
            raise ValueError("Informe um COD válido para vincular ao estoque.")

        if not cls.codigo_produto_cadastrado(cod):
            raise ValueError(
                "Esse Produto não está cadastrado no sistema. "
                "Cadastre o produto antes de vinculá-lo ao estoque."
            )

        return cod

    @classmethod
    def vinculos_ativos_queryset(cls):
        return EstoqueVinculo.objects.exclude(status__in=cls.STATUS_VINCULO_CANCELADO)

    @classmethod
    def buscar_vinculo_ativo_por_cod(cls, cod_patrimonio: str):
        cod = cls.normalizar_cod(cod_patrimonio)

        if not cod:
            return None

        return (
            cls.vinculos_ativos_queryset()
            .select_related("orcamento", "item", "ambiente", "patrimonio")
            .filter(cod_patrimonio=cod)
            .first()
        )

    @classmethod
    def validar_cod_disponivel(cls, cod_patrimonio: str, item: OrcamentoItem) -> str:
        cod = cls.normalizar_cod(cod_patrimonio)

        if not cod:
            raise ValueError("Informe um COD válido para vincular ao estoque.")

        vinculo_existente = cls.buscar_vinculo_ativo_por_cod(cod)

        if vinculo_existente:
            orcamento_codigo = getattr(vinculo_existente.orcamento, "codigo", "-")
            item_nome = getattr(vinculo_existente.item, "equipamento", "-")
            ambiente_nome = getattr(vinculo_existente.ambiente, "nome", "-") if vinculo_existente.ambiente else "-"

            if vinculo_existente.item_id == item.id:
                raise ValueError(
                    f"O COD {cod} já está vinculado a este mesmo item."
                )

            raise ValueError(
                f"O COD {cod} já está vinculado no orçamento {orcamento_codigo}, "
                f"ambiente {ambiente_nome}, item {item_nome}. "
                f"Remova o vínculo antigo antes de usar este COD novamente."
            )

        return cod

    @classmethod
    def quantidade_vinculada_item(cls, item: OrcamentoItem) -> int:
        total = 0
        vinculos = getattr(item, "estoque_vinculos", None)

        if vinculos is None:
            return 0

        for vinculo in vinculos.all():
            status = (getattr(vinculo, "status", "") or "").strip()

            if status in cls.STATUS_VINCULO_CANCELADO:
                continue

            total += cls._quantidade_vinculo(vinculo)

        return total

    @classmethod
    def _status_por_quantidade(cls, solicitado: int, vinculado: int) -> dict:
        solicitado = max(cls._to_int(solicitado, 0), 0)
        vinculado = max(cls._to_int(vinculado, 0), 0)

        vinculado_limitado = min(vinculado, solicitado) if solicitado > 0 else 0
        pendente = max(solicitado - vinculado_limitado, 0)

        if solicitado <= 0 or vinculado_limitado <= 0:
            status = "A fazer"
            classe = "afazer"
        elif vinculado_limitado >= solicitado:
            status = "Concluído"
            classe = "concluido"
        else:
            status = "Em andamento"
            classe = "andamento"

        percentual = 0

        if solicitado > 0:
            percentual = round((vinculado_limitado / solicitado) * 100)

        return {
            "status": status,
            "classe": classe,
            "total_solicitado": solicitado,
            "total_vinculado": vinculado_limitado,
            "total_pendente": pendente,
            "percentual": percentual,
        }

    @classmethod
    def aplicar_status_no_item(cls, item: OrcamentoItem) -> OrcamentoItem:
        solicitado = cls._quantidade_item(item)
        vinculado_real = cls.quantidade_vinculada_item(item)

        info = cls._status_por_quantidade(solicitado, vinculado_real)

        item.estoque_qtd_solicitada = info["total_solicitado"]
        item.estoque_qtd_vinculada = info["total_vinculado"]
        item.estoque_qtd_pendente = info["total_pendente"]
        item.estoque_status = info["status"]
        item.estoque_status_classe = info["classe"]
        item.estoque_percentual = info["percentual"]

        return item

    @classmethod
    def calcular_status_estoque(cls, orcamento: Orcamento) -> dict:
        total_solicitado = 0
        total_vinculado = 0

        itens_manager = getattr(orcamento, "itens", None)

        if itens_manager is None:
            return cls._status_por_quantidade(0, 0)

        for item in itens_manager.all():
            solicitado_item = cls._quantidade_item(item)
            vinculado_item = cls.quantidade_vinculada_item(item)

            total_solicitado += solicitado_item
            total_vinculado += min(vinculado_item, solicitado_item)

        return cls._status_por_quantidade(total_solicitado, total_vinculado)

    @classmethod
    def aplicar_status_estoque_eventos(cls, eventos):
        for evento in eventos:
            info = cls.calcular_status_estoque(evento)

            evento.status_estoque = info["status"]
            evento.status_estoque_classe = info["classe"]
            evento.estoque_total_solicitado = info["total_solicitado"]
            evento.estoque_total_vinculado = info["total_vinculado"]
            evento.estoque_total_pendente = info["total_pendente"]
            evento.estoque_percentual = info["percentual"]

        return eventos

    @classmethod
    def aplicar_status_estoque_itens(cls, orcamento: Orcamento) -> Orcamento:
        for item in orcamento.itens.all():
            cls.aplicar_status_no_item(item)

        return orcamento

    @classmethod
    def montar_grupos_por_ambiente(cls, orcamento: Orcamento) -> list[dict]:
        grupos = []
        ids_itens_com_ambiente = set()

        ambientes_manager = getattr(orcamento, "ambientes", None)

        if ambientes_manager is not None:
            for ambiente in ambientes_manager.all():
                itens = list(ambiente.itens.all())

                if not itens:
                    continue

                total_solicitado = 0
                total_vinculado = 0

                for item in itens:
                    cls.aplicar_status_no_item(item)

                    ids_itens_com_ambiente.add(item.id)

                    solicitado = cls._quantidade_item(item)
                    vinculado = cls.quantidade_vinculada_item(item)

                    total_solicitado += solicitado
                    total_vinculado += min(vinculado, solicitado)

                info_grupo = cls._status_por_quantidade(total_solicitado, total_vinculado)

                nome_ambiente = getattr(ambiente, "nome", "") or "Ambiente sem nome"

                try:
                    tipo_ambiente = ambiente.get_tipo_display()
                except Exception:
                    tipo_ambiente = getattr(ambiente, "tipo", "") or "Ambiente"

                grupos.append(
                    {
                        "ambiente": ambiente,
                        "nome": nome_ambiente,
                        "tipo": tipo_ambiente,
                        "itens": itens,
                        "status": info_grupo["status"],
                        "classe": info_grupo["classe"],
                        "total_solicitado": info_grupo["total_solicitado"],
                        "total_vinculado": info_grupo["total_vinculado"],
                        "total_pendente": info_grupo["total_pendente"],
                        "percentual": info_grupo["percentual"],
                    }
                )

        itens_sem_ambiente = []

        for item in orcamento.itens.all():
            if item.id in ids_itens_com_ambiente:
                continue

            if getattr(item, "ambiente_id", None) is None:
                itens_sem_ambiente.append(item)

        if itens_sem_ambiente:
            total_solicitado = 0
            total_vinculado = 0

            for item in itens_sem_ambiente:
                cls.aplicar_status_no_item(item)

                solicitado = cls._quantidade_item(item)
                vinculado = cls.quantidade_vinculada_item(item)

                total_solicitado += solicitado
                total_vinculado += min(vinculado, solicitado)

            info_grupo = cls._status_por_quantidade(total_solicitado, total_vinculado)

            grupos.append(
                {
                    "ambiente": None,
                    "nome": "Sem ambiente definido",
                    "tipo": "Geral",
                    "itens": itens_sem_ambiente,
                    "status": info_grupo["status"],
                    "classe": info_grupo["classe"],
                    "total_solicitado": info_grupo["total_solicitado"],
                    "total_vinculado": info_grupo["total_vinculado"],
                    "total_pendente": info_grupo["total_pendente"],
                    "percentual": info_grupo["percentual"],
                }
            )

        return grupos

    @staticmethod
    @transaction.atomic
    def vincular_patrimonio(
        item: OrcamentoItem,
        patrimonio: ProdutoPatrimonio | None,
        cod_patrimonio: str,
        usuario: UsuarioApp | None,
        **extra,
    ) -> EstoqueVinculo:
        cod_normalizado = EstoqueService.validar_produto_cadastrado(cod_patrimonio)

        cod_normalizado = EstoqueService.validar_cod_disponivel(
            cod_patrimonio=cod_normalizado,
            item=item,
        )

        try:
            vinculo = EstoqueVinculo.objects.create(
                orcamento=item.orcamento,
                ambiente=item.ambiente,
                item=item,
                produto=item.produto,
                patrimonio=patrimonio,
                cod_patrimonio=cod_normalizado,
                descricao=extra.get("descricao") or item.descricao,
                quantidade=extra.get("quantidade") or 1,
                status=extra.get("status") or "Vinculado",
                vinculado_por=usuario,
                vinculado_em=timezone.now(),
                observacoes=extra.get("observacoes"),
            )

        except IntegrityError:
            raise ValueError(
                f"O COD {cod_normalizado} já está vinculado em outro item ativo. "
                f"Remova o vínculo antigo antes de usar este COD novamente."
            )

        if patrimonio:
            patrimonio.status = "Reservado"
            patrimonio.save(update_fields=["status", "updated_at"])

        return vinculo

    @staticmethod
    @transaction.atomic
    def excluir_vinculo(vinculo: EstoqueVinculo) -> None:
        patrimonio = vinculo.patrimonio

        if patrimonio:
            patrimonio.status = "Disponível"
            patrimonio.save(update_fields=["status", "updated_at"])

        vinculo.delete()