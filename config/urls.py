# =============================================================================
# Project-level URL configuration.
# Mounts Django admin and delegates everything under /wizard/ to the accounts
# app's URLconf which implements the multi-step merge wizard.
# =============================================================================
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("wizard/", include("accounts.urls")),
    # Convenience redirect so visiting "/" lands on the wizard.
    path("", RedirectView.as_view(url="/wizard/", permanent=False)),
]
