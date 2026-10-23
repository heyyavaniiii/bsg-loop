import pytest
from playwright.sync_api import expect

from framework import parabank as pb

OK = "Transfer Complete!"


@pytest.mark.sop("Transfer funds between your own accounts")
def test_transfer_between_own_accounts(page, rec, two_accounts):
    src, dst = two_accounts
    page.goto(pb.url("transfer.htm"))
    pb._wait_options(page, "#fromAccountId")
    pb._wait_options(page, "#toAccountId")
    rec.step("Select Transfer Funds from the left-hand menu")
    page.fill("#amount", "25.00")
    page.select_option("#fromAccountId", src)
    page.select_option("#toAccountId", dst)
    rec.step("Enter the amount and choose the account to transfer from and the account to transfer to")
    page.click('input[value="Transfer"]')
    expect(page.locator("#showResult")).to_contain_text(OK)
    rec.step("Select Transfer - a confirmation shows the amount moved between the two accounts")


@pytest.mark.boundary
@pytest.mark.parametrize("amount", ["0.01", "10.55", "100.00"])
def test_transfer_valid_amounts_update_balances(page, rec, two_accounts, amount):
    src, dst = two_accounts
    before = pb.balances(page)
    pb.transfer(page, src, dst, amount)
    expect(page.locator("#showResult")).to_contain_text(OK)
    after = pb.balances(page)
    assert round(before[src] - after[src], 2) == float(amount), "source balance must drop by exactly the amount"
    assert round(after[dst] - before[dst], 2) == float(amount), "destination balance must rise by exactly the amount"


@pytest.mark.negative
@pytest.mark.boundary
@pytest.mark.parametrize(
    "amount",
    [
        pytest.param("0", id="zero"),
        pytest.param("-5", id="negative"),
        pytest.param("abc", id="non_numeric"),
        pytest.param("", id="empty"),
        pytest.param("1.2.3", id="malformed_decimal"),
    ],
)
def test_transfer_invalid_amount_rejected(page, rec, two_accounts, amount):
    src, dst = two_accounts
    pb.transfer(page, src, dst, amount)
    rec.step(f"Transfer attempted with amount {amount!r}")
    pb.expect_rejected(page, OK)
