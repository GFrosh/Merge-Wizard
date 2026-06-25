# =============================================================================
# URL routes for the merge wizard.
# Mounted under /wizard/ by config/urls.py, so the full paths are:
#   /wizard/             -> step 1 (select accounts)
#   /wizard/resolve/     -> step 2 (conflict resolution)
#   /wizard/confirm/     -> step 3 (confirmation + merge)
#   /wizard/done/        -> success page
# =============================================================================
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.step1_select, name="step1"),
    path("resolve/", views.step2_resolve, name="step2"),
    path("confirm/", views.step3_confirm, name="step3"),
    path("done/", views.done, name="done"),
]
