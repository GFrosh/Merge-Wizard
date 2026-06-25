# =============================================================================
# Django admin registration.
# Registers User and Post so an administrator can quickly create fixture data
# to play with the merge wizard in a browser.
# =============================================================================
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Post, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Expose the extra profile fields in the admin edit form.
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Extra profile", {"fields": ("phone_number", "address")}),
    )
    list_display = (
        "username", "email", "first_name", "last_name",
        "phone_number", "is_staff",
    )


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at")
    search_fields = ("title", "author__username")
