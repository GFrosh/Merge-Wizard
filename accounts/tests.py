# =============================================================================
# Automated tests for the merge wizard.
#
# These cover the three scenarios the spec requires:
#   1. Successful merge: related records transferred, source deleted,
#      target keeps the chosen merged values.
#   2. Same-user validation: choosing the same user for source and target
#      raises ValidationError on the form *and* ValueError in the service.
#   3. Transaction rollback: if the service raises mid-merge, no data is lost
#      and nothing is partially moved.
#
# A few extra tests exercise the conflict-detection helper to lock down the
# "auto-resolve when one side is empty" behaviour required by the spec.
# =============================================================================
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.forms import SelectAccountsForm
from accounts.models import Post
from accounts.services import compute_conflicts, merge_users

User = get_user_model()


class MergeWizardTestsBase(TestCase):
    """Shared fixture: two duplicate-ish users with posts owned by each."""

    def setUp(self):
        # `source` is the duplicate to be absorbed.
        self.source = User.objects.create_user(
            username="alice_old",
            email="alice.old@example.com",
            first_name="Alice",
            last_name="Smith",
            phone_number="+1-555-1111",
            address="",  # intentionally empty -> should auto-resolve
        )
        # `target` is the surviving record.
        self.target = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smithson",      # conflicts with "Smith"
            phone_number="",           # empty -> source value should win automatically
            address="42 Main Street",
        )
        # Two posts on the source must be moved over.
        self.post_a = Post.objects.create(title="A", content="x", author=self.source)
        self.post_b = Post.objects.create(title="B", content="y", author=self.source)
        # And one already on the target, which must remain untouched.
        self.post_c = Post.objects.create(title="C", content="z", author=self.target)


# -----------------------------------------------------------------------------
# 1. Successful merge
# -----------------------------------------------------------------------------
class SuccessfulMergeTests(MergeWizardTestsBase):

    def test_compute_conflicts_auto_resolves_empty_sides(self):
        """Fields where exactly one side is empty get auto-resolved."""
        conflicts = compute_conflicts(self.source, self.target)
        names = {c["name"]: c for c in conflicts}

        # last_name differs and both sides populated -> manual conflict
        self.assertIn("last_name", names)
        self.assertFalse(names["last_name"]["auto"])

        # phone_number: source populated, target empty -> auto pick source.
        self.assertIn("phone_number", names)
        self.assertTrue(names["phone_number"]["auto"])
        self.assertEqual(names["phone_number"]["auto_value"], "+1-555-1111")

        # address: source empty, target populated -> auto pick target.
        self.assertIn("address", names)
        self.assertTrue(names["address"]["auto"])
        self.assertEqual(names["address"]["auto_value"], "42 Main Street")

        # first_name is identical on both sides -> no conflict at all.
        self.assertNotIn("first_name", names)

    def test_merge_transfers_posts_deletes_source_and_applies_resolutions(self):
        """End-to-end successful merge via the service layer."""
        resolutions = {
            "last_name": "Smith",                # admin picks source value
            "email": "alice@example.com",        # keep target email
            "phone_number": "+1-555-1111",       # auto-resolved
            "address": "42 Main Street",         # auto-resolved
        }

        merged = merge_users(self.source, self.target, resolutions)

        # 1. Source user is gone.
        self.assertFalse(User.objects.filter(pk=self.source.pk).exists())

        # 2. Target survives and now owns *all* posts (its own + source's).
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.assertEqual(merged.posts.count(), 3)
        self.assertSetEqual(
            set(merged.posts.values_list("title", flat=True)),
            {"A", "B", "C"},
        )

        # 3. Resolutions are applied on the surviving target.
        self.assertEqual(merged.last_name, "Smith")
        self.assertEqual(merged.phone_number, "+1-555-1111")
        self.assertEqual(merged.address, "42 Main Street")

    def test_full_wizard_flow_via_http(self):
        """Drive the three wizard pages through the test client end-to-end."""
        admin = User.objects.create_superuser(
            username="boss", email="b@x.com", password="pw"
        )
        self.client.force_login(admin)

        # Step 1: pick the two accounts.
        r1 = self.client.post(
            reverse("accounts:step1"),
            {"source": self.source.pk, "target": self.target.pk},
        )
        self.assertRedirects(r1, reverse("accounts:step2"))

        # Step 2: only `last_name` and `email` need manual resolution
        # (phone_number & address are auto). Pick "source" for last_name,
        # "target" for email.
        r2 = self.client.post(
            reverse("accounts:step2"),
            {"choice_last_name": "source", "choice_email": "target"},
        )
        self.assertRedirects(r2, reverse("accounts:step3"))

        # Step 3: confirm.
        r3 = self.client.post(reverse("accounts:step3"))
        self.assertRedirects(r3, reverse("accounts:done"))

        # Verify final state.
        self.assertFalse(User.objects.filter(pk=self.source.pk).exists())
        target = User.objects.get(pk=self.target.pk)
        self.assertEqual(target.last_name, "Smith")
        self.assertEqual(target.email, "alice@example.com")
        self.assertEqual(target.posts.count(), 3)


