"""Account registration = digital onboarding. Data-driven with synthetic KYC-style customers."""
import pytest

from framework import data
from framework import parabank as pb


@pytest.mark.sop("Register as a new online banking customer")
def test_register_new_customer(page, rec, customer):
    page.goto(pb.url("register.htm"))
    rec.step("Open the Register page from the home page")
    pb.fill_registration(page, customer)
    rec.step("Fill in your personal details, address, identification number and choose a username and password")
    page.click('input[value="Register"]')
    pb.expect_registered(page)
    rec.step("Select Register - a confirmation says your account was created and you are signed in")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_register_data_driven(page, rec, n):
    c = data.customer(500 + n)
    pb.register(page, c)
    pb.expect_registered(page)


REQUIRED = [
    "customer.firstName",
    "customer.lastName",
    "customer.address.street",
    "customer.address.city",
    "customer.ssn",
    "customer.username",
    "customer.password",
]


@pytest.mark.negative
@pytest.mark.parametrize("blank", REQUIRED)
def test_register_missing_required_field(page, rec, customer, blank):
    pb.register(page, customer, blank=blank)
    rec.step(f"Submit with {blank} left blank")
    pb.expect_validation_error(page)
    pb.expect_not_logged_in(page)


@pytest.mark.negative
def test_register_password_mismatch(page, rec, customer):
    pb.register(page, customer, mismatch_password=True)
    rec.step("Submit with mismatching password confirmation")
    pb.expect_validation_error(page)


@pytest.mark.negative
def test_register_duplicate_username(page, rec, customer):
    pb.register(page, customer)
    pb.expect_registered(page)
    pb.logout(page)
    pb.register(page, customer)  # same username again
    rec.step("Register again with an already-used username")
    pb.expect_validation_error(page)
