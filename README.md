# salvo

> *sal·vo* — a simultaneous discharge of multiple pieces; all guns fired at once.

Atomic swap+pay on [Tempo](https://tempo.xyz). Multiple economic actions, one transaction.

## Live on mainnet

```
3 payments in 1 atomic tx ($1.00 + $0.50 + $0.25), each with provenance hash:
  https://explore.tempo.xyz/tx/0x40a47a91d59527e09b9ba9fb9c4e7459df5720808d1b503ca1f705f974996478

pathUSD transfer with SHA-256 memo on mainnet:
  https://explore.tempo.xyz/tx/0xfb6c9d7cf5b98a49fea06188abb28561720d9acae93930f0faba42aff4d2cc27
```

Also on testnet (swap+pay):

```
Swap AlphaUSD→pathUSD + pay with memo (2 calls, 1 tx):
  https://explore.moderato.tempo.xyz/tx/0xe467a6baffb7e892790b2822172b7392cca323a70f047bb42bb08067ce40884a

Swap + pay 2 recipients (3 calls, 1 tx):
  https://explore.moderato.tempo.xyz/tx/0x8def5b04de33b12bae764967dfc8a38edc8a0472afb97df5428849669345b8f9
```

Click those. Multiple calls in one block. All succeed or all revert. Real money.

## Why this exists

AI agents that pay for services face a basic problem: they hold one token but owe another. On Ethereum, that's two transactions — a swap and then a payment — with a gap in between where the price can move, the second tx can fail, or the agent runs out of gas.

On Tempo, the 0x76 transaction type lets you batch multiple operations into a single atomic unit. Salvo uses this to combine a stablecoin swap and a service payment into one transaction. The swap converts the token, the payment settles the bill, and a SHA-256 memo hash links the whole thing to the task that triggered it. If any part fails, everything reverts.

No smart contracts to deploy. No multicall routers. No keeper infrastructure. Just two `Call` objects in a tuple.

The same atomicity is achievable elsewhere — Ethereum via multicall or ERC-4337 bundlers, Solana via instruction composition. What Tempo gives you on top is native fee sponsorship as a transaction flag, stablecoin-native gas, and sub-cent settlement, so the pattern is practical for agent-scale workloads rather than something you reach for once and amortize. x402 is the exception: it's one tx per request by spec, so this particular flow doesn't fit.

## What it does

```python
from salvo import SwapPayBuilder
from pytempo.contracts.addresses import ALPHA_USD, PATH_USD

sp = SwapPayBuilder().build(
    token_in=ALPHA_USD,
    token_out=PATH_USD,
    swap_amount=1_000_000,     # $1 alphaUSD in
    min_swap_out=990_000,      # accept 1% slippage
    pay_to="0xRecipient",
    pay_amount=990_000,        # pay $0.99 pathUSD
    memo={"task": "research", "agent": "a1", "confidence": 0.92},
)

# sp.tx is a TempoTransaction with 2 calls — sign and submit
receipt = await submitter.sign_and_send(sp.tx)
print(receipt.explorer_url)
```

The swap uses Tempo's native `StablecoinDEX`. The payment uses `TIP20.transfer_with_memo()` with a 32-byte SHA-256 hash of your structured metadata. The full JSON lives off-chain; the hash on-chain proves the link.

### Multi-party settlement

Swap once, pay several parties. All or nothing.

```python
sp = SwapPayBuilder().build_multi_pay(
    token_in=ALPHA_USD, token_out=PATH_USD,
    swap_amount=5_000_000, min_swap_out=4_900_000,
    payments=[
        {"to": data_provider, "amount": 2_000_000, "memo": {"service": "search"}},
        {"to": model_provider, "amount": 1_500_000, "memo": {"service": "inference"}},
        {"to": treasury, "amount": 1_000_000, "memo": {"type": "platform_fee"}},
    ],
)
# 4 calls in 1 tx: swap + 3 payments
```

### Fee sponsorship

Agents don't need gas. The master pays.

```python
sp = SwapPayBuilder().build(
    ...,
    sponsored=True,  # awaiting_fee_payer=True
)
```

## Use cases

**Just-in-time treasury.** Agent holds USDC but a service wants pathUSD. Instead of pre-converting and holding idle balances, the agent swaps and pays in one shot. No leftover dust, no wasted capital.

**Conditional payment.** The swap acts as a price check. If the exchange rate is bad (slippage exceeds your limit), the whole tx reverts — including the payment. The agent never overpays because a bad swap kills the entire operation.

**Atomic multi-party settlement.** A research swarm completes a task: the data provider, the model provider, and the platform treasury all get paid in one transaction. If any payment fails, none go through. No partial settlements, no reconciliation headaches.

## Tempo primitives used

| Primitive | What salvo does with it |
|-----------|------------------------|
| `TempoTransaction.calls` | Batch swap + payment(s) into one atomic tx |
| `StablecoinDEX.swap_exact_amount_in()` | Convert between any TIP-20 stablecoins |
| `TIP20.transfer_with_memo()` | Pay with a 32-byte provenance hash |
| `awaiting_fee_payer` | Let a sponsor pay gas — agents hold zero native tokens |
| `nonce_key` | Parallel execution lanes for concurrent agents |

## Install

```bash
pip install salvo
```

From source:

```bash
git clone https://github.com/mcevoyinit/salvo.git
cd salvo
pip install -e ".[dev]"
pytest tests/ -v  # 30 tests
```

## Testnet

Tempo Moderato testnet. Fund your wallet for free:

```bash
curl -X POST https://rpc.moderato.tempo.xyz \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tempo_fundAddress","params":["YOUR_ADDRESS"],"id":1}'
```

Note: you need to approve the StablecoinDEX to spend your tokens before swapping. See `tests/test_live.py` for the approval flow.

## Related

- [Maestro](https://github.com/mcevoyinit/maestro) — zero-gas agent orchestrator (session keys, fee sponsorship, parallel execution)
- [Parley](https://github.com/mcevoyinit/parley) — tiered pricing for MPP endpoints
- [Agent Treaty](https://github.com/mcevoyinit/tempo-agent-treaty) — multi-field OTC negotiation between agents

## License

MIT
