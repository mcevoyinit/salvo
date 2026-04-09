"""Live testnet: atomic swap+pay on Tempo Moderato.

Run with: pytest tests/test_live.py -v -s
"""

import pytest
from mpp.methods.tempo import TempoAccount
from pytempo.contracts.addresses import PATH_USD, ALPHA_USD

from salvo.builder import SwapPayBuilder, memo_hash
from salvo.submitter import TxSubmitter

MASTER_KEY = "0x" + "ab" * 32
RECIPIENT_KEY = "0x" + "cd" * 32


@pytest.fixture(scope="module")
def accounts():
    master = TempoAccount.from_key(MASTER_KEY)
    recipient = TempoAccount.from_key(RECIPIENT_KEY)
    return master, recipient


@pytest.fixture(scope="module")
def submitter(accounts):
    return TxSubmitter(accounts[0])


class TestLiveSwapPay:

    @pytest.mark.asyncio
    async def test_fund_and_approve(self, submitter, accounts):
        """Fund accounts and approve DEX to spend tokens."""
        from pytempo import TempoTransaction
        from pytempo.contracts.tip20 import TIP20
        from pytempo.contracts.addresses import STABLECOIN_DEX_ADDRESS

        master, recipient = accounts
        for addr in [master.address, recipient.address]:
            await submitter.fund(addr)

        # Approve DEX for both tokens
        for token in [ALPHA_USD, PATH_USD]:
            tip = TIP20(token)
            approve = tip.approve(spender=STABLECOIN_DEX_ADDRESS, amount=2**128 - 1)
            tx = TempoTransaction(
                chain_id=42431, calls=(approve,), gas_limit=500_000,
                max_fee_per_gas=25_000_000_000, max_priority_fee_per_gas=1_000_000_000,
            )
            r = await submitter.sign_and_send(tx)
            assert r.success, f"Approve failed for {token}"

        bal = await submitter.balance(ALPHA_USD)
        assert bal > 0
        print(f"\n  AlphaUSD balance: ${bal / 1_000_000:,.2f}")
        print(f"  DEX approved for both tokens")

    @pytest.mark.asyncio
    async def test_atomic_swap_and_pay(self, submitter, accounts):
        """THE TEST: swap AlphaUSD→pathUSD + pay recipient, one atomic tx."""
        _, recipient = accounts
        builder = SwapPayBuilder()

        sp = builder.build(
            token_in=ALPHA_USD,
            token_out=PATH_USD,
            swap_amount=100_000,       # $0.10 alphaUSD
            min_swap_out=1,            # accept any output (testnet)
            pay_to=recipient.address,
            pay_amount=50_000,         # $0.05 pathUSD
            memo={"task": "salvo-live-test", "type": "swap+pay"},
        )

        assert sp.num_calls == 2
        receipt = await submitter.sign_and_send(sp.tx)

        print(f"\n  ATOMIC SWAP+PAY:")
        print(f"  TX hash:  {receipt.tx_hash}")
        print(f"  Block:    {receipt.block}")
        print(f"  Gas used: {receipt.gas_used}")
        print(f"  Status:   {'SUCCESS' if receipt.success else 'FAILED'}")
        print(f"  Explorer: {receipt.explorer_url}")
        print(f"  Calls:    {sp.num_calls} (swap + pay)")

        assert receipt.success, f"Atomic swap+pay failed: {receipt.error}"
        assert receipt.block > 0

    @pytest.mark.asyncio
    async def test_atomic_swap_and_multi_pay(self, submitter, accounts):
        """Swap + pay 2 recipients in one tx."""
        _, recipient = accounts
        builder = SwapPayBuilder()

        sp = builder.build_multi_pay(
            token_in=ALPHA_USD,
            token_out=PATH_USD,
            swap_amount=200_000,       # $0.20 alphaUSD
            min_swap_out=1,
            payments=[
                {"to": recipient.address, "amount": 30_000,
                 "memo": {"service": "data", "idx": 0}},
                {"to": recipient.address, "amount": 20_000,
                 "memo": {"service": "inference", "idx": 1}},
            ],
        )

        assert sp.num_calls == 3  # 1 swap + 2 pays
        receipt = await submitter.sign_and_send(sp.tx)

        print(f"\n  ATOMIC SWAP + MULTI-PAY:")
        print(f"  TX hash:  {receipt.tx_hash}")
        print(f"  Block:    {receipt.block}")
        print(f"  Calls:    {sp.num_calls} (swap + 2 payments)")
        print(f"  Status:   {'SUCCESS' if receipt.success else 'FAILED'}")
        print(f"  Explorer: {receipt.explorer_url}")

        assert receipt.success

    @pytest.mark.asyncio
    async def test_plain_swap_only(self, submitter):
        """Sanity: just a swap, no payment."""
        from pytempo import TempoTransaction
        from pytempo.contracts.dex import StablecoinDEX

        dex = StablecoinDEX()
        swap = dex.swap_exact_amount_in(
            token_in=ALPHA_USD, token_out=PATH_USD,
            amount_in=50_000, min_amount_out=1,
        )
        tx = TempoTransaction(
            chain_id=42431, calls=(swap,), gas_limit=500_000,
            max_fee_per_gas=25_000_000_000,
            max_priority_fee_per_gas=1_000_000_000,
        )
        receipt = await submitter.sign_and_send(tx)
        print(f"\n  Plain swap: {receipt.tx_hash} ({'OK' if receipt.success else 'FAIL'})")
        assert receipt.success
