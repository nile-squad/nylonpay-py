"""Unit tests for snake/camel wire format conversion."""

from __future__ import annotations

from nylonpay.types import CollectPaymentInput, Customer, StatusResponse
from nylonpay.wire import camel_to_snake, from_wire, snake_to_camel, to_wire

# snake_to_camel ---------------------------------------------------------------


def test_snake_to_camel_simple():
    assert snake_to_camel("phone_number") == "phoneNumber"
    assert snake_to_camel("api_key") == "apiKey"
    assert snake_to_camel("updated_at") == "updatedAt"


def test_snake_to_camel_single_word():
    assert snake_to_camel("foo") == "foo"


def test_snake_to_camel_many_underscores():
    assert snake_to_camel("a_b_c_d_e") == "aBCDE"


# camel_to_snake ---------------------------------------------------------------


def test_camel_to_snake_simple():
    assert camel_to_snake("phoneNumber") == "phone_number"
    assert camel_to_snake("updatedAt") == "updated_at"
    assert camel_to_snake("apiKey") == "api_key"


def test_camel_to_snake_single_word():
    assert camel_to_snake("foo") == "foo"


def test_camel_to_snake_consecutive_caps():
    # Common heuristic: every uppercase gets a preceding underscore
    assert camel_to_snake("APIKey") == "a_p_i_key"


# to_wire ----------------------------------------------------------------------


def test_to_wire_dict_snake_to_camel():
    out = to_wire({"phone_number": "+256700000000", "api_key": "npk_x"})
    assert out == {"phoneNumber": "+256700000000", "apiKey": "npk_x"}


def test_to_wire_dataclass_to_camel_dict():
    inp = CollectPaymentInput(
        amount=1000,
        currency="UGX",
        customer=Customer(name="Alice", phone_number="+256700000000"),
        description="Order",
    )
    out = to_wire(inp)
    assert out["amount"] == 1000
    assert out["currency"] == "UGX"
    assert out["description"] == "Order"
    assert isinstance(out["customer"], dict)
    assert out["customer"]["phoneNumber"] == "+256700000000"
    assert out["customer"]["name"] == "Alice"


def test_to_wire_nested_dataclass_to_camel():
    inp = CollectPaymentInput(
        amount=1000,
        currency="UGX",
        customer=Customer(name="Alice", phone_number="+256700000000"),
        description="x",
    )
    out = to_wire(inp)
    assert "customer" in out
    assert "phoneNumber" in out["customer"]
    assert "phone_number" not in out["customer"]


def test_to_wire_list_processed_element_by_element():
    out = to_wire([{"phone_number": "1"}, {"phone_number": "2"}])
    assert out == [{"phoneNumber": "1"}, {"phoneNumber": "2"}]


def test_to_wire_passthrough_non_dict():
    assert to_wire(42) == 42
    assert to_wire("string") == "string"
    assert to_wire(None) is None


# from_wire --------------------------------------------------------------------


def test_from_wire_camel_to_snake_dataclass():
    wire = {
        "reference": "ref_abc",
        "status": "pending",
        "amount": 1000,
        "currency": "UGX",
        "updatedAt": "2024-01-01T00:00:00Z",
    }
    r = from_wire(StatusResponse, wire)
    assert isinstance(r, StatusResponse)
    assert r.reference == "ref_abc"
    assert r.status == "pending"
    assert r.amount == 1000
    assert r.currency == "UGX"
    assert r.updated_at == "2024-01-01T00:00:00Z"


def test_from_wire_filters_unknown_keys():
    wire = {
        "reference": "ref_abc",
        "status": "pending",
        "amount": 1000,
        "currency": "UGX",
        "updatedAt": "2024-01-01T00:00:00Z",
        "unknownField": "leaked",
        "provider": "internal",
    }
    r = from_wire(StatusResponse, wire)
    assert not hasattr(r, "unknown_field")
    assert not hasattr(r, "provider")


def test_from_wire_non_dataclass_returns_data():
    out = from_wire(dict, {"foo": "bar"})
    assert out == {"foo": "bar"}


def test_from_wire_with_optional_fields():
    wire = {
        "reference": "ref",
        "status": "pending",
        "amount": 100,
        "currency": "UGX",
        "updatedAt": "2024",
    }
    r = from_wire(StatusResponse, wire)
    assert r.reference == "ref"
