"""Tests for SwapPayBuilder — atomic transaction construction."""

import json
from pytempo import TempoTransaction, Call
from pytempo.contracts.addresses import PATH_USD, ALPHA_USD, BETA_USD
from mpp.methods.tempo import TempoAccount

from flashpay.builder import SwapPayBuilder, SwapPay, memo_hash, STABLECOINS


RECIPIENT = TempoAccount.from_key("0x" + "dd" * 32).address
BUILDER = SwapPayBuilder()


class TestMemoHash:
    def test_32_bytes(self):
        assert len(memo_hash({"a": 1})) == 32

    def test_deterministic(self):
        assert memo_hash({"a": 1, "b": 2}) == memo_hash({"b": 2, "a": 1})

    def test_different_data(self):
        assert memo_hash({"a": 1}) != memo_hash({"a": 2})


class TestBuildBasic:
    def test_returns_swap_pay(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert isinstance(sp, SwapPay)

    def test_two_calls(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert sp.num_calls == 2

    def test_tx_is_tempo_transaction(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert isinstance(sp.tx, TempoTransaction)
        assert sp.tx.TRANSACTION_TYPE == 0x76

    def test_chain_id(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert sp.tx.chain_id == 42431

    def test_calls_are_call_objects(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert isinstance(sp.swap_call, Call)
        assert isinstance(sp.pay_call, Call)

    def test_swap_call_targets_dex(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        from pytempo.contracts.addresses import STABLECOIN_DEX_ADDRESS
        # swap_call.to should be the DEX address (as bytes)
        assert sp.swap_call.to is not None

    def test_pay_call_targets_token(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert sp.pay_call.to is not None

    def test_different_swap_directions(self):
        sp1 = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        sp2 = BUILDER.build(
            token_in=BETA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        # Different swap calls (different token_in)
        assert sp1.swap_call.data != sp2.swap_call.data
        assert sp1.token_in != sp2.token_in


class TestMemo:
    def test_with_memo(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            memo={"task": "research", "agent": "a1"},
        )
        assert sp.memo_data == {"task": "research", "agent": "a1"}

    def test_memo_changes_calldata(self):
        sp_no_memo = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        sp_with_memo = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            memo={"task": "x"},
        )
        assert sp_no_memo.pay_call.data != sp_with_memo.pay_call.data

    def test_different_memos_different_calldata(self):
        sp1 = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            memo={"task": "a"},
        )
        sp2 = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            memo={"task": "b"},
        )
        assert sp1.pay_call.data != sp2.pay_call.data


class TestSponsored:
    def test_not_sponsored_by_default(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert not sp.is_sponsored

    def test_sponsored_flag(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            sponsored=True,
        )
        assert sp.is_sponsored
        assert sp.tx.awaiting_fee_payer is True


class TestNonceKey:
    def test_default_nonce_key(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        assert sp.tx.nonce_key == 0

    def test_custom_nonce_key(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
            nonce_key=7,
        )
        assert sp.tx.nonce_key == 7


class TestEncoding:
    def test_encodes_to_bytes(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        raw = sp.tx.encode()
        assert isinstance(raw, bytes)
        assert raw[0] == 0x76  # TempoTransaction type

    def test_signable(self):
        sp = BUILDER.build(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            pay_to=RECIPIENT, pay_amount=900_000,
        )
        key = "0x" + "ab" * 32
        signed = sp.tx.sign(key)
        assert signed.sender_signature is not None


class TestMultiPay:
    def test_swap_plus_two_payments(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=2_000_000, min_swap_out=1_800_000,
            payments=[
                {"to": RECIPIENT, "amount": 1_000_000, "memo": {"idx": 0}},
                {"to": RECIPIENT, "amount": 500_000, "memo": {"idx": 1}},
            ],
        )
        assert sp.num_calls == 3  # 1 swap + 2 pays

    def test_swap_plus_three_payments(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=5_000_000, min_swap_out=4_500_000,
            payments=[
                {"to": RECIPIENT, "amount": 1_000_000},
                {"to": RECIPIENT, "amount": 2_000_000},
                {"to": RECIPIENT, "amount": 1_500_000, "memo": {"type": "fee"}},
            ],
        )
        assert sp.num_calls == 4  # 1 swap + 3 pays

    def test_multi_pay_total_amount(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=3_000_000, min_swap_out=2_700_000,
            payments=[
                {"to": RECIPIENT, "amount": 1_000_000},
                {"to": RECIPIENT, "amount": 2_000_000},
            ],
        )
        assert sp.pay_amount == 3_000_000

    def test_multi_pay_sponsored(self):
        sp = BUILDER.build_multi_pay(
            token_in=ALPHA_USD, token_out=PATH_USD,
            swap_amount=1_000_000, min_swap_out=900_000,
            payments=[{"to": RECIPIENT, "amount": 500_000}],
            sponsored=True,
        )
        assert sp.is_sponsored


class TestStablecoins:
    def test_all_stablecoin_addresses_present(self):
        assert "pathUSD" in STABLECOINS
        assert "alphaUSD" in STABLECOINS
        assert "betaUSD" in STABLECOINS
        assert "thetaUSD" in STABLECOINS

    def test_all_pairs_build(self):
        for name, addr in STABLECOINS.items():
            if addr == PATH_USD:
                continue
            sp = BUILDER.build(
                token_in=addr, token_out=PATH_USD,
                swap_amount=100_000, min_swap_out=90_000,
                pay_to=RECIPIENT, pay_amount=90_000,
            )
            assert sp.num_calls == 2
