"""Account details: the identifier that goes with each kind of account.

An M-PESA account is a phone line, a bank account is a bank plus a number, and
neither statement means LifeSmart can see inside it. These tests hold the two
halves of that: the number must be recorded accurately (or the request is
rejected), and the app must still describe the account as unverified.

The second half of the file covers correcting an account that already exists.
Before that, a mistake was permanent: an account typed in as M-PESA when it was
really a bank stayed wrong forever, and two rows named the same looked
identical in every picker with no way to tell them apart.
"""
import io
import csv
import zipfile

import pytest
import sqlalchemy as sa

from app.core.database import Base
from app.core.schema_compat import apply_missing_columns
from app.schemas.finance import normalize_mpesa_number


def _create(client, headers, **body):
    body.setdefault("name", "Account")
    body.setdefault("type", "cash")
    return client.post("/api/accounts", json=body, headers=headers)


def _get(client, headers, account_id):
    accounts = client.get("/api/accounts", headers=headers).json()
    return next(a for a in accounts if a["id"] == account_id)


def _patch(client, headers, account_id, **body):
    return client.patch(f"/api/accounts/{account_id}", json=body, headers=headers)


@pytest.mark.parametrize(
    "typed",
    ["0712 345 678", "0712-345-678", "0712345678", "+254712345678", "254712345678"],
)
def test_mpesa_number_is_stored_in_one_shape(typed):
    """However it is written down, it is kept as one canonical form."""
    assert normalize_mpesa_number(typed) == "+254712345678"


def test_mshwari_shares_the_line_and_is_kept_the_same_way():
    assert normalize_mpesa_number("0112 345 678") == "+254112345678"


@pytest.mark.parametrize("typed", ["0412345678", "071234567", "9712345678", "07123456789"])
def test_unrecognised_phone_shapes_are_refused(typed):
    with pytest.raises(ValueError):
        normalize_mpesa_number(typed)


def test_mpesa_account_requires_its_number(client, auth_headers):
    missing = _create(client, auth_headers, name="M-PESA", type="mpesa")
    assert missing.status_code == 422

    created = _create(client, auth_headers, name="M-PESA", type="mpesa",
                      mpesa_number="0712 345 678")
    assert created.status_code == 201
    acct = created.json()
    assert acct["mpesa_number"] == "+254712345678"
    assert acct["bank_name"] is None and acct["account_number"] is None
    # A number the person typed identifies the account. It connects to nothing.
    assert acct["is_synced"] is False


def test_mshwari_account_also_carries_the_line(client, auth_headers):
    created = _create(client, auth_headers, name="M-Shwari", type="mshwari",
                      mpesa_number="+254712345678", balance_minor=45000)
    assert created.status_code == 201
    acct = created.json()
    assert acct["type"] == "mshwari"
    assert acct["mpesa_number"] == "+254712345678"
    assert acct["initialized"] is True
    assert acct["balance_minor"] == 45000


def test_wallet_and_mshwari_stay_separate_pockets(client, auth_headers):
    """Why M-Shwari is its own row: money moving in one is not moving in the
    other, even though both live on the same phone number."""
    wallet = _create(client, auth_headers, name="M-PESA", type="mpesa",
                     mpesa_number="0712345678", balance_minor=100000).json()
    savings = _create(client, auth_headers, name="M-Shwari", type="mshwari",
                      mpesa_number="0712345678", balance_minor=500000).json()

    spend = client.post("/api/transactions", json={
        "type": "expense", "amount_minor": 40000, "account_id": wallet["id"],
        "occurred_on": "2026-10-20", "description": "chapati",
    }, headers=auth_headers)
    assert spend.status_code in (200, 201)

    assert _get(client, auth_headers, wallet["id"])["balance_minor"] == 60000
    assert _get(client, auth_headers, savings["id"])["balance_minor"] == 500000


