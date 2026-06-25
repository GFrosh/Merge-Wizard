# Duplicate Account Merge Wizard

A Django app that lets an administrator merge two duplicate user accounts
through a 3-step wizard.

## Features

1. **Step 1 — Select accounts.** Searchable dropdowns for source/target,
   with cross-field validation rejecting `source == target`.
2. **Step 2 — Resolve conflicts.** Auto-resolves fields where one side is
   empty; surfaces only the genuinely conflicting fields to the admin as
   radio choices.
3. **Step 3 — Confirm & merge.** Shows the final summary (chosen values +
   number of related records). The "Confirm Merge" button runs the merge
   inside `transaction.atomic()`, so any failure rolls back fully.

## Project Layout

```
merge_wizard/
├── config/                  # Django project (settings, root urls)
├── accounts/
│   ├── models.py            # Custom User + Post (related model)
│   ├── forms.py             # Step 1 & 2 forms
│   ├── services.py          # Atomic merge logic (the core)
│   ├── views.py             # 3 wizard views + done page
│   ├── urls.py              # /wizard/, /resolve/, /confirm/, /done/
│   ├── admin.py             # Admin registration for fixture data
│   ├── templates/accounts/  # base.html + one per step + done
│   └── tests.py             # All required tests
├── manage.py
├── requirements.txt
└── README.md
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser   # for /admin/ to create fixture users
python manage.py runserver
```

Then visit **<http://127.0.0.1:8000/wizard/>** (you must be logged in as a
staff user — `staff_member_required` gates every wizard view).

## Run the tests

```bash
python manage.py test accounts -v 2
```

The suite covers:

| # | Scenario                          | Test class                    |
|---|-----------------------------------|-------------------------------|
| 1 | Successful merge (service + HTTP) | `SuccessfulMergeTests`        |
| 2 | Same-user validation              | `SameUserValidationTests`     |
| 3 | Transaction rollback on failure   | `TransactionRollbackTests`    |

## Design notes

* **Service layer (`services.py`)** keeps the merge logic out of views so
  it's testable and reusable from a Celery task / management command.
* **`@transaction.atomic`** wraps the whole merge: field updates, related
  record reassignment, and source deletion all commit together or not at
  all.
* **Auto-resolution rule:** if a field is empty on one side and populated
  on the other, the populated value wins automatically — the admin only
  has to make a decision on truly conflicting non-empty values.
* **Whitelist on writes:** the service only applies resolutions for fields
  listed in `User.MERGEABLE_FIELDS`, so a malicious or buggy caller can't
  pivot the merge into a privilege-escalation vector.
