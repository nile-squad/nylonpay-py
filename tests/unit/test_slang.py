"""Unit tests for the Result type.

Mirrors the TS SDK's result.test.ts — Ok/Err construction, value/error
access, immutability, and the wrong-side-access guard.
"""

from __future__ import annotations

import dataclasses

import pytest

from nylonpay.slang import Err, Ok, Result


def test_ok_creates_success_result():
    r = Ok(42)
    assert r.is_ok is True
    assert r.is_err is False
    assert r.value == 42


def test_err_creates_error_result():
    r = Err("boom")
    assert r.is_err is True
    assert r.is_ok is False
    assert r.error == "boom"


def test_value_on_err_raises():
    r = Err("x")
    with pytest.raises(ValueError, match=r"Cannot access \.value"):
        _ = r.value


def test_error_on_ok_raises():
    r = Ok(1)
    with pytest.raises(ValueError, match=r"Cannot access \.error"):
        _ = r.error


def test_result_is_frozen():
    r = Ok(1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r._is_ok = False  # ty: ignore[invalid-assignment]


def test_result_ok_constructor():
    r = Result.ok("hello")
    assert r.is_ok and r.value == "hello"


def test_result_err_constructor():
    r = Result.err("nope")
    assert r.is_err and r.error == "nope"


def test_try_success():
    """Result.try_ wraps a successful callable."""
    result = Result.try_(lambda: 42)
    assert result.is_ok
    assert result.value == 42


def test_try_catches_exception():
    """Result.try_ catches exceptions and returns Err."""

    def boom():
        raise ValueError("kaboom")

    result = Result.try_(boom)
    assert result.is_err
    assert isinstance(result.error, ValueError)
    assert str(result.error) == "kaboom"


def test_try_never_raises():
    """Result.try_ never raises even on catastrophic failure."""

    def catastrophe():
        raise RuntimeError("the end")

    result = Result.try_(catastrophe)
    assert result.is_err
    assert isinstance(result.error, RuntimeError)
