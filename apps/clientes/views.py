from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import permission_required
from apps.core.logging import log_action
from apps.core.models import Cliente
from .forms import ClienteForm


BRASILAPI_CNPJ_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"


def _only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _format_cnpj(value: str | None) -> str:
    digits = _only_digits(value)

    if len(digits) != 14:
        return value or ""

    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _format_cep(value: str | None) -> str:
    digits = _only_digits(value)

    if len(digits) != 8:
        return value or ""

    return f"{digits[:5]}-{digits[5:]}"


def _format_phone(value: str | None) -> str:
    digits = _only_digits(value)

    if not digits:
        return ""

    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"

    return value or digits


def _situacao_para_status(value: str | None) -> str:
    situacao = (value or "").strip().lower()

    if "ativa" in situacao:
        return "Ativo"

    if any(token in situacao for token in ["baixada", "inapta", "suspensa", "nula"]):
        return "Bloqueado"

    return "Prospecto"


def _primeiro_socio(data: dict) -> dict:
    qsa = data.get("qsa") or []

    if isinstance(qsa, list) and qsa:
        item = qsa[0]

        if isinstance(item, dict):
            return item

    return {}


def _montar_observacoes_cnpj(data: dict) -> str:
    partes = []

    situacao = data.get("descricao_situacao_cadastral")
    cnae = data.get("cnae_fiscal_descricao")
    fantasia = data.get("nome_fantasia")
    natureza = data.get("natureza_juridica")
    abertura = data.get("data_inicio_atividade")

    if fantasia:
        partes.append(f"Nome fantasia: {fantasia}")

    if situacao:
        partes.append(f"Situação cadastral: {situacao}")

    if cnae:
        partes.append(f"CNAE principal: {cnae}")

    if natureza:
        partes.append(f"Natureza jurídica: {natureza}")

    if abertura:
        partes.append(f"Data de abertura: {abertura}")

    if partes:
        return " | ".join(partes)

    return ""


def _get_app_user_id(request):
    app_user = getattr(request, "app_user", None)

    if not app_user:
        return None

    if isinstance(app_user, dict):
        return app_user.get("id") or app_user.get("pk") or app_user.get("usuario_id")

    return getattr(app_user, "id", None) or getattr(app_user, "pk", None)


def _map_brasilapi_to_cliente(data: dict) -> dict:
    socio = _primeiro_socio(data)

    telefone_1 = _format_phone(data.get("ddd_telefone_1"))
    telefone_2 = _format_phone(data.get("ddd_telefone_2"))

    telefone = telefone_1 or telefone_2
    whatsapp = telefone_1 or telefone_2

    razao_social = data.get("razao_social") or ""
    nome_fantasia = data.get("nome_fantasia") or ""
    nome = razao_social or nome_fantasia

    cep = _format_cep(data.get("cep"))
    municipio = data.get("municipio") or ""
    uf = data.get("uf") or ""

    return {
        "nome": nome,
        "tipo_pessoa": "juridica",
        "documento": _format_cnpj(data.get("cnpj")),
        "inscricao_estadual": "",
        "responsavel_nome": socio.get("nome_socio") or "",
        "responsavel_cargo": socio.get("qualificacao_socio") or "",
        "telefone": telefone,
        "whatsapp": whatsapp,
        "email": data.get("email") or "",
        "cep": cep,
        "endereco": data.get("logradouro") or "",
        "numero": data.get("numero") or "",
        "complemento": data.get("complemento") or "",
        "bairro": data.get("bairro") or "",
        "cidade": municipio,
        "uf": uf,
        "status": _situacao_para_status(data.get("descricao_situacao_cadastral")),
        "origem": "BrasilAPI CNPJ",
        "observacoes": _montar_observacoes_cnpj(data),
        "nome_fantasia": nome_fantasia,
        "situacao_cadastral": data.get("descricao_situacao_cadastral") or "",
        "cnae_principal": data.get("cnae_fiscal_descricao") or "",
        "logo_url": "",
    }


