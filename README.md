# flashpay

Atomic swap+pay on [Tempo](https://tempo.xyz). Convert stablecoins and settle a payment in one transaction.

## Live on testnet

```
Swap AlphaUSD→pathUSD + pay recipient (2 calls, 1 tx):
  https://explore.moderato.tempo.xyz/tx/0xe467a6baffb7e892790b2822172b7392cca323a70f047bb42bb08067ce40884a

Swap + pay 2 recipients (3 calls, 1 tx):
  https://explore.moderato.tempo.xyz/tx/0x8def5b04de33b12bae764967dfc8a38edc8a0472afb97df5428849669345b8f9
```

## What it does

Builds a single `TempoTransaction` with two calls:

1. `StablecoinDEX.swap_exact_amount_in()` — convert token A to token B
2. `TIP20.transfer_with_memo()` — pay a recipient in token B with a provenance hash

Both succeed or both revert. If the swap fails (bad rate, no liquidity), the payment never happens. If the payment fails (insufficient balance post-swap), the swap rolls back.

On Ethereum you'd need a custom router contract for this. On Tempo it's two Call objects in a tuple.

```python
from flashpay import SwapPayBuilder

sp = SwapPayBuilder().build(
    token_in=ALPHA_USD,
    token_out=PATH_USD,
    swap_amount=1_000_000,     # $1 alphaUSD in
    min_swap_out=990_000,      # accept 1% slippage
    pay_to="0xRecipient",
    pay_amount=990_000,        # pay $0.99 pathUSD
    memo={"task": "research", "agent": "a1"},
)

# sp.tx is a TempoTransaction with 2 calls — sign and submit
```

Multi-party settlement in one atomic tx:

```python
sp = SwapPayBuilder().build_multi_pay(
    token_in=ALPHA_USD, token_out=PATH_USD,
    swap_amount=5_000_000, min_swap_out=4_900_000,
    payments=[
        {"to": provider_a, "amount": 2_000_000, "memo": {"service": "data"}},
        {"to": provider_b, "amount": 1_500_000, "memo": {"service": "inference"}},
        {"to": treasury,   "amount": 1_000_000, "memo": {"type": "fee"}},
    ],
)
# 4 calls in 1 tx: swap + 3 payments. All or nothing.
```

## Install

```bash
pip install flashpay
```

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Related

- [Maestro](https://github.com/mcevoyinit/maestro) — zero-gas agent orchestrator (session keys, fee sponsorship)
- [Parley](https://github.com/mcevoyinit/parley) — tiered pricing for MPP endpoints

## License

MIT
