import re

import pytest
from playwright.sync_api import expect

from framework import parabank as pb


@pytest.mark.sop("Log in to online banking")
def test_login_valid_credentials(page, rec, banked):
    pb.logout(page)
    page.goto(pb.url("index.htm"))
    rec.step("Open the online banking home page")
    page.fill('input[name="username"]', banked["username"])
    page.fill('input[name="password"]', banked["password"])
    rec.step("Enter your username and password in the Customer Login panel")
    page.click('input[value="Log In"]')
    expect(page).to_have_url(re.compile(r"overview\.htm"))
    expect(page.get_by_role("heading", name="Accounts Overview")).to_be_visible()
    rec.step("Select Log In - the Accounts Overview page confirms you are signed in")


def test_logout_ends_session(page, rec, banked):
    pb.logout(page)
    pb.expect_not_logged_in(page)
    page.goto(pb.url("overview.htm"))
    pb.expect_not_logged_in(page)  # protected page must not reopen the session


NEGATIVE_LOGINS = [
    pytest.param(lambda c: (c["username"], "WrongPass#1"), True, id="wrong_password"),
    pytest.param(lambda c: ("nouser" + c["username"], c["password"]), True, id="unknown_user"),
    pytest.param(lambda c: ("", ""), True, id="empty_both"),
    pytest.param(lambda c: (c["username"], ""), True, id="empty_password"),
    pytest.param(lambda c: ("", c["password"]), True, id="empty_username"),
    pytest.param(lambda c: ("' OR '1'='1' --", "x"), False, id="sql_injection_username"),
    pytest.param(lambda c: ("a" * 300, "x"), False, id="very_long_username"),
]


@pytest.mark.negative
@pytest.mark.parametrize("creds, expect_msg", NEGATIVE_LOGINS)
def test_login_rejected(page, rec, customer, creds, expect_msg):
    username, password = creds(customer)
    pb.login(page, username, password)
    rec.step(f"Login attempt rejected ({username[:20]!r})")
    pb.expect_not_logged_in(page)
    if expect_msg:
        pb.expect_validation_error(page)
