from __future__ import annotations


def auth_context(request):
    return {
        "app_user": getattr(request, "app_user", None),
        "app_permissions": getattr(request, "app_permissions", {}),
        "nav_items": getattr(request, "app_navigation", []),
    }
