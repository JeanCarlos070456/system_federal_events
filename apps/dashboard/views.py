from __future__ import annotations

from django.shortcuts import render

from apps.accounts.decorators import permission_required
from .services import DashboardService


@permission_required("Dashboard")
def index(request):
    context = DashboardService.get_context()
    context["page_title"] = "Dashboard"

    return render(request, "dashboard/index.html", context)