# -----------------------------------------------------------------------------
# 2. Same-user validation
# -----------------------------------------------------------------------------
class SameUserValidationTests(MergeWizardTestsBase):

    def test_form_rejects_same_source_and_target(self):
        """SelectAccountsForm.clean() must reject identical source/target."""
        form = SelectAccountsForm(
            data={"source": self.source.pk, "target": self.source.pk}
        )
        self.assertFalse(form.is_valid())
        # Error is attached as a non-field error.
        self.assertIn(
            "Source and target accounts cannot be the same user.",
            form.non_field_errors()[0],
        )

    def test_service_rejects_same_source_and_target(self):
        """Defence in depth: the service must also refuse the no-op merge."""
        with self.assertRaises(ValueError):
            merge_users(self.source, self.source, resolutions={})


# -----------------------------------------------------------------------------
# 3. Transaction rollback
# -----------------------------------------------------------------------------
class TransactionRollbackTests(MergeWizardTestsBase):
    """Force an exception mid-merge and assert nothing was persisted."""

    def test_rollback_when_post_reassignment_fails(self):
        # Patch QuerySet.update so the *bulk reassignment* step inside
        # `merge_users` raises. Because the service is wrapped in
        # `@transaction.atomic`, the exception must trigger a full rollback
        # of: (a) the field updates already applied to `target`, and
        # (b) the not-yet-issued source delete.
        from django.db.models.query import QuerySet

        original_update = QuerySet.update

        def boom(self, *args, **kwargs):
            # Only blow up for the Post reassignment call; let other updates
            # (e.g. the target.save() under the hood) proceed normally.
            if self.model is Post:
                raise RuntimeError("simulated DB failure")
            return original_update(self, *args, **kwargs)

        with patch.object(QuerySet, "update", boom):
            with self.assertRaises(RuntimeError):
                merge_users(
                    self.source,
                    self.target,
                    resolutions={"last_name": "Smith"},
                )

        # ---- Assert *nothing* changed ------------------------------------
        # Source user still exists.
        self.assertTrue(User.objects.filter(pk=self.source.pk).exists())

        # Target user is unchanged — the in-memory `self.target` may be
        # stale because we set attributes before save(); reload from DB.
        fresh_target = User.objects.get(pk=self.target.pk)
        self.assertEqual(fresh_target.last_name, "Smithson")  # original

        # Posts haven't moved.
        self.assertEqual(
            set(Post.objects.filter(author=self.source).values_list("title", flat=True)),
            {"A", "B"},
        )
        self.assertEqual(
            set(Post.objects.filter(author=self.target).values_list("title", flat=True)),
            {"C"},
        )
