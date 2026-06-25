# =============================================================================
# Wizard views.
#
# The three steps are implemented as three function-based views that share
# state through the request's session under the key WIZARD_SESSION_KEY:
#
#     request.session[WIZARD_SESSION_KEY] = {
#         "source_id": <int>,
#         "target_id": <int>,
#         "resolutions": {"email": "...", "phone_number": "...", ...},
#     }
#
# Why the session and not query params? The conflict-resolution step can carry
# arbitrary user-provided values that we don't want round-tripping through the
# URL. The session is server-side, signed, and cleared on success.
#
# Access control:
#   Only staff users are allowed to use the wizard (`staff_member_required`).
#   In production you'd likely add a more specific permission.
# =============================================================================
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ConflictResolutionForm, SelectAccountsForm
from .models import User
from .services import compute_conflicts, count_related_records, merge_users

WIZARD_SESSION_KEY = "merge_wizard_state"


def _get_state(request) -> dict:
    """Return (and lazily initialise) the wizard's session-backed state dict."""
    return request.session.setdefault(WIZARD_SESSION_KEY, {})


def _clear_state(request) -> None:
    """Wipe wizard state — called after success or when the admin restarts."""
    request.session.pop(WIZARD_SESSION_KEY, None)


# -----------------------------------------------------------------------------
# Step 1 — Select source and target accounts
# -----------------------------------------------------------------------------
@staff_member_required
def step1_select(request):
    """Render and process the source/target selection form."""
    # Starting a new wizard run always wipes any stale state from a prior run.
    if request.method == "GET":
        _clear_state(request)

    if request.method == "POST":
        form = SelectAccountsForm(request.POST)
        if form.is_valid():
            source = form.cleaned_data["source"]
            target = form.cleaned_data["target"]
            # Persist selection for the next step.
            request.session[WIZARD_SESSION_KEY] = {
                "source_id": source.pk,
                "target_id": target.pk,
                "resolutions": {},
            }
            return redirect(reverse("accounts:step2"))
    else:
        form = SelectAccountsForm()

    return render(request, "accounts/step1_select.html", {"form": form})


# -----------------------------------------------------------------------------
# Step 2 — Conflict resolution
# -----------------------------------------------------------------------------
@staff_member_required
def step2_resolve(request):
    """Render conflicting fields, capture admin choices, store resolutions."""
    state = _get_state(request)
    if not state.get("source_id") or not state.get("target_id"):
        # User skipped step 1 — bounce them back.
        messages.warning(request, "Please pick the two accounts to merge first.")
        return redirect(reverse("accounts:step1"))

    source = get_object_or_404(User, pk=state["source_id"])
    target = get_object_or_404(User, pk=state["target_id"])

    # Figure out which fields conflict (and which are auto-resolved).
    conflicts = compute_conflicts(source, target)
    manual_conflicts = [c for c in conflicts if not c["auto"]]
    auto_resolutions = {c["name"]: c["auto_value"] for c in conflicts if c["auto"]}

    if request.method == "POST":
        form = ConflictResolutionForm(request.POST, conflicts=manual_conflicts)
        if form.is_valid():
            # Translate the radio "source"/"target" choice into the actual value.
            resolutions = dict(auto_resolutions)  # start with auto picks
            for c in manual_conflicts:
                choice = form.cleaned_data[f"choice_{c['name']}"]
                resolutions[c["name"]] = c[choice]  # c["source"] or c["target"]

            state["resolutions"] = resolutions
            # Session is mutable but we changed a nested dict; flag it dirty.
            request.session.modified = True
            return redirect(reverse("accounts:step3"))
    else:
        form = ConflictResolutionForm(conflicts=manual_conflicts)

    return render(
        request,
        "accounts/step2_resolve.html",
        {
            "form": form,
            "source": source,
            "target": target,
            "manual_conflicts": manual_conflicts,
            "auto_resolutions": auto_resolutions,
        },
    )


# -----------------------------------------------------------------------------
# Step 3 — Confirmation + perform the actual merge
# -----------------------------------------------------------------------------
@staff_member_required
def step3_confirm(request):
    """Show a summary and, on POST, atomically execute the merge."""
    state = _get_state(request)
    if not state.get("source_id") or not state.get("target_id"):
        messages.warning(request, "Wizard state is missing; please start over.")
        return redirect(reverse("accounts:step1"))

    source = get_object_or_404(User, pk=state["source_id"])
    target = get_object_or_404(User, pk=state["target_id"])
    resolutions: dict = state.get("resolutions", {})
    related_counts = count_related_records(source)

    if request.method == "POST":
        try:
            merge_users(source, target, resolutions)
        except Exception as exc:  # noqa: BLE001 - we want to surface anything
            # `merge_users` is wrapped in transaction.atomic(); any exception
            # from inside it has already triggered a full rollback. We just
            # need to inform the admin.
            messages.error(request, f"Merge failed and was rolled back: {exc}")
            return redirect(reverse("accounts:step1"))

        _clear_state(request)
        messages.success(
            request,
            f"Successfully merged '{source}' into '{target}'.",
        )
        return redirect(reverse("accounts:done"))

    return render(
        request,
        "accounts/step3_confirm.html",
        {
            "source": source,
            "target": target,
            "resolutions": resolutions,
            "related_counts": related_counts,
        },
    )


# -----------------------------------------------------------------------------
# Final "done" page — pure GET, nothing to process.
# -----------------------------------------------------------------------------
@staff_member_required
def done(request):
    return render(request, "accounts/done.html")
