# =============================================================================
# Data Models
#
# We define:
#   1. A custom `User` model that extends Django's `AbstractUser`. Extending
#      AbstractUser gives us all the built-in auth fields (username, email,
#      password, is_staff, ...) plus extra profile-style columns (phone,
#      address) that are realistic targets for conflict resolution when merging
#      two duplicate accounts.
#
#   2. A `Post` model with a ForeignKey to User. This is the "related record"
#      the wizard reassigns from the source user to the target user during a
#      merge. In a real system there might be many such related models
#      (Orders, Comments, Tickets, ...); the merge logic uses the same
#      pattern for all of them.
# =============================================================================
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with extra profile fields used by the merge wizard.

    These extra fields are the ones the wizard's "Conflict Resolution" step
    compares between the two accounts.
    """

    # Extra fields beyond AbstractUser's username/email/first_name/last_name.
    phone_number = models.CharField(max_length=32, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")

    # Fields whose values are compared and resolved during a merge.
    # Centralising this list keeps the wizard, forms and templates in sync.
    MERGEABLE_FIELDS = [
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "address",
    ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        # A friendly identifier for admin dropdowns.
        full = self.get_full_name()
        return f"{self.username} ({full or self.email or 'no name'})"


class Post(models.Model):
    """A simple content record owned by a User.

    During a merge, every Post whose `author` points at the source user is
    reassigned to the target user before the source user is deleted.
    """

    title = models.CharField(max_length=200)
    content = models.TextField(blank=True, default="")
    # related_name="posts" lets us write `user.posts.all()` and, crucially,
    # `user.posts.update(author=target)` for bulk reassignment during merge.
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="posts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.title
