"""Unit tests for dict-to-dataclass coercion at SDK boundaries."""

from __future__ import annotations

import pytest

from nylonpay.coerce import coerce_dataclass
from nylonpay.types import (
    BankDetails,
    CollectPaymentInput,
    CreateInvoiceInput,
    Customer,
    Destination,
    InvoiceItem,
    MakePayoutInput,
)

# Dict → dataclass (flat) ------------------------------------------------------


def test_dict_to_dataclass_flat():
    data = {"name": "John", "phone_number": "256700000000"}
    result = coerce_dataclass(Customer, data)

    assert isinstance(result, Customer)
    assert result.name == "John"
    assert result.phone_number == "256700000000"
    assert result.email is None


# Dict → dataclass (with optional fields) --------------------------------------


def test_dict_to_dataclass_optional_fields_omitted():
    data = {"name": "Jane", "phone_number": "256700000001"}
    result = coerce_dataclass(Customer, data)

    assert isinstance(result, Customer)
    assert result.email is None


def test_dict_to_dataclass_optional_fields_provided():
    data = {"name": "Jane", "phone_number": "256700000001", "email": "jane@example.com"}
    result = coerce_dataclass(Customer, data)

    assert isinstance(result, Customer)
    assert result.email == "jane@example.com"


# Dict → dataclass (with None optional) ----------------------------------------


def test_dict_to_dataclass_none_optional():
    data = {"name": "Jane", "phone_number": "256700000001", "email": None}
    result = coerce_dataclass(Customer, data)

    assert isinstance(result, Customer)
    assert result.email is None


# Already a dataclass ----------------------------------------------------------


def test_already_dataclass_returns_unchanged():
    original = Customer(name="John", phone_number="256700000000")
    result = coerce_dataclass(Customer, original)

    assert result is original


# Non-dict, non-dataclass ------------------------------------------------------


def test_non_dict_non_dataclass_returns_unchanged():
    result = coerce_dataclass(Customer, "just a string")
    assert result == "just a string"


def test_integer_returns_unchanged():
    result = coerce_dataclass(Customer, 42)
    assert result == 42


# Nested dict coercion ---------------------------------------------------------


def test_nested_dict_customer():
    data = {
        "amount": 5000,
        "currency": "UGX",
        "customer": {"name": "John", "phone_number": "256700000000"},
        "description": "Order #1",
    }
    result = coerce_dataclass(CollectPaymentInput, data)

    assert isinstance(result, CollectPaymentInput)
    assert isinstance(result.customer, Customer)
    assert result.customer.name == "John"
    assert result.customer.phone_number == "256700000000"


# List of dicts ----------------------------------------------------------------


def test_list_of_dicts_single():
    data = {
        "amount": 10000,
        "currency": "UGX",
        "customer_email": "buyer@example.com",
        "description": "Invoice #1",
        "items": [{"name": "Widget", "quantity": 1, "amount": 5000}],
    }
    result = coerce_dataclass(CreateInvoiceInput, data)

    assert isinstance(result, CreateInvoiceInput)
    assert isinstance(result.items, list)
    assert len(result.items) == 1
    assert isinstance(result.items[0], InvoiceItem)
    assert result.items[0].name == "Widget"
    assert result.items[0].quantity == 1
    assert result.items[0].amount == 5000


def test_list_of_dicts_multiple():
    data = {
        "amount": 15000,
        "currency": "UGX",
        "customer_email": "buyer@example.com",
        "description": "Invoice #2",
        "items": [
            {"name": "Widget", "quantity": 2, "amount": 5000},
            {"name": "Gadget", "quantity": 1, "amount": 5000},
        ],
    }
    result = coerce_dataclass(CreateInvoiceInput, data)

    assert len(result.items) == 2
    assert all(isinstance(item, InvoiceItem) for item in result.items)
    assert result.items[0].name == "Widget"
    assert result.items[1].name == "Gadget"


# Mixed list (dict + dataclass) ------------------------------------------------


