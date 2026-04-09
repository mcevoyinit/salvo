"""Build atomic swap+pay transactions on Tempo.

One TempoTransaction with two (or more) Calls:
  1. Swap token_in → token_out via StablecoinDEX
  2. Pay recipient in token_out via TIP-20 transfer (with optional memo)

Both succeed or both revert. No contracts to deploy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pytempo import TempoTransaction, Call
from pytempo.contracts.dex import StablecoinDEX
from pytempo.contracts.tip20 import TIP20
from pytempo.contracts.addresses import (
    PATH_USD, ALPHA_USD, BETA_USD, THETA_USD, STABLECOIN_DEX_ADDRESS,
)


# ----- Default config: Tempo TESTNET (Moderato) -----
# For mainnet, override when constructing SwapPayBuilder:
#   SwapPayBuilder(chain_id=42170)
CHAIN_ID = 42431                   # testnet (Moderato)
GAS_LIMIT = 500_000
MAX_FEE = 25_000_000_000          # 25 gwei
MAX_PRIORITY_FEE = 1_000_000_000  # 1 gwei

STABLECOINS = {
    "pathUSD": PATH_USD,
    "alphaUSD": ALPHA_USD,
    "betaUSD": BETA_USD,
    "thetaUSD": THETA_USD,
}


def memo_hash(data: dict[str, Any]) -> bytes:
    """SHA-256 hash of structured metadata. 32 bytes for TIP-20 memo."""
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).digest()


@dataclass(frozen=True)
class SwapPay:
    """A built atomic swap+pay operation."""

    tx: TempoTransaction
    swap_call: Call
    pay_call: Call
    extra_calls: tuple[Call, ...] = ()
    token_in: str = ""
    token_out: str = ""
    swap_amount: int = 0
    pay_amount: int = 0
    pay_to: str = ""
    memo_data: dict[str, Any] = field(default_factory=dict)

    @property
    def num_calls(self) -> int:
        return len(self.tx.calls)

    @property
    def is_sponsored(self) -> bool:
        return self.tx.awaiting_fee_payer


class SwapPayBuilder:
    """Fluent builder for atomic swap+pay transactions."""

    def __init__(
        self,
        chain_id: int = CHAIN_ID,
        gas_limit: int = GAS_LIMIT,
        max_fee: int = MAX_FEE,
        max_priority_fee: int = MAX_PRIORITY_FEE,
    ):
        self.chain_id = chain_id
        self.gas_limit = gas_limit
        self.max_fee = max_fee
        self.max_priority_fee = max_priority_fee

    def build(
        self,
        token_in: str,
        token_out: str,
        swap_amount: int,
        min_swap_out: int,
        pay_to: str,
        pay_amount: int,
        *,
        memo: dict[str, Any] | None = None,
        nonce_key: int = 0,
        sponsored: bool = False,
        extra_calls: tuple[Call, ...] = (),
    ) -> SwapPay:
        """Build an atomic swap+pay transaction.

        Args:
            token_in: Address of token to swap from.
            token_out: Address of token to swap to.
            swap_amount: Amount of token_in to swap (base units).
            min_swap_out: Minimum acceptable token_out from swap.
            pay_to: Recipient address for the payment.
            pay_amount: Amount of token_out to pay (base units).
            memo: Optional structured metadata (hashed to 32 bytes).
            nonce_key: Parallel execution lane.
            sponsored: If True, awaiting_fee_payer=True.
            extra_calls: Additional Calls to include in the batch.
        """
        dex = StablecoinDEX()
        swap_call = dex.swap_exact_amount_in(
            token_in=token_in,
            token_out=token_out,
            amount_in=swap_amount,
            min_amount_out=min_swap_out,
        )

        tip20 = TIP20(token_out)
        if memo:
            pay_call = tip20.transfer_with_memo(
                to=pay_to, amount=pay_amount, memo=memo_hash(memo),
            )
        else:
            pay_call = tip20.transfer(to=pay_to, amount=pay_amount)

        all_calls = (swap_call, pay_call) + extra_calls

        tx = TempoTransaction(
            chain_id=self.chain_id,
            calls=all_calls,
            nonce_key=nonce_key,
            gas_limit=self.gas_limit,
            max_fee_per_gas=self.max_fee,
            max_priority_fee_per_gas=self.max_priority_fee,
            awaiting_fee_payer=sponsored,
        )

        return SwapPay(
            tx=tx,
            swap_call=swap_call,
            pay_call=pay_call,
            extra_calls=extra_calls,
            token_in=token_in,
            token_out=token_out,
            swap_amount=swap_amount,
            pay_amount=pay_amount,
            pay_to=pay_to,
            memo_data=memo or {},
        )

    def build_multi_pay(
        self,
        token_in: str,
        token_out: str,
        swap_amount: int,
        min_swap_out: int,
        payments: list[dict[str, Any]],
        *,
        nonce_key: int = 0,
        sponsored: bool = False,
    ) -> SwapPay:
        """Build an atomic swap + multiple payments.

        Each payment: {"to": addr, "amount": int, "memo": {...}}
        All succeed or all revert.
        """
        dex = StablecoinDEX()
        swap_call = dex.swap_exact_amount_in(
            token_in=token_in, token_out=token_out,
            amount_in=swap_amount, min_amount_out=min_swap_out,
        )

        tip20 = TIP20(token_out)
        pay_calls = []
        for p in payments:
            if p.get("memo"):
                call = tip20.transfer_with_memo(
                    to=p["to"], amount=p["amount"], memo=memo_hash(p["memo"]),
                )
            else:
                call = tip20.transfer(to=p["to"], amount=p["amount"])
            pay_calls.append(call)

        all_calls = (swap_call,) + tuple(pay_calls)

        tx = TempoTransaction(
            chain_id=self.chain_id,
            calls=all_calls,
            nonce_key=nonce_key,
            gas_limit=self.gas_limit,
            max_fee_per_gas=self.max_fee,
            max_priority_fee_per_gas=self.max_priority_fee,
            awaiting_fee_payer=sponsored,
        )

        return SwapPay(
            tx=tx,
            swap_call=swap_call,
            pay_call=pay_calls[0] if pay_calls else swap_call,
            extra_calls=tuple(pay_calls[1:]),
            token_in=token_in, token_out=token_out,
            swap_amount=swap_amount,
            pay_amount=sum(p["amount"] for p in payments),
            pay_to=payments[0]["to"] if payments else "",
            memo_data={"payments": len(payments)},
        )
