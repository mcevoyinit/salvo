"""End-to-end blackbox tests for Salvo.

These tests build real atomic transactions, encode them to bytes,
and verify every structural claim. No mocks. Real pytempo objects.
"""

import hashlib
import json

import pytest
from pytempo.contracts.addresses import (
    PATH_USD,
    ALPHA_USD,
    BETA_USD,
    STABLECOIN_DEX_ADDRESS,
)

from salvo import SwapPayBuilder
from salvo.builder import memo_hash


RECIPIENT = "0x" + "dd" * 20
RECIPIENT_2 = "0x" + "ee" * 20
RECIPIENT_3 = "0x" + "ff" * 20
BUILDER = SwapPayBuilder()


def build_basic(**overrides):
    defaults = dict(
        token_in=ALPHA_USD,
        token_out=PATH_USD,
        swap_amount=100_000,
        min_swap_out=95_000,
        pay_to=RECIPIENT,
        pay_amount=20_000,
        memo={"service": "test", "tier": "pro"},
    )
    defaults.update(overrides)
    return BUILDER.build(**defaults)


class TestAtomicSwapPay:
    """Core claim: swap + pay in a single atomic transaction."""

    def test_produces_exactly_2_calls(self):
        sp = build_basic()
        assert sp.num_calls == 2

    def test_first_call_targets_stablecoin_dex(self):
        sp = build_basic()
        swap_call = sp.tx.calls[0]
        expected = bytes.fromhex(STABLECOIN_DEX_ADDRESS[2:])  # Call.to is raw bytes
        assert swap_call.to == expected

    def test_second_call_targets_token_out(self):
        sp = build_basic()
        pay_call = sp.tx.calls[1]
        expected = bytes.fromhex(PATH_USD[2:])  # Call.to is raw bytes
        assert pay_call.to == expected

    def test_encodes_to_bytes(self):
        sp = build_basic()
        encoded = sp.tx.encode()
        assert isinstance(encoded, bytes)
        assert len(encoded) > 0

    def test_transaction_type_is_0x76(self):
        sp = build_basic()
        assert sp.tx.TRANSACTION_TYPE == 0x76
        assert sp.tx.encode()[0] == 0x76

    def test_chain_id_defaults_to_mainnet(self):
        sp = build_basic()
        assert sp.tx.chain_id == 4217

    def test_custom_chain_id(self):
        builder = SwapPayBuilder(chain_id=42431)
        sp = builder.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=100_000, min_swap_out=95_000,
            pay_to=RECIPIENT, pay_amount=20_000,
            memo={"test": True},
        )
        assert sp.tx.chain_id == 42431

    def test_dataclass_fields_populated(self):
        sp = build_basic()
        assert sp.token_in == ALPHA_USD
        assert sp.token_out == PATH_USD
        assert sp.swap_amount == 100_000
        assert sp.pay_amount == 20_000
        assert sp.pay_to == RECIPIENT


class TestMultiPay:
    """swap + N payments in one atomic transaction."""

    def test_3_payments_produces_4_calls(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD,
            token_out=PATH_USD,
            swap_amount=500_000,
            min_swap_out=475_000,
            payments=[
                {"to": RECIPIENT, "amount": 100_000, "memo": {"svc": "a"}},
                {"to": RECIPIENT_2, "amount": 200_000, "memo": {"svc": "b"}},
                {"to": RECIPIENT_3, "amount": 150_000, "memo": {"svc": "c"}},
            ],
        )
        assert sp.num_calls == 4  # 1 swap + 3 pays
        assert sp.tx.encode()

    def test_single_payment_multi_pay(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD,
            token_out=PATH_USD,
            swap_amount=100_000,
            min_swap_out=95_000,
            payments=[{"to": RECIPIENT, "amount": 50_000, "memo": {"x": 1}}],
        )
        assert sp.num_calls == 2  # 1 swap + 1 pay

    def test_empty_payments_rejected(self):
        with pytest.raises(ValueError):
            BUILDER.build_multi_pay(
                token_in=ALPHA_USD, token_out=PATH_USD,
                swap_amount=100_000, min_swap_out=95_000,
                payments=[],
            )


class TestFeeSponsorship:
    """sponsored=True sets awaiting_fee_payer on the transaction."""

    def test_sponsored_true(self):
        sp = build_basic(sponsored=True)
        assert sp.tx.awaiting_fee_payer is True
        assert sp.is_sponsored is True

    def test_sponsored_false_default(self):
        sp = build_basic()
        assert sp.tx.awaiting_fee_payer is False
        assert sp.is_sponsored is False

    def test_both_sponsored_values_encode(self):
        sp_yes = build_basic(sponsored=True)
        sp_no = build_basic(sponsored=False)
        assert sp_yes.tx.encode()
        assert sp_no.tx.encode()


class TestNonceKey:
    """Parallel execution lanes via nonce_key."""

    def test_default_nonce_key_is_0(self):
        sp = build_basic()
        assert sp.tx.nonce_key == 0

    def test_custom_nonce_key(self):
        sp = build_basic(nonce_key=5)
        assert sp.tx.nonce_key == 5

    def test_different_nonce_keys_both_encode(self):
        sp1 = build_basic(nonce_key=1)
        sp2 = build_basic(nonce_key=2)
        assert sp1.tx.encode()
        assert sp2.tx.encode()
        assert sp1.tx.nonce_key != sp2.tx.nonce_key


class TestMemoHash:
    """SHA-256 memo hashing — deterministic, exactly 32 bytes."""

    def test_deterministic(self):
        data = {"service": "search", "query_id": "abc123"}
        h1 = memo_hash(data)
        h2 = memo_hash(data)
        assert h1 == h2

    def test_exactly_32_bytes(self):
        h = memo_hash({"x": 1})
        assert isinstance(h, bytes)
        assert len(h) == 32

    def test_different_data_different_hash(self):
        h1 = memo_hash({"a": 1})
        h2 = memo_hash({"a": 2})
        assert h1 != h2

    def test_matches_manual_sha256(self):
        data = {"key": "value"}
        expected = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).digest()
        assert memo_hash(data) == expected

    def test_key_order_irrelevant(self):
        h1 = memo_hash({"z": 1, "a": 2})
        h2 = memo_hash({"a": 2, "z": 1})
        assert h1 == h2


class TestStablecoinPairs:
    """Every stablecoin pair builds a valid transaction."""

    @pytest.mark.parametrize("token_in", [ALPHA_USD, BETA_USD])
    def test_swap_to_path_usd(self, token_in):
        sp = BUILDER.build(
            token_in=token_in,
            token_out=PATH_USD,
            swap_amount=100_000,
            min_swap_out=90_000,
            pay_to=RECIPIENT,
            pay_amount=50_000,
            memo={"pair": f"{token_in[:8]}->pathUSD"},
        )
        assert sp.num_calls == 2
        assert sp.tx.encode()
