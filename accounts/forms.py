# =============================================================================
# Forms used by the multi-step merge wizard.
#
# Step 1: SelectAccountsForm
#   - Choose source and target user.
#   - Enforces "source != target" at the form level.
#
# Step 2: ConflictResolutionForm (built dynamically)
#   - For each mergeable field where the two users disagree, render a
#     radio-button choice between the source value and the target value.
#   - Fields that don't conflict (either equal, or one side empty) are
#     auto-resolved by the view and not shown to the admin.
#
# Step 3: Confirmation
#   - No form fields needed beyond CSRF; confirmation is a simple POST.
# =============================================================================
from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class SelectAccountsForm(forms.Form):
    """Step 1 form: pick the source (absorbed) and target (surviving) users."""

    source = forms.ModelChoiceField(
        queryset=User.objects.all().order_by("username"),
        label="Source account (will be deleted)",
        help_text="This account's data will be merged into the target and then deleted.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    target = forms.ModelChoiceField(
        queryset=User.objects.all().order_by("username"),
        label="Target account (survives)",
        help_text="This account will receive all data from the source.",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        """Cross-field validation: source and target must differ.

        Doing this in `clean()` (instead of per-field) lets us attach the error
        to the form as a non-field error AND raise a clean ValidationError that
        the tests can assert against.
        """
        cleaned = super().clean()
        source = cleaned.get("source")
        target = cleaned.get("target")
        if source and target and source.pk == target.pk:
            raise forms.ValidationError(
                "Source and target accounts cannot be the same user."
            )
        return cleaned


class ConflictResolutionForm(forms.Form):
    """Step 2 form: dynamically built from the list of *conflicting* fields.

    The view constructs this form by passing in `conflicts`, a list of dicts:
        {"name": "email", "source": "a@x.com", "target": "b@x.com"}

    For each conflict we add a ChoiceField named `choice_<field>` whose value
    is either "source" or "target". The view then maps that back to the actual
    value to write onto the surviving user.
    """

    def __init__(self, *args, conflicts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.conflicts = conflicts or []

        for conflict in self.conflicts:
            field_name = f"choice_{conflict['name']}"
            self.fields[field_name] = forms.ChoiceField(
                label=conflict["name"].replace("_", " ").title(),
                choices=[
                    ("source", f"Source: {conflict['source'] or '(empty)'}"),
                    ("target", f"Target: {conflict['target'] or '(empty)'}"),
                ],
                # Default to keeping the target's value — the target is the
                # surviving account, so this is the safest default.
                initial="target",
                widget=forms.RadioSelect,
            )
