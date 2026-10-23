import pytest
from playwright.sync_api import expect

from framework import data
from framework import parabank as pb

OK = "Bill Payment Complete"


@pytest.mark.sop("Pay a bill to a new payee")
def test_bill_payment_valid(page, rec, banked):
    src = next(iter(pb.balances(page)))
    payee = data.payee(1)
    page.goto(pb.url("billpay.htm"))
    rec.step("Select Bill Pay from the left-hand menu")
    pb.fill_bill(page, src, payee, "15.00")
    rec.step("Enter the payee name, address, phone and account number (twice), the amount and the account to pay from")
    pb.send_payment(page)
    expect(page.locator("#billpayResult")).to_contain_text(OK)
    rec.step("Select Send Payment - a confirmation shows the payee, amount and paying account")


def test_bill_payment_reduces_balance(page, rec, banked):
    src = next(iter(pb.balances(page)))
    before = pb.balances(page)[src]
    pb.fill_bill(page, src, data.payee(2), "20.00")
    pb.send_payment(page)
    expect(page.locator("#billpayResult")).to_contain_text(OK)
    assert round(before - pb.balances(page)[src], 2) == 20.00


@pytest.mark.negative
def test_bill_payment_missing_payee_name(page, rec, banked):
    src = next(iter(pb.balances(page)))
    pb.fill_bill(page, src, data.payee(3), "10.00", blank="payee.name")
    pb.send_payment(page)
    rec.step("Send payment with the payee name blank")
    pb.expect_validation_error(page)
    pb.expect_rejected(page, OK)


@pytest.mark.negative
def test_bill_payment_account_mismatch(page, rec, banked):
    src = next(iter(pb.balances(page)))
    payee = data.payee(4)
    pb.fill_bill(page, src, payee, "10.00", verify=payee["account"] + "9")
    pb.send_payment(page)
    rec.step("Send payment where the verify-account number differs")
    pb.expect_validation_error(page)
    pb.expect_rejected(page, OK)


@pytest.mark.negative
@pytest.mark.boundary
@pytest.mark.parametrize("amount", ["", "abc", "0"])
def test_bill_payment_invalid_amount(page, rec, banked, amount):
    src = next(iter(pb.balances(page)))
    pb.fill_bill(page, src, data.payee(5), amount)
    pb.send_payment(page)
    rec.step(f"Send payment with amount {amount!r}")
    pb.expect_rejected(page, OK)
