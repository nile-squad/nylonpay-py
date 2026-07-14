"""Tests for poll-until-terminal continuation."""

from __future__ import annotations

from unittest.mock import Mock, patch

from nylonpay.slang import Ok

from nylonpay.poll_until_terminal import poll_until_terminal
from nylonpay.types import StatusResponse, Transaction


def _pending_tx(*, delayed: bool = False) -> Transaction:
    return Transaction(
        id="txn-123",
        reference="test-ref",
        amount=1000,
        currency="UGX",
        status="pending",
        type="collection",
        method="mobileMoney",
        description="Test",
        phone="256700000000",
        email=None,
        failure_reason=None,
        metadata={},
        mode="test",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:01Z",
        delayed=delayed or None,
    )


def _successful_tx() -> Transaction:
    return Transaction(
        id="txn-123",
        reference="test-ref",
        amount=1000,
        currency="UGX",
        status="successful",
        type="collection",
        method="mobileMoney",
        description="Test",
        phone="256700000000",
        email=None,
        failure_reason=None,
        metadata={},
        mode="test",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:02Z",
    )


def test_returns_pending_when_delayed_and_on_delayed_return() -> None:
    fetch_status = Mock(
        return_value=Ok(
            StatusResponse(
                reference="test-ref",
                status="pending",
                amount=1000,
                currency="UGX",
                updated_at="2024-01-01T00:00:01Z",
                delayed=True,
            )
        )
    )
    fetch_transaction = Mock(return_value=Ok(_pending_tx(delayed=True)))

    result = poll_until_terminal(
        {
            "fetch_status": fetch_status,
            "fetch_transaction": fetch_transaction,
            "on_delayed": "return",
            "poll_interval_ms": 10,
            "reference": "test-ref",
        }
    )

    assert result.is_ok
    assert result.value.status == "pending"
    assert result.value.delayed is True
    fetch_status.assert_called_once()


def test_keeps_polling_when_delayed_and_on_delayed_wait() -> None:
    fetch_status = Mock(
        side_effect=[
            Ok(
                StatusResponse(
                    reference="test-ref",
                    status="pending",
                    amount=1000,
                    currency="UGX",
                    updated_at="2024-01-01T00:00:01Z",
                    delayed=True,
                )
            ),
            Ok(
                StatusResponse(
                    reference="test-ref",
                    status="successful",
                    amount=1000,
                    currency="UGX",
                    updated_at="2024-01-01T00:00:02Z",
                )
            ),
        ]
    )
    fetch_transaction = Mock(return_value=Ok(_successful_tx()))

    with patch("nylonpay.poll_until_terminal.time.sleep", return_value=None):
        result = poll_until_terminal(
            {
                "fetch_status": fetch_status,
                "fetch_transaction": fetch_transaction,
                "on_delayed": "wait",
                "poll_interval_ms": 10,
                "reference": "test-ref",
            }
        )

    assert result.is_ok
    assert result.value.status == "successful"
    assert fetch_status.call_count == 2
