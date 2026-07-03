from __future__ import annotations

import base64
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import permission_required
from apps.arquivos.services import ArquivoService
from apps.core.logging import log_action
from apps.core.models import Arquivo, EstoqueVinculo, Produto, ProdutoPatrimonio
from .forms import ProdutoForm, ProdutoPatrimonioForm


STATUS_PRODUTOS = [
    "Disponível",
    "Reservado",
    "Locado",
    "Manutenção",
    "Inativo",
    "Danificado",
]


IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
VIDEO_EXTS = {"mp4", "mov", "avi", "mkv", "webm"}
DOC_EXTS = {"pdf", "doc", "docx", "xls", "xlsx", "txt"}

PERFIS_ADMIN_VALORES = {
    "admin_empresa",
    "administrador",
    "admin",
    "superadmin",
}


def _normalizar_texto(value: str | None) -> str:
    return (value or "").strip().lower()


def _get_app_user_perfil(request) -> str:
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return ""

    if isinstance(app_user, dict):
        return _normalizar_texto(app_user.get("perfil"))

    return _normalizar_texto(getattr(app_user, "perfil", ""))


def _usuario_pode_ver_valores(request) -> bool:
    perfil = _get_app_user_perfil(request)
    return perfil in PERFIS_ADMIN_VALORES


def _produto_tem_valor(produto: Produto) -> bool:
    diaria = getattr(produto, "valor_diaria", None) or Decimal("0.00")
    semanal = getattr(produto, "valor_semanal", None) or Decimal("0.00")
    mensal = getattr(produto, "valor_mensal", None) or Decimal("0.00")

    return diaria > 0 or semanal > 0 or mensal > 0


def _aplicar_quantidade_unitaria(produto: Produto) -> Produto:
    """
    Cada produto representa uma unidade física única.
    O código escaneado identifica esse equipamento individual.
    """
    produto.quantidade_total = 1

    status = _normalizar_texto(produto.status)

    if status in {"disponível", "disponivel"}:
        produto.quantidade_disponivel = 1
    else:
        produto.quantidade_disponivel = 0

    return produto


def _foto_camera_para_file(data_url: str | None, codigo: str | None = None):
    """
    Converte imagem capturada via câmera no navegador em arquivo Django.
    Espera algo como:
    data:image/png;base64,AAA...
    """
    if not data_url:
        return None

    if not data_url.startswith("data:image/"):
        return None

    try:
        header, encoded = data_url.split(",", 1)
        mime_part = header.split(";")[0]
        mime_type = mime_part.replace("data:", "").strip() or "image/png"
        ext = mime_type.split("/")[-1].replace("jpeg", "jpg")

        raw = base64.b64decode(encoded)

        nome = f"foto_produto_{codigo or 'sem_codigo'}.{ext}"
        file_obj = ContentFile(raw, name=nome)
        file_obj.content_type = mime_type
        file_obj.size = len(raw)

        return file_obj
    except Exception:
        return None


def _salvar_foto_produto(request, produto: Produto) -> None:
    """
    Salva foto do produto no Supabase Storage e registra em arquivos.

    Fontes aceitas:
    1. Arquivo enviado pelo input foto_produto.
    2. Foto capturada pela câmera em base64 no campo foto_camera_base64.
    """
    foto_upload = request.FILES.get("foto_produto")
    foto_camera = _foto_camera_para_file(
        request.POST.get("foto_camera_base64"),
        codigo=produto.codigo,
    )

    foto = foto_upload or foto_camera

    if not foto:
        return

    try:
        ArquivoService.upload_e_registrar(
            entidade="produto",
            entidade_id=produto.id,
            file_obj=foto,
            usuario=request.app_user,
            tipo="imagem",
            codigo_referencia=produto.codigo,
        )

        messages.success(request, "Foto do produto salvo com sucesso.")
    except Exception as exc:
        messages.warning(
            request,
            f"Produto salvo, mas a foto não foi enviada para o bucket: {exc}",
        )


def _status_class(status: str | None) -> str:
    status_norm = _normalizar_texto(status)

    if any(
        token in status_norm
        for token in ["manutenção", "manutencao", "danificado", "inativo", "extraviado"]
    ):
        return "danger"

    if any(
        token in status_norm
        for token in ["locado", "reservado", "retirado", "separado"]
    ):
        return "warning"

    if any(
        token in status_norm
        for token in ["disponível", "disponivel", "vinculado", "devolvido"]
    ):
        return "success"

    return "neutral"


def _arquivo_url(arquivo: Arquivo) -> str:
    if getattr(arquivo, "public_url", None):
        return arquivo.public_url

    path = getattr(arquivo, "path", None)

    if path and str(path).startswith(("http://", "https://")):
        return str(path)

    return ""


