from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import permission_required
from apps.core.models import AgendaEvento, Orcamento
from .forms import AgendaEventoForm
from .services import AgendaService


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@permission_required("Agenda")
def index(request):
    hoje = timezone.localdate()

    selected_orcamento_id = request.GET.get("orcamento")

    eventos = list(AgendaService.eventos_queryset()[:300])
    orcamento_selecionado = AgendaService.buscar_orcamento(selected_orcamento_id)

    if orcamento_selecionado and orcamento_selecionado.data_inicio:
        default_year = orcamento_selecionado.data_inicio.year
        default_month = orcamento_selecionado.data_inicio.month
    else:
        default_year = hoje.year
        default_month = hoje.month

    year = _to_int(request.GET.get("year"), default_year)
    month = _to_int(request.GET.get("month"), default_month)

    if month < 1 or month > 12:
        month = hoje.month

    calendar_weeks = AgendaService.montar_calendario(
        year=year,
        month=month,
        eventos=eventos,
    )

    previous_month = AgendaService.previous_month(year, month)
    next_month = AgendaService.next_month(year, month)

    return render(
        request,
        "agenda/index.html",
        {
            "eventos": eventos,
            "orcamento_selecionado": orcamento_selecionado,
            "calendar_weeks": calendar_weeks,
            "month": month,
            "year": year,
            "month_name": AgendaService.month_name(month),
            "previous_month": previous_month,
            "next_month": next_month,
            "today": hoje,
            "page_title": "Agenda",
        },
    )


@permission_required("Agenda", "pode_criar")
def create(request):
    form = AgendaEventoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Evento criado na agenda.")
        return redirect("agenda:index")

    return render(
        request,
        "agenda/form.html",
        {
            "form": form,
            "page_title": "Novo Evento",
        },
    )


@permission_required("Agenda")
def baixar_relacao_evento(request, orcamento_id):
    orcamento = get_object_or_404(
        Orcamento.objects
        .select_related("cliente")
        .prefetch_related(
            "ambientes__itens__estoque_vinculos",
            "itens__estoque_vinculos",
        ),
        pk=orcamento_id,
    )

    pdf = AgendaService.gerar_pdf_relacao_evento(orcamento)

    filename = f"relacao_evento_{orcamento.codigo}.pdf"

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


@permission_required("Agenda")
def eventos_json(request):
    eventos = []

    for o in AgendaService.eventos_queryset()[:500]:
        eventos.append(
            {
                "id": str(o.id),
                "title": o.evento_nome,
                "start": o.data_inicio.isoformat() if o.data_inicio else None,
                "end": o.data_fim.isoformat() if o.data_fim else (o.data_inicio.isoformat() if o.data_inicio else None),
                "status": o.status,
                "tipo": "Evento",
                "codigo": o.codigo,
            }
        )

    return JsonResponse(eventos, safe=False)