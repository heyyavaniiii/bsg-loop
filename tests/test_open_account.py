import pytest
from playwright.sync_api import expect

from framework import parabank as pb


@pytest.mark.sop("Open a new savings account")
def test_open_savings_account(page, rec, banked):
    page.goto(pb.url("openaccount.htm"))
    pb._wait_options(page, "#fromAccountId")
    rec.step("Select Open New Account from the left-hand menu")
    page.select_option("#type", "1")
    rec.step("Choose SAVINGS as the account type and pick the account to fund it from")
    page.click('input[value="Open New Account"]')
    expect(page.locator("#openAccountResult")).to_contain_text("Account Opened!")
    rec.step("Select Open New Account - the new account number is displayed")


@pytest.mark.parametrize("kind", ["SAVINGS", "CHECKING"])
def test_new_account_appears_in_overview(page, rec, banked, kind):
    before = set(pb.balances(page))
    new_id = pb.open_account(page, kind)
    assert new_id.isdigit(), f"account id should be numeric, got {new_id!r}"
    after = set(pb.balances(page))
    assert after - before == {new_id}