@permission_required("Clientes")
def buscar_cnpj(request):
    cnpj = _only_digits(request.GET.get("cnpj"))

    if len(cnpj) != 14:
        return JsonResponse(
            {
                "ok": False,
                "message": "Informe um CNPJ válido com 14 dígitos.",
            },
            status=400,
        )

    url = BRASILAPI_CNPJ_URL.format(cnpj=cnpj)

    try:
        req = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "FederalEventosDjango/1.0",
            },
        )

        with urlopen(req, timeout=12) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload)

        cliente_data = _map_brasilapi_to_cliente(data)

        return JsonResponse(
            {
                "ok": True,
                "source": "BrasilAPI",
                "data": cliente_data,
            }
        )

    except HTTPError as exc:
        if exc.code == 404:
            message = "CNPJ não encontrado na BrasilAPI."
        elif exc.code == 429:
            message = "Muitas consultas em sequência. Aguarde alguns instantes e tente novamente."
        else:
            message = f"Erro ao consultar CNPJ. Código HTTP: {exc.code}."

        return JsonResponse(
            {
                "ok": False,
                "message": message,
            },
            status=exc.code if exc.code in [400, 404, 429] else 502,
        )

    except URLError:
        return JsonResponse(
            {
                "ok": False,
                "message": "Não foi possível conectar à BrasilAPI agora.",
            },
            status=502,
        )

    except Exception as exc:
        return JsonResponse(
            {
                "ok": False,
                "message": f"Erro inesperado ao consultar CNPJ: {exc}",
            },
            status=500,
        )


@permission_required("Clientes")
def index(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    clientes = Cliente.objects.all()

    if q:
        clientes = clientes.filter(
            Q(nome__icontains=q)
            | Q(documento__icontains=q)
            | Q(email__icontains=q)
            | Q(telefone__icontains=q)
            | Q(whatsapp__icontains=q)
            | Q(cidade__icontains=q)
        )

    if status:
        clientes = clientes.filter(status=status)

    status_options = ["Ativo", "Prospecto", "Inativo", "Bloqueado"]

    paginator = Paginator(clientes, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    total_clientes = Cliente.objects.count()
    total_ativos = Cliente.objects.filter(status="Ativo").count()
    total_prospectos = Cliente.objects.filter(status="Prospecto").count()
    total_bloqueados = Cliente.objects.filter(status="Bloqueado").count()

    context = {
        "page_obj": page_obj,
        "q": q,
        "status": status,
        "status_options": status_options,
        "total_clientes": total_clientes,
        "total_ativos": total_ativos,
        "total_prospectos": total_prospectos,
        "total_bloqueados": total_bloqueados,
        "page_title": "Clientes",
    }

    return render(request, "clientes/index.html", context)


@permission_required("Clientes", "pode_criar")
def create(request):
    form = ClienteForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        app_user_id = _get_app_user_id(request)

        if app_user_id:
            obj.criado_por_id = app_user_id
            obj.atualizado_por_id = app_user_id

        obj.save()

        log_action(
            request,
            "clientes",
            "criar",
            "cliente",
            obj.id,
            "Cliente criado",
        )

        messages.success(request, "Cliente cadastrado com sucesso.")
        return redirect("clientes:detail", pk=obj.pk)

    return render(
        request,
        "clientes/form.html",
        {
            "form": form,
            "page_title": "Novo Cliente",
            "cnpj_lookup_url": "clientes:buscar_cnpj",
        },
    )


@permission_required("Clientes")
def detail(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    orcamentos = (
        cliente.orcamentos
        .all()
        .order_by("-created_at")[:10]
    )

    resumo_orcamentos = cliente.orcamentos.aggregate(
        total=Count("id"),
        valor_total=Sum("valor_final"),
    )

    context = {
        "cliente": cliente,
        "orcamentos": orcamentos,
        "resumo_orcamentos": resumo_orcamentos,
        "page_title": cliente.nome,
    }

    return render(request, "clientes/detail.html", context)


@permission_required("Clientes", "pode_editar")
def update(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    form = ClienteForm(request.POST or None, instance=cliente)

    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        app_user_id = _get_app_user_id(request)

        if app_user_id:
            obj.atualizado_por_id = app_user_id

        obj.save()

        log_action(
            request,
            "clientes",
            "editar",
            "cliente",
            obj.id,
            "Cliente atualizado",
        )

        messages.success(request, "Cliente atualizado com sucesso.")
        return redirect("clientes:detail", pk=obj.pk)

    return render(
        request,
        "clientes/form.html",
        {
            "form": form,
            "cliente": cliente,
            "page_title": "Editar Cliente",
            "cnpj_lookup_url": "clientes:buscar_cnpj",
        },
    )


@permission_required("Clientes", "pode_excluir")
def delete(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "POST":
        cliente.delete()

        log_action(
            request,
            "clientes",
            "excluir",
            "cliente",
            pk,
            "Cliente excluído",
        )

        messages.success(request, "Cliente excluído com sucesso.")
        return redirect("clientes:index")

    return render(
        request,
        "common/confirm_delete.html",
        {
            "object": cliente,
            "cancel_url": "clientes:detail",
            "page_title": "Excluir Cliente",
        },
    )