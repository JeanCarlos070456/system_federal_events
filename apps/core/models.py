from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models


class TimeStampedMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Perfil(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "perfis"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class UsuarioApp(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, editable=False)
    nome = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    perfil = models.CharField(max_length=120)
    telefone = models.CharField(max_length=50, blank=True, null=True)
    cargo = models.CharField(max_length=120, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    ultimo_login = models.DateTimeField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "usuarios_app"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class PaginaSistema(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    ordem = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "paginas_sistema"
        ordering = ["ordem", "nome"]

    def __str__(self) -> str:
        return self.nome


class PerfilPermissao(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    perfil = models.CharField(max_length=120)
    pagina = models.CharField(max_length=120)
    pode_acessar = models.BooleanField(default=True)
    pode_criar = models.BooleanField(default=False)
    pode_editar = models.BooleanField(default=False)
    pode_excluir = models.BooleanField(default=False)
    pode_exportar = models.BooleanField(default=False)

    class Meta:
        managed = False
        db_table = "perfil_permissoes"
        unique_together = (("perfil", "pagina"),)

    def __str__(self) -> str:
        return f"{self.perfil} → {self.pagina}"


class Cliente(TimeStampedMixin):
    TIPO_CHOICES = (("fisica", "Física"), ("juridica", "Jurídica"))
    STATUS_CHOICES = (("Ativo", "Ativo"), ("Inativo", "Inativo"), ("Bloqueado", "Bloqueado"), ("Prospecto", "Prospecto"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=255)
    tipo_pessoa = models.CharField(max_length=20, choices=TIPO_CHOICES, default="juridica")
    documento = models.CharField(max_length=40, unique=True, blank=True, null=True)
    inscricao_estadual = models.CharField(max_length=80, blank=True, null=True)
    responsavel_nome = models.CharField(max_length=255, blank=True, null=True)
    responsavel_cargo = models.CharField(max_length=120, blank=True, null=True)
    telefone = models.CharField(max_length=50, blank=True, null=True)
    whatsapp = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    cep = models.CharField(max_length=20, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=40, blank=True, null=True)
    complemento = models.CharField(max_length=120, blank=True, null=True)
    bairro = models.CharField(max_length=120, blank=True, null=True)
    cidade = models.CharField(max_length=120, blank=True, null=True)
    uf = models.CharField(max_length=2, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="Ativo")
    origem = models.CharField(max_length=120, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="criado_por", related_name="clientes_criados")
    atualizado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="atualizado_por", related_name="clientes_atualizados")

    class Meta:
        managed = False
        db_table = "clientes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.nome


class Produto(TimeStampedMixin):
    STATUS_CHOICES = (
        ("Disponível", "Disponível"), ("Reservado", "Reservado"), ("Locado", "Locado"),
        ("Manutenção", "Manutenção"), ("Inativo", "Inativo"), ("Danificado", "Danificado"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo = models.CharField(max_length=80, unique=True)
    nome = models.CharField(max_length=255)
    categoria = models.CharField(max_length=120, blank=True, null=True)
    subcategoria = models.CharField(max_length=120, blank=True, null=True)
    marca = models.CharField(max_length=120, blank=True, null=True)
    modelo = models.CharField(max_length=120, blank=True, null=True)
    descricao = models.TextField(blank=True, null=True)
    especificacoes = models.TextField(blank=True, null=True)
    valor_diaria = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    valor_semanal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    valor_mensal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    quantidade_total = models.IntegerField(default=0)
    quantidade_disponivel = models.IntegerField(default=0)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Disponível")
    localizacao = models.CharField(max_length=120, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="criado_por", related_name="produtos_criados")
    atualizado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="atualizado_por", related_name="produtos_atualizados")

    class Meta:
        managed = False
        db_table = "produtos"
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nome}"


class ProdutoPatrimonio(TimeStampedMixin):
    STATUS_CHOICES = (
        ("Disponível", "Disponível"), ("Reservado", "Reservado"), ("Locado", "Locado"),
        ("Manutenção", "Manutenção"), ("Inativo", "Inativo"), ("Danificado", "Danificado"), ("Extraviado", "Extraviado"),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    produto = models.ForeignKey(Produto, models.CASCADE, db_column="produto_id", related_name="patrimonios")
    cod_patrimonio = models.CharField(max_length=120, unique=True)
    numero_serie = models.CharField(max_length=120, blank=True, null=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Disponível")
    localizacao = models.CharField(max_length=120, blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "produto_patrimonios"
        ordering = ["cod_patrimonio"]

    def __str__(self) -> str:
        return self.cod_patrimonio


class Orcamento(TimeStampedMixin):
    STATUS_CHOICES = (
        ("Em análise", "Em análise"),
        ("Aprovado", "Aprovado"),
    )
    FINANCEIRO_CHOICES = (("Pendente", "Pendente"), ("Parcial", "Parcial"), ("Pago", "Pago"), ("Atrasado", "Atrasado"), ("Cancelado", "Cancelado"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codigo = models.CharField(max_length=80, unique=True)
    cliente = models.ForeignKey(Cliente, models.SET_NULL, blank=True, null=True, db_column="cliente_id", related_name="orcamentos")
    cliente_nome = models.CharField(max_length=255, blank=True, null=True)
    cliente_documento = models.CharField(max_length=40, blank=True, null=True)
    responsavel_cliente = models.CharField(max_length=255, blank=True, null=True)
    evento_nome = models.CharField(max_length=255)
    local_evento = models.CharField(max_length=255, blank=True, null=True)
    data_envio = models.DateField(blank=True, null=True)
    validade_dias = models.IntegerField(default=7)
    data_montagem = models.DateField(blank=True, null=True)
    data_inicio = models.DateField(blank=True, null=True)
    data_fim = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Em análise")
    financeiro = models.CharField(max_length=40, choices=FINANCEIRO_CHOICES, default="Pendente")
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    valor_desconto = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    valor_caucao = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    valor_final = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    observacoes = models.TextField(blank=True, null=True)
    condicoes_pagamento = models.TextField(blank=True, null=True)
    criado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="criado_por", related_name="orcamentos_criados")
    atualizado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="atualizado_por", related_name="orcamentos_atualizados")

    class Meta:
        managed = False
        db_table = "orcamentos"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.codigo} - {self.evento_nome}"


class OrcamentoAmbiente(TimeStampedMixin):
    """
    Ambiente/sala do orçamento.

    O campo tipo aceita valores livres para permitir ambientes como Garagem,
    Camarim, Palco, Área externa etc. Mantemos get_tipo_display para
    compatibilidade com templates e PDFs que já chamavam esse método.
    """

    TIPO_LEGACY_LABELS = {
        "sala": "Sala",
        "auditorio": "Auditório",
        "auditório": "Auditório",
        "credenciamento": "Credenciamento",
        "outro": "Outro",
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, db_column="orcamento_id", related_name="ambientes")
    tipo = models.CharField(max_length=40, default="Sala")
    nome = models.CharField(max_length=255)
    ordem = models.IntegerField(default=0)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "orcamento_ambientes"
        ordering = ["ordem", "created_at"]

    def get_tipo_display(self) -> str:
        tipo = (self.tipo or "").strip()

        if not tipo:
            return "Ambiente"

        return self.TIPO_LEGACY_LABELS.get(tipo.lower(), tipo)

    def __str__(self) -> str:
        return self.nome

class OrcamentoItem(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, db_column="orcamento_id", related_name="itens")
    ambiente = models.ForeignKey(OrcamentoAmbiente, models.CASCADE, blank=True, null=True, db_column="ambiente_id", related_name="itens")
    produto = models.ForeignKey(Produto, models.SET_NULL, blank=True, null=True, db_column="produto_id", related_name="orcamento_itens")
    equipamento = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)
    quantidade = models.IntegerField(default=1)
    dias_uso = models.IntegerField(default=1)
    valor_diaria = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    ordem = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = "orcamento_itens"
        ordering = ["ordem", "created_at"]

    def __str__(self) -> str:
        return self.equipamento


class EstoqueVinculo(TimeStampedMixin):
    STATUS_CHOICES = (("Vinculado", "Vinculado"), ("Separado", "Separado"), ("Retirado", "Retirado"), ("Devolvido", "Devolvido"), ("Danificado", "Danificado"), ("Cancelado", "Cancelado"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, db_column="orcamento_id", related_name="estoque_vinculos")
    ambiente = models.ForeignKey(OrcamentoAmbiente, models.SET_NULL, blank=True, null=True, db_column="ambiente_id", related_name="estoque_vinculos")
    item = models.ForeignKey(OrcamentoItem, models.CASCADE, db_column="item_id", related_name="estoque_vinculos")
    produto = models.ForeignKey(Produto, models.SET_NULL, blank=True, null=True, db_column="produto_id", related_name="estoque_vinculos")
    patrimonio = models.ForeignKey(ProdutoPatrimonio, models.SET_NULL, blank=True, null=True, db_column="patrimonio_id", related_name="estoque_vinculos")
    cod_patrimonio = models.CharField(max_length=120)
    descricao = models.TextField(blank=True, null=True)
    quantidade = models.IntegerField(default=1)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Vinculado")
    vinculado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="vinculado_por", related_name="estoque_vinculos")
    vinculado_em = models.DateTimeField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "estoque_vinculos"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.cod_patrimonio} - {self.status}"


class AgendaEvento(TimeStampedMixin):
    TIPO_CHOICES = (("Evento", "Evento"), ("Montagem", "Montagem"), ("Retirada", "Retirada"), ("Devolução", "Devolução"), ("Reunião", "Reunião"), ("Outro", "Outro"))
    STATUS_CHOICES = (("Agendado", "Agendado"), ("Em andamento", "Em andamento"), ("Concluído", "Concluído"), ("Cancelado", "Cancelado"), ("Atrasado", "Atrasado"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, blank=True, null=True, db_column="orcamento_id", related_name="agenda_eventos")
    titulo = models.CharField(max_length=255)
    tipo_evento = models.CharField(max_length=40, choices=TIPO_CHOICES, default="Evento")
    data_inicio = models.DateField()
    data_fim = models.DateField(blank=True, null=True)
    horario_inicio = models.TimeField(blank=True, null=True)
    horario_fim = models.TimeField(blank=True, null=True)
    local_evento = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Agendado")
    responsavel = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="responsavel_id", related_name="agenda_eventos")
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "agenda_eventos"
        ordering = ["data_inicio", "horario_inicio"]

    def __str__(self) -> str:
        return self.titulo


class FinanceiroMovimento(TimeStampedMixin):
    TIPO_CHOICES = (("Receita", "Receita"), ("Despesa", "Despesa"), ("Estorno", "Estorno"), ("Ajuste", "Ajuste"))
    STATUS_CHOICES = (("Pendente", "Pendente"), ("Pago", "Pago"), ("Parcial", "Parcial"), ("Atrasado", "Atrasado"), ("Cancelado", "Cancelado"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, blank=True, null=True, db_column="orcamento_id", related_name="financeiro_movimentos")
    cliente = models.ForeignKey(Cliente, models.SET_NULL, blank=True, null=True, db_column="cliente_id", related_name="financeiro_movimentos")
    tipo = models.CharField(max_length=40, choices=TIPO_CHOICES, default="Receita")
    categoria = models.CharField(max_length=120, blank=True, null=True)
    descricao = models.CharField(max_length=255)
    valor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    forma_pagamento = models.CharField(max_length=80, blank=True, null=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="Pendente")
    data_vencimento = models.DateField(blank=True, null=True)
    data_pagamento = models.DateField(blank=True, null=True)
    comprovante_url = models.URLField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    criado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="criado_por", related_name="financeiro_criados")
    atualizado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="atualizado_por", related_name="financeiro_atualizados")

    class Meta:
        managed = False
        db_table = "financeiro_movimentos"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.descricao


class RetiradaDevolucao(TimeStampedMixin):
    TIPO_CHOICES = (("Retirada", "Retirada"), ("Devolução", "Devolução"))
    ESTADO_CHOICES = (("Novo", "Novo"), ("Bom", "Bom"), ("Regular", "Regular"), ("Danificado", "Danificado"), ("Extraviado", "Extraviado"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orcamento = models.ForeignKey(Orcamento, models.CASCADE, db_column="orcamento_id", related_name="retiradas_devolucoes")
    estoque_vinculo = models.ForeignKey(EstoqueVinculo, models.SET_NULL, blank=True, null=True, db_column="estoque_vinculo_id", related_name="movimentos")
    item = models.ForeignKey(OrcamentoItem, models.SET_NULL, blank=True, null=True, db_column="item_id", related_name="movimentos")
    produto = models.ForeignKey(Produto, models.SET_NULL, blank=True, null=True, db_column="produto_id", related_name="movimentos")
    cod_patrimonio = models.CharField(max_length=120, blank=True, null=True)
    tipo_movimento = models.CharField(max_length=40, choices=TIPO_CHOICES)
    data_movimento = models.DateTimeField(blank=True, null=True)
    estado = models.CharField(max_length=40, choices=ESTADO_CHOICES, default="Bom")
    acessorios_conferidos = models.BooleanField(default=False)
    checklist = models.JSONField(default=dict)
    dias_atraso = models.IntegerField(default=0)
    multa_dia = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    valor_multa = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    responsavel = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="responsavel_id", related_name="movimentos_operacionais")
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "retirada_devolucao"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tipo_movimento} - {self.cod_patrimonio}"


class Arquivo(TimeStampedMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entidade = models.CharField(max_length=80)
    entidade_id = models.UUIDField(blank=True, null=True)
    tipo_arquivo = models.CharField(max_length=80, blank=True, null=True)
    nome_original = models.CharField(max_length=255)
    nome_armazenado = models.CharField(max_length=255, blank=True, null=True)
    extensao = models.CharField(max_length=20, blank=True, null=True)
    mime_type = models.CharField(max_length=120, blank=True, null=True)
    tamanho_bytes = models.BigIntegerField(blank=True, null=True)
    storage_provider = models.CharField(max_length=80, default="supabase")
    bucket = models.CharField(max_length=120, blank=True, null=True)
    path = models.TextField(blank=True, null=True)
    public_url = models.URLField(blank=True, null=True)
    enviado_por = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="enviado_por", related_name="arquivos_enviados")

    class Meta:
        managed = False
        db_table = "arquivos"
        ordering = ["-created_at"]


class LogSistema(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(UsuarioApp, models.SET_NULL, blank=True, null=True, db_column="usuario_id")
    nivel = models.CharField(max_length=20, default="INFO")
    modulo = models.CharField(max_length=120, blank=True, null=True)
    acao = models.CharField(max_length=120)
    entidade = models.CharField(max_length=120, blank=True, null=True)
    entidade_id = models.UUIDField(blank=True, null=True)
    mensagem = models.TextField(blank=True, null=True)
    dados = models.JSONField(default=dict)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "logs_sistema"
        ordering = ["-created_at"]