def test_bank_account_needs_a_bank_and_a_number(client, auth_headers):
    no_bank = _create(client, auth_headers, name="SACCO", type="bank",
                      account_number="011004567890")
    assert no_bank.status_code == 422

    no_number = _create(client, auth_headers, name="Equity", type="bank",
                        bank_name="Equity")
    assert no_number.status_code == 422

    created = _create(client, auth_headers, name="Equity", type="bank",
                      bank_name="Equity Bank", account_number="0110 0456 7890",
                      balance_minor=12500000)
    assert created.status_code == 201
    acct = created.json()
    assert acct["bank_name"] == "Equity Bank"
    assert acct["account_number"] == "011004567890"  # spaces are not part of it
    assert acct["mpesa_number"] is None
    assert acct["balance_minor"] == 12500000


def test_details_for_a_type_that_has_none_are_not_stored(client, auth_headers):
    """A cash wallet has no phone number. Whatever a caller sent, nothing
    misleading is recorded against it."""
    created = _create(client, auth_headers, name="Pocket cash", type="cash",
                      mpesa_number="0712345678", bank_name="Equity",
                      account_number="011004567890")
    assert created.status_code == 201
    acct = created.json()
    assert acct["mpesa_number"] is None
    assert acct["bank_name"] is None
    assert acct["account_number"] is None


def test_balance_left_out_stays_unknown(client, auth_headers):
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678").json()
    assert acct["initialized"] is False
    assert acct["balance_minor"] is None  # never filled in as zero

    # It can be set later, which is what the Initialize control is for.
    later = client.post(f"/api/accounts/{acct['id']}/initialize",
                        json={"balance_minor": 9900}, headers=auth_headers).json()
    assert later["balance_minor"] == 9900
    assert later["mpesa_number"] == "+254712345678"


def test_account_details_appear_in_the_export(client, auth_headers):
    """Export is built from the model, so a recorded number travels with the
    person's other data - and nothing else does."""
    _create(client, auth_headers, name="Equity", type="bank", bank_name="Equity",
            account_number="011004567890", balance_minor=500000)

    resp = client.get("/api/account/export", headers=auth_headers)
    assert resp.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    rows = list(csv.DictReader(io.StringIO(archive.read("csv/accounts.csv").decode())))
    bank = next(r for r in rows if r["type"] == "bank")
    assert bank["bank_name"] == "Equity"
    assert bank["account_number"] == "011004567890"
    assert bank["mpesa_number"] == ""


