"""CANARIES - deliberately failing tests with a known ground-truth failure class.

They exist for two honest reasons:
  1. to exercise the failure -> Claude triage -> Jira path on demand (the public demo site rarely fails by itself);
  2. to score the AI triage: each carries @expected_class, and the pipeline reports Claude's accuracy against it.

They are skipped unless RUN_CANARIES=1, and every Jira ticket they create is labelled `canary`.
The "real defect" canaries encode a *specification* the app does not follow (spec-vs-behaviour mismatch);
they do not claim ParaBank has that defect in production.
"""
import pytest
from playwright.sync_api import expect

from framework import parabank as pb

pytestmark = pytest.mark.canary


@pytest.mark.expected_class("UI_CHANGE")
@pytest.mark.parametrize("renamed", ["Sign In", "Submit"])
def test_canary_ui_change_button_renamed(page, rec, customer, renamed):
    """Simulates a release that renamed the login button: flow still works, locator does not."""
    page.goto(pb.url("index.htm"))
    page.fill('input[name="username"]', customer["username"])
    page.click(f'input[value="{renamed}"]', timeout=3000)


@pytest.mark.expected_class("DATA_ISSUE")
@pytest.mark.parametrize("variant", ["unregistered_user", "stale_account_id"])
def test_canary_data_issue(page, rec, banked, variant):
    """Test data is wrong, not the app: logs in with a user that was never created / uses an account id that does not exist."""
    if variant == "unregistered_user":
        pb.logout(page)
        pb.login(page, "ghost_user_never_registered", "x")
        expect(page.get_by_role("heading", name="Accounts Overview")).to_be_visible(timeout=3000)
    else:
        page.set_default_timeout(4000)
        pb.transfer(page, "00000", "99999", "5.00")
        expect(page.locator("#showResult")).to_contain_text("Transfer Complete!", timeout=3000)


@pytest.mark.expected_class("REAL_DEFECT")
@pytest.mark.parametrize("amount", ["10.00", "40.00"])
def test_canary_spec_mismatch_balance(page, rec, two_accounts, amount):
    """Spec encoded here (intentionally wrong): 'a transfer must NOT change the source balance'.
    The app correctly debits the account, so the assertion fails with a balance mismatch that looks like a money-movement defect."""
    src, dst = two_accounts
    before = pb.balances(page)[src]
    pb.transfer(page, src, dst, amount)
    after = pb.balances(page)[src]
    assert after == before, f"expected source balance to remain {before:.2f} after transfer of {amount}, got {after:.2f}"
