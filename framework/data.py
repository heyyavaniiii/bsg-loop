"""Synthetic banking data (Faker, Indian locale).

Everything generated here is fake. KYC identifiers follow the *format* of Indian IDs
(e.g. PAN: AAAAA9999A) but are random strings, never real identity numbers.
Run `python -m framework.data` to export a CSV feed to dashboard/.
"""
import csv
import random
import string
import time
from datetime import date

from faker import Faker

from framework.config import DASHBOARD, SEED

_INCOME_BANDS = ["<3L", "3-6L", "6-12L", "12-25L", "25L+"]
_ADDRESS_PROOFS = ["Utility bill", "Rental agreement", "Passport", "Voter ID"]


def _faker(offset: int = 0) -> Faker:
    f = Faker("en_IN")
    f.seed_instance(SEED + offset)
    return f


def pan_like(rng: random.Random) -> str:
    """Random string in PAN *format* (5 letters, 4 digits, 1 letter). Not a real PAN."""
    letters = string.ascii_uppercase
    return "".join(rng.choices(letters, k=3)) + "P" + rng.choice(letters) + "".join(rng.choices(string.digits, k=4)) + rng.choice(letters)


def ifsc_like(rng: random.Random) -> str:
    return "".join(rng.choices(string.ascii_uppercase, k=4)) + "0" + "".join(rng.choices(string.digits, k=6))


def customer(offset: int = 0) -> dict:
    """One synthetic customer incl. KYC fields. Deterministic per (SEED, offset) except the username suffix,
    which is time-based because ParaBank usernames must be unique across all users of the public demo."""
    f = _faker(offset)
    rng = random.Random(SEED + offset)
    first, last = f.first_name(), f.last_name()
    suffix = int(time.time() * 1000) % 10**8
    return {
        "first_name": first,
        "last_name": last,
        "street": f.street_address().replace("\n", " "),
        "city": f.city(),
        "state": f.state(),
        "zip": f.postcode(),
        "phone": f"9{rng.randint(10**8, 10**9 - 1)}",
        "kyc_id": pan_like(rng),
        "username": f"{first.lower()}{last.lower()}{suffix}"[:30],
        "password": f"Pw@{rng.randint(10**5, 10**6 - 1)}",
        # KYC fields beyond what ParaBank's form needs (used by the CSV feed / dashboards)
        "dob": f.date_of_birth(minimum_age=18, maximum_age=70).isoformat(),
        "occupation": f.job(),
        "income_band": rng.choice(_INCOME_BANDS),
        "address_proof": rng.choice(_ADDRESS_PROOFS),
        "pan_like": pan_like(rng),
        "ifsc_like": ifsc_like(rng),
        "upi_id": f"{first.lower()}{rng.randint(10, 99)}@examplebank",
    }


def payee(offset: int = 0) -> dict:
    f = _faker(1000 + offset)
    rng = random.Random(SEED + 1000 + offset)
    return {
        "name": f.company()[:40],
        "street": f.street_address().replace("\n", " "),
        "city": f.city(),
        "state": f.state(),
        "zip": f.postcode(),
        "phone": f"9{rng.randint(10**8, 10**9 - 1)}",
        "account":str(rng.randint(10**7, 10**8 - 1)),
    }


def card_number(offset: int = 0) -> str:
    """Luhn-valid synthetic card number (Faker)."""
    return _faker(2000 + offset).credit_card_number()


def transactions(n: int = 50, offset: int = 0) -> list[dict]:
    f = _faker(3000 + offset)
    rng = random.Random(SEED + 3000 + offset)
    kinds = ["TRANSFER", "BILL_PAY", "UPI", "CARD_POS", "ATM"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "txn_id": f"T{SEED}{offset:03d}{i:05d}",
                "date": f.date_between(start_date=date(2026, 1, 1), end_date=date(2026, 10, 1)).isoformat(),
                "type": rng.choice(kinds),
                "amount_inr": round(rng.uniform(1, 50000), 2),
                "card_last4": card_number(i)[-4:],
            }
        )
    return rows


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    custs = [customer(i) for i in range(25)]
    for c in custs:
        c.pop("password")
    _write(DASHBOARD / "synthetic_customers.csv", custs)
    _write(DASHBOARD / "synthetic_transactions.csv", transactions(200))
    print("wrote dashboard/synthetic_customers.csv and dashboard/synthetic_transactions.csv")