def test_mixed_list_dict_and_dataclass():
    existing = InvoiceItem(name="Gadget", quantity=1, amount=3000)
    data = {
        "amount": 8000,
        "currency": "UGX",
        "customer_email": "buyer@example.com",
        "description": "Mixed",
        "items": [
            {"name": "Widget", "quantity": 1, "amount": 5000},
            existing,
        ],
    }
    result = coerce_dataclass(CreateInvoiceInput, data)

    assert len(result.items) == 2
    assert isinstance(result.items[0], InvoiceItem)
    assert result.items[0].name == "Widget"
    assert result.items[1] is existing


# Nested with Destination ------------------------------------------------------


def test_nested_destination():
    data = {
        "amount": 50000,
        "currency": "UGX",
        "customer": {"name": "John", "phone_number": "256700000000"},
        "destination": {
            "account_holder_name": "John Doe",
            "account_number": "1234567890",
        },
        "description": "Payout #1",
    }
    result = coerce_dataclass(MakePayoutInput, data)

    assert isinstance(result, MakePayoutInput)
    assert isinstance(result.destination, Destination)
    assert result.destination.account_holder_name == "John Doe"
    assert result.destination.account_number == "1234567890"
    assert result.destination.bank_name is None


# Deeply nested (customer + bank) ----------------------------------------------


def test_deeply_nested_customer_and_bank():
    data = {
        "amount": 100000,
        "currency": "UGX",
        "customer": {"name": "Jane", "phone_number": "256700000001"},
        "description": "Bank collection",
        "method": "bank",
        "bank": {"account_number": "9876543210", "bank_name": "Stanbic"},
    }
    result = coerce_dataclass(CollectPaymentInput, data)

    assert isinstance(result.customer, Customer)
    assert result.customer.name == "Jane"
    assert isinstance(result.bank, BankDetails)
    assert result.bank.account_number == "9876543210"
    assert result.bank.bank_name == "Stanbic"


# Extra keys in dict → TypeError -----------------------------------------------


def test_extra_keys_raises_type_error():
    data = {"name": "John", "phone_number": "256700000000", "extra_field": "nope"}

    with pytest.raises(TypeError):
        coerce_dataclass(Customer, data)


# Empty dict -------------------------------------------------------------------


def test_empty_dict_raises_for_required_fields():
    with pytest.raises(TypeError):
        coerce_dataclass(Customer, {})


def test_empty_dict_raises_for_collect_input():
    with pytest.raises(TypeError):
        coerce_dataclass(CollectPaymentInput, {})


# None value -------------------------------------------------------------------


def test_none_value_returns_none():
    result = coerce_dataclass(Customer, None)
    assert result is None


# Dict with None values for required fields ------------------------------------


def test_dict_with_none_required_field_constructs():
    """coerce doesn't validate — just constructs. None passes through."""
    data = {"name": None, "phone_number": "256700000000"}
    result = coerce_dataclass(Customer, data)

    assert isinstance(result, Customer)
    assert result.name is None
    assert result.phone_number == "256700000000"


# Destination with optional fields ---------------------------------------------


def test_destination_all_fields():
    data = {
        "account_holder_name": "Jane",
        "account_number": "111222333",
        "bank_name": "Centenary",
        "phone": "256700000002",
    }
    result = coerce_dataclass(Destination, data)

    assert isinstance(result, Destination)
    assert result.bank_name == "Centenary"
    assert result.phone == "256700000002"


# Invoice item direct ----------------------------------------------------------


def test_invoice_item_from_dict():
    data = {"name": "Service Fee", "quantity": 1, "amount": 2000}
    result = coerce_dataclass(InvoiceItem, data)

    assert isinstance(result, InvoiceItem)
    assert result.name == "Service Fee"
    assert result.quantity == 1
    assert result.amount == 2000


# List of dicts with None items field ------------------------------------------


def test_none_items_field_stays_none():
    data = {
        "amount": 5000,
        "currency": "UGX",
        "customer_email": "buyer@example.com",
        "description": "No items",
        "items": None,
    }
    result = coerce_dataclass(CreateInvoiceInput, data)

    assert result.items is None


# Bank details None in optional bank field -------------------------------------


def test_bank_none_in_collect_input():
    data = {
        "amount": 5000,
        "currency": "UGX",
        "customer": {"name": "John", "phone_number": "256700000000"},
        "description": "MM collection",
        "bank": None,
    }
    result = coerce_dataclass(CollectPaymentInput, data)

    assert result.bank is None
