# =============================================================================
# Merge service layer.
#
# Keeping the actual merge logic out of the view makes it:
#   * trivially unit-testable without HTTP plumbing,
#   * reusable from a management command, Celery task, DRF endpoint, etc.,
#   * easier to reason about for atomicity.
#
# The single public entry point is `merge_users(source, target, resolutions)`.
# It must always run inside `transaction.atomic()` so that any failure
# (database error, business-rule error, signal handler exception, ...)
# rolls back the *entire* merge — no orphaned posts, no half-deleted user.
# =============================================================================
from __future__ import annotations

from typing import Dict

from django.db import transaction

from .models import Post, User


def compute_conflicts(source: User, target: User) -> list[dict]:
    """Return the list of fields the admin actually needs to resolve.

    Rules:
      * If both sides hold the same value -> no conflict, skip.
      * If exactly one side is empty -> auto-resolve to the populated value;
        we *don't* surface this to the admin (the spec calls for this).
      * If both sides hold different non-empty values -> conflict; the admin
        must pick one in Step 2.

    The function returns two pieces of information bundled into one list of
    dicts so the caller can both render the form and apply auto-resolutions:

        [
          {"name": "email", "source": "...", "target": "...",
           "auto": False, "auto_value": None},
          ...
        ]
    """
    conflicts = []
    for field in User.MERGEABLE_FIELDS:
        s_val = getattr(source, field) or ""
        t_val = getattr(target, field) or ""

        if s_val == t_val:
            continue  # nothing to resolve

        if not s_val or not t_val:
            # Exactly one side is empty -> auto pick the populated one.
            conflicts.append({
                "name": field,
                "source": s_val,
                "target": t_val,
                "auto": True,
                "auto_value": s_val or t_val,
            })
        else:
            # Genuine conflict -> needs admin input.
            conflicts.append({
                "name": field,
                "source": s_val,
                "target": t_val,
                "auto": False,
                "auto_value": None,
            })
    return conflicts


def count_related_records(user: User) -> Dict[str, int]:
    """Return a small dict of {related_model_label: count} for the UI.

    Extend this when you add more related models. Keeping it centralised means
    the confirmation page automatically picks up new tables.
    """
    return {
        "posts": Post.objects.filter(author=user).count(),
    }


@transaction.atomic
def merge_users(source: User, target: User, resolutions: Dict[str, str]) -> User:
    """Merge `source` into `target` atomically.

    Parameters
    ----------
    source : User
        The duplicate account that will be absorbed and deleted.
    target : User
        The account that survives.
    resolutions : dict[str, str]
        Mapping of mergeable field name -> final value to write on `target`.
        Callers (the view) are responsible for already having applied
        auto-resolutions and the admin's manual choices into this dict.

    Returns
    -------
    User
        The refreshed surviving target user.

    Raises
    ------
    ValueError
        If source and target are the same user. The `@transaction.atomic`
        decorator guarantees that if this — or any DB error below — is raised
        the whole operation rolls back.
    """
    # ---- Guard rails ------------------------------------------------------
    if source.pk == target.pk:
        # This *should* have been caught by the form, but defending in depth
        # here means the service can be safely called from anywhere.
        raise ValueError("Cannot merge a user with themselves.")

    # ---- 1. Apply field resolutions to the surviving user -----------------
    # Only allow writing to whitelisted fields to avoid accidental privilege
    # escalation if `resolutions` ever came from an untrusted source.
    for field, value in resolutions.items():
        if field in User.MERGEABLE_FIELDS:
            setattr(target, field, value)
    target.save()

    # ---- 2. Reassign related records --------------------------------------
    # Using QuerySet.update() issues a single UPDATE per related table, which
    # is both fast and atomic. For each *new* related model in the system,
    # add a similar line here (or iterate over `source._meta.related_objects`
    # generically — kept explicit for clarity in this educational example).
    Post.objects.filter(author=source).update(author=target)

    # ---- 3. Delete the source user ----------------------------------------
    # Because we already moved the posts off `source`, the cascading delete
    # has nothing left to cascade to.
    source.delete()

    # ---- 4. Return the freshened survivor ---------------------------------
    target.refresh_from_db()
    return target
