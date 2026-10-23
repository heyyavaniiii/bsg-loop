"""Thin page-object helpers for ParaBank (https://parabank.parasoft.com).

NOTE: selectors are written from knowledge of the ParaBank markup and were not verified against the live
site when this file was generated. Run the suite once and fix any selector that errors; every selector
lives in this file so there is one place to repair.
"""
import re

from playwright.sync_api import Page, expect

from framework.config import BASE_URL

REG_FIELDS = {
    "customer.firstName": "first_name",
    "customer.lastName": "last_name",
    "customer.address.street": "street",
    "customer.address.city": "city",
    "customer.address.state": "state",
    "customer.address.zipCode": "zip",
    "customer.phoneNumber": "phone",
    "customer.ssn": "kyc_id",
    "customer.username": "username",
    "customer.password": "password",
    "repeatedPassword": "password",
}

PAYEE_FIELDS = {
    "payee.name": "name",
    "payee.address.street": "street",
    "payee.address.city": "city",
    "payee.address.state": "state",
    "payee.address.zipCode": "zip",
    "payee.phoneNumber": "phone",
    "payee.accountNumber": "account",
}


def url(path: str) -> str:
    return f"{BASE_URL}/{path}"


def money(text: str) -> float:
    return float(text.replace("$", "").replace(",", "").strip())


# ---------- registration / login ----------
def fill_registration(page: Page, c: dict, blank: str | None = None, mismatch_password: bool = False):
    for field, key in REG_FIELDS.items():
        value = "" if field == blank else c[key]
        if mismatch_password and field == "repeatedPassword":
            value = c["password"] + "x"
        page.fill(f'input[name="{field}"]', value)


def register(page: Page, c: dict, **kw):
    page.goto(url("register.htm"))
    fill_registration(page, c, **kw)
    page.click('input[value="Register"]')


def expect_registered(page: Page):
    expect(page.locator("#rightPanel")).to_contain_text("Your account was created successfully")


def login(page: Page, username: str, password: str):
    page.goto(url("index.htm"))
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('input[value="Log In"]')


def logout(page: Page):
    page.get_by_role("link", name="Log Out").click()


def expect_not_logged_in(page: Page):
    expect(page.get_by_role("link", name="Log Out")).to_have_count(0)


# ---------- accounts ----------
def _wait_options(page: Page, selector: str):
    page.wait_for_function(
        "sel => { const e = document.querySelector(sel); return e && e.options.length > 0; }", arg=selector
    )


def balances(page: Page) -> dict[str, float]:
    page.goto(url("overview.htm"))
    page.wait_for_selector("#accountTable tbody tr")
    out = {}
    for row in page.locator("#accountTable tbody tr").all():
        cells = row.locator("td")
        if cells.count() < 2:
            continue
        acct = cells.nth(0).inner_text().strip()
        if acct.isdigit():
            out[acct] = money(cells.nth(1).inner_text())
    return out


def open_account(page: Page, kind: str = "SAVINGS") -> str:
    page.goto(url("openaccount.htm"))
    _wait_options(page, "#fromAccountId")
    page.select_option("#type", "1" if kind == "SAVINGS" else "0")
    page.click('input[value="Open New Account"]')
    expect(page.locator("#openAccountResult")).to_contain_text("Account Opened!")
    return page.locator("#newAccountId").inner_text().strip()


# ---------- money movement ----------
def transfer(page: Page, from_id: str, to_id: str, amount: str):
    page.goto(url("transfer.htm"))
    _wait_options(page, "#fromAccountId")
    _wait_options(page, "#toAccountId")
    page.fill("#amount", amount)
    page.select_option("#fromAccountId", from_id)
    page.select_option("#toAccountId", to_id)
    page.click('input[value="Transfer"]')


def fill_bill(page: Page, from_id: str, payee: dict, amount: str, verify: str | None = None, blank: str | None = None):
    page.goto(url("billpay.htm"))
    _wait_options(page, 'select[name="fromAccountId"]')
    for field, key in PAYEE_FIELDS.items():
        page.fill(f'input[name="{field}"]', "" if field == blank else payee[key])
    page.fill('input[name="verifyAccount"]', payee["account"] if verify is None else verify)
    page.fill('input[name="amount"]', amount)
    page.select_option('select[name="fromAccountId"]', from_id)


def send_payment(page: Page):
    page.click('input[value="Send Payment"]')


def expect_rejected(page: Page, success_text: str):
    """The success banner must never appear. Waits for the network to settle first so a slow
    success response can't sneak in after the assertion."""
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(success_text)).to_have_count(0)


def expect_validation_error(page: Page):
    expect(page.locator(".error").first).to_be_visible()


ACCOUNT_ID = re.compile(r"^\d+$")