def test_a_database_from_before_the_columns_still_opens(tmp_path):
    """The desktop launcher builds its schema with create_all, which never
    alters a table that already exists. An install made before these columns
    were added must still start, and must keep the rows it already has."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, user_id INTEGER NOT "
            "NULL, name VARCHAR(120) NOT NULL, type VARCHAR(6) NOT NULL, "
            "is_synced BOOLEAN NOT NULL, initialized BOOLEAN NOT NULL, "
            "initial_balance_minor BIGINT NOT NULL, created_at DATETIME NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO accounts VALUES (1, 1, 'M-PESA', 'mpesa', 0, 1, 12000, "
            "'2026-10-01 00:00:00')"
        )

    added = apply_missing_columns(engine, Base)

    assert set(added) == {"accounts.mpesa_number", "accounts.bank_name",
                          "accounts.account_number"}
    columns = {c["name"]: c for c in sa.inspect(engine).get_columns("accounts")}
    # Nullable, so an old row reads as "never recorded" rather than as blank.
    for key in ("mpesa_number", "bank_name", "account_number"):
        assert columns[key]["nullable"] is True
    with engine.connect() as conn:
        row = conn.exec_driver_sql("SELECT type, mpesa_number FROM accounts").one()
    assert row[0] == "mpesa" and row[1] is None
    # Running it again changes nothing.
    assert apply_missing_columns(engine, Base) == []


def test_a_duplicate_mpesa_row_can_be_corrected_into_a_bank(client, auth_headers):
    """The mistake this exists for: an account added as M-PESA that is a bank."""
    acct = _create(client, auth_headers, name="mpesa", type="mpesa",
                   mpesa_number="0712345678", balance_minor=250000).json()

    fixed = _patch(client, auth_headers, acct["id"], name="Equity",
                   type="bank", bank_name="Equity Bank",
                   account_number="0110 0456 7890")
    assert fixed.status_code == 200
    out = fixed.json()
    assert out["name"] == "Equity" and out["type"] == "bank"
    assert out["bank_name"] == "Equity Bank"
    assert out["account_number"] == "011004567890"
    # A bank account does not hold an M-PESA number, so the old one is gone
    # rather than sitting there contradicting the kind.
    assert out["mpesa_number"] is None
    assert out["balance_minor"] == 250000


def test_editing_an_account_leaves_the_money_where_it_was(client, auth_headers):
    """Balances come from the initial figure plus the transactions naming the
    account, so changing the kind cannot move a pesa or drop a record."""
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678", balance_minor=100000).json()
    spend = client.post("/api/transactions", json={
        "type": "expense", "amount_minor": 30000, "account_id": acct["id"],
        "occurred_on": "2026-10-20", "description": "bata",
    }, headers=auth_headers).json()

    _patch(client, auth_headers, acct["id"], type="wallet", name="Shop wallet")

    now = _get(client, auth_headers, acct["id"])
    assert now["id"] == acct["id"]
    assert now["balance_minor"] == 70000
    listed = client.get("/api/transactions", params={"page_size": 10},
                        headers=auth_headers).json()["transactions"]
    assert [t["id"] for t in listed] == [spend["id"]]


def test_leaving_a_field_out_keeps_what_was_stored(client, auth_headers):
    """Renaming must not ask for the phone number back, and must not lose it."""
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678").json()

    out = _patch(client, auth_headers, acct["id"], name="My M-PESA").json()

    assert out["name"] == "My M-PESA"
    assert out["type"] == "mpesa"
    assert out["mpesa_number"] == "+254712345678"


def test_switching_kind_demands_what_the_new_kind_needs(client, auth_headers):
    """A bank account with no bank behind it is nothing to record, and the
    failed edit must leave the account exactly as it was."""
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678", balance_minor=50000).json()

    refused = _patch(client, auth_headers, acct["id"], type="bank")
    assert refused.status_code == 422
    assert "bank" in refused.json()["detail"].lower()

    still = _get(client, auth_headers, acct["id"])
    assert still["type"] == "mpesa"
    assert still["mpesa_number"] == "+254712345678"
    assert still["balance_minor"] == 50000


def test_a_number_typed_over_another_is_still_judged(client, auth_headers):
    """Blank and malformed are rejected, not quietly ignored in favour of the
    stored value - otherwise the person believes a change took place."""
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678").json()

    blank = _patch(client, auth_headers, acct["id"], mpesa_number="")
    assert blank.status_code == 422
    malformed = _patch(client, auth_headers, acct["id"], mpesa_number="0412345678")
    assert malformed.status_code == 422

    assert _get(client, auth_headers, acct["id"])["mpesa_number"] == "+254712345678"

    corrected = _patch(client, auth_headers, acct["id"], mpesa_number="0115 222 333")
    assert corrected.status_code == 200
    assert corrected.json()["mpesa_number"] == "+254115222333"


def test_editing_never_claims_a_connection(client, auth_headers):
    acct = _create(client, auth_headers, name="M-PESA", type="mpesa",
                   mpesa_number="0712345678").json()

    out = _patch(client, auth_headers, acct["id"], type="mshwari",
                 mpesa_number="+254712345678").json()

    assert out["type"] == "mshwari"
    assert out["is_synced"] is False


def test_someone_elses_account_cannot_be_edited(client, auth_headers,
                                                 second_user_headers):
    acct = _create(client, auth_headers, name="Pocket cash", type="cash").json()

    refused = _patch(client, second_user_headers, acct["id"], name="Mine now",
                     type="cash")
    assert refused.status_code == 404
    assert _get(client, auth_headers, acct["id"])["name"] == "Pocket cash"