def _classificar_arquivo(arquivo: Arquivo) -> str:
    tipo = _normalizar_texto(getattr(arquivo, "tipo_arquivo", None))
    mime = _normalizar_texto(getattr(arquivo, "mime_type", None))
    extensao = _normalizar_texto(getattr(arquivo, "extensao", None))

    if "imagem" in tipo or "image" in mime or extensao in IMAGE_EXTS:
        return "imagem"

    if "video" in tipo or "vídeo" in tipo or "video" in mime or extensao in VIDEO_EXTS:
        return "video"

    if extensao in DOC_EXTS or "manual" in tipo or "documento" in tipo:
        return "documento"

    return "outro"


def _preparar_arquivos_produtos(produtos: list[Produto]) -> dict:
    produto_ids = [produto.id for produto in produtos]

    arquivos_map = defaultdict(
        lambda: {
            "imagens": [],
            "videos": [],
            "documentos": [],
            "outros": [],
        }
    )

    if not produto_ids:
        return arquivos_map

    arquivos = (
        Arquivo.objects
        .filter(entidade__iexact="produto", entidade_id__in=produto_ids)
        .order_by("-created_at")
    )

    for arquivo in arquivos:
        arquivo.file_url = _arquivo_url(arquivo)
        grupo = _classificar_arquivo(arquivo)

        if grupo == "imagem":
            arquivos_map[arquivo.entidade_id]["imagens"].append(arquivo)
        elif grupo == "video":
            arquivos_map[arquivo.entidade_id]["videos"].append(arquivo)
        elif grupo == "documento":
            arquivos_map[arquivo.entidade_id]["documentos"].append(arquivo)
        else:
            arquivos_map[arquivo.entidade_id]["outros"].append(arquivo)

    return arquivos_map


def _preparar_contagem_patrimonios(produtos: list[Produto]) -> dict:
    produto_ids = [produto.id for produto in produtos]

    if not produto_ids:
        return {}

    patrimonio_rows = (
        ProdutoPatrimonio.objects
        .filter(produto_id__in=produto_ids)
        .values("produto_id")
        .annotate(total=Count("id"))
    )

    vinculo_rows = (
        EstoqueVinculo.objects
        .filter(produto_id__in=produto_ids)
        .values("produto_id")
        .annotate(total=Count("id"))
    )

    contador = defaultdict(int)

    for row in patrimonio_rows:
        contador[row["produto_id"]] += row["total"] or 0

    for row in vinculo_rows:
        contador[row["produto_id"]] += row["total"] or 0

    return contador


def _preparar_cards(produtos: list[Produto]) -> list[Produto]:
    arquivos_map = _preparar_arquivos_produtos(produtos)
    patrimonio_count_map = _preparar_contagem_patrimonios(produtos)

    for produto in produtos:
        grupos = arquivos_map.get(
            produto.id,
            {
                "imagens": [],
                "videos": [],
                "documentos": [],
                "outros": [],
            },
        )

        imagens = grupos.get("imagens", [])
        videos = grupos.get("videos", [])
        documentos = grupos.get("documentos", [])

        produto.card_status_class = _status_class(produto.status)
        produto.card_imagens_count = len(imagens)
        produto.card_videos_count = len(videos)
        produto.card_documentos_count = len(documentos)
        produto.card_patrimonios_count = patrimonio_count_map.get(produto.id, 0)
        produto.card_image_url = imagens[0].file_url if imagens and imagens[0].file_url else ""
        produto.card_tem_valor = _produto_tem_valor(produto)

    return produtos


@permission_required("Produtos")
def index(request):
    q = request.GET.get("q", "").strip()

    selected_status = [
        item.strip()
        for item in request.GET.getlist("status")
        if item.strip()
    ]

    selected_categorias = [
        item.strip()
        for item in request.GET.getlist("categoria")
        if item.strip()
    ]

    produtos = Produto.objects.all().order_by("nome")

    if q:
        produtos = produtos.filter(
            Q(nome__icontains=q)
            | Q(codigo__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(descricao__icontains=q)
        )

    if selected_status:
        produtos = produtos.filter(status__in=selected_status)

    if selected_categorias:
        produtos = produtos.filter(categoria__in=selected_categorias)

    categorias = list(
        Produto.objects
        .exclude(categoria__isnull=True)
        .exclude(categoria="")
        .values_list("categoria", flat=True)
        .distinct()
        .order_by("categoria")
    )

    paginator = Paginator(produtos, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_obj.object_list = _preparar_cards(list(page_obj.object_list))

    can_manage_values = _usuario_pode_ver_valores(request)

    context = {
        "page_obj": page_obj,
        "q": q,
        "selected_status": selected_status,
        "selected_categorias": selected_categorias,
        "categorias": categorias,
        "status_options": STATUS_PRODUTOS,
        "can_manage_values": can_manage_values,
        "page_title": "Produtos",
    }

    return render(request, "produtos/index.html", context)


@permission_required("Produtos", "pode_criar")
def create(request):
    can_manage_values = _usuario_pode_ver_valores(request)
    form = ProdutoForm(
        request.POST or None,
        can_manage_values=can_manage_values,
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj = _aplicar_quantidade_unitaria(obj)

        if request.app_user:
            obj.criado_por_id = request.app_user.id
            obj.atualizado_por_id = request.app_user.id

        obj.save()
        _salvar_foto_produto(request, obj)

        log_action(
            request,
            "produtos",
            "criar",
            "produto",
            obj.id,
            "Produto criado como unidade física única",
        )

        messages.success(request, "Produto cadastrado com sucesso.")
        return redirect("produtos:detail", pk=obj.pk)

    return render(
        request,
        "produtos/form.html",
        {
            "form": form,
            "can_manage_values": can_manage_values,
            "page_title": "Novo Produto",
        },
    )


@permission_required("Produtos")
def detail(request, pk):
    produto = get_object_or_404(Produto, pk=pk)

    patrimonios = produto.patrimonios.all().order_by("cod_patrimonio")

    estoque_vinculos = (
        produto.estoque_vinculos
        .select_related("orcamento", "item")
        .order_by("-created_at")[:50]
    )

    arquivos = (
        Arquivo.objects
        .filter(entidade__iexact="produto", entidade_id=produto.id)
        .order_by("-created_at")
    )

    imagens = []
    videos = []
    documentos = []
    outros = []

    for arquivo in arquivos:
        arquivo.file_url = _arquivo_url(arquivo)
        grupo = _classificar_arquivo(arquivo)

        if grupo == "imagem":
            imagens.append(arquivo)
        elif grupo == "video":
            videos.append(arquivo)
        elif grupo == "documento":
            documentos.append(arquivo)
        else:
            outros.append(arquivo)

    produto.detail_status_class = _status_class(produto.status)
    produto.detail_tem_valor = _produto_tem_valor(produto)

    can_manage_values = _usuario_pode_ver_valores(request)

    context = {
        "produto": produto,
        "patrimonios": patrimonios,
        "estoque_vinculos": estoque_vinculos,
        "imagens": imagens,
        "videos": videos,
        "documentos": documentos,
        "outros": outros,
        "imagem_principal": imagens[0] if imagens else None,
        "can_manage_values": can_manage_values,
        "page_title": produto.nome,
    }

    return render(request, "produtos/detail.html", context)


@permission_required("Produtos", "pode_editar")
def update(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    can_manage_values = _usuario_pode_ver_valores(request)

    form = ProdutoForm(
        request.POST or None,
        instance=produto,
        can_manage_values=can_manage_values,
    )

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj = _aplicar_quantidade_unitaria(obj)

        if request.app_user:
            obj.atualizado_por_id = request.app_user.id

        obj.save()
        _salvar_foto_produto(request, obj)

        log_action(
            request,
            "produtos",
            "editar",
            "produto",
            obj.id,
            "Produto atualizado como unidade física única",
        )

        messages.success(request, "Produto atualizado com sucesso.")
        return redirect("produtos:detail", pk=obj.pk)

    return render(
        request,
        "produtos/form.html",
        {
            "form": form,
            "produto": produto,
            "can_manage_values": can_manage_values,
            "page_title": "Editar Produto",
        },
    )


@permission_required("Produtos", "pode_criar")
def patrimonio_create(request, produto_id):
    produto = get_object_or_404(Produto, pk=produto_id)
    form = ProdutoPatrimonioForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        patrimonio = form.save(commit=False)
        patrimonio.produto = produto
        patrimonio.save()

        produto = _aplicar_quantidade_unitaria(produto)
        produto.save(
            update_fields=[
                "quantidade_total",
                "quantidade_disponivel",
                "updated_at",
            ]
        )

        log_action(
            request,
            "produtos",
            "criar_patrimonio",
            "produto_patrimonio",
            patrimonio.id,
            "Patrimônio/COD complementar criado",
        )

        messages.success(request, "COD/Patrimônio cadastrado com sucesso.")
        return redirect("produtos:detail", pk=produto.pk)

    return render(
        request,
        "produtos/patrimonio_form.html",
        {
            "form": form,
            "produto": produto,
            "page_title": "Novo Patrimônio",
        },
    )