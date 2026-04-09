"""Sign and submit transactions to Tempo RPC."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pytempo import TempoTransaction
from mpp.methods.tempo import TempoAccount

logger = logging.getLogger(__name__)

RPC_URL = "https://rpc.tempo.xyz"

# Explorer URL by RPC endpoint. Mainnet RPC → mainnet explorer, else testnet.
_EXPLORER_MAP = {
    "https://rpc.tempo.xyz": "https://explore.tempo.xyz/tx",
    "https://rpc.moderato.tempo.xyz": "https://explore.moderato.tempo.xyz/tx",
}
_DEFAULT_EXPLORER = "https://explore.moderato.tempo.xyz/tx"


def _explorer_for_rpc(rpc_url: str) -> str:
    """Derive the block explorer base URL from the RPC endpoint."""
    return _EXPLORER_MAP.get(rpc_url.rstrip("/"), _DEFAULT_EXPLORER)


class TxReceipt:
    def __init__(self, tx_hash: str, explorer_base: str = _DEFAULT_EXPLORER,
                 success: bool = False, block: int = 0,
                 gas_used: int = 0, error: str = "", raw: dict | None = None):
        self.tx_hash = tx_hash
        self._explorer_base = explorer_base
        self.success = success
        self.block = block
        self.gas_used = gas_used
        self.error = error
        self.raw = raw or {}

    @property
    def explorer_url(self) -> str:
        return f"{self._explorer_base}/{self.tx_hash}"

    def __repr__(self) -> str:
        s = "OK" if self.success else "FAIL"
        return f"TxReceipt({s}, block={self.block}, hash={self.tx_hash[:18]}...)"


class TxSubmitter:
    def __init__(self, account: TempoAccount, rpc_url: str = RPC_URL):
        self.account = account
        self.rpc_url = rpc_url
        self._explorer_base = _explorer_for_rpc(rpc_url)

    async def sign_and_send(self, tx: TempoTransaction) -> TxReceipt:
        if tx.nonce == 0:
            nonce = await self._get_nonce()
            tx = TempoTransaction(
                chain_id=tx.chain_id,
                calls=tx.calls,
                nonce_key=tx.nonce_key,
                nonce=nonce,
                gas_limit=tx.gas_limit,
                max_fee_per_gas=tx.max_fee_per_gas,
                max_priority_fee_per_gas=tx.max_priority_fee_per_gas,
                awaiting_fee_payer=tx.awaiting_fee_payer,
                valid_after=tx.valid_after,
                valid_before=tx.valid_before,
                fee_token=tx.fee_token,
                access_list=tx.access_list,
                tempo_authorization_list=tx.tempo_authorization_list,
                key_authorization=tx.key_authorization,
                sender_address=tx.sender_address,
            )

        signed = tx.sign(self.account.private_key)
        raw_hex = "0x" + signed.encode().hex()
        tx_hash = await self._rpc("eth_sendRawTransaction", [raw_hex])
        logger.info(f"Submitted: {tx_hash}")
        receipt = await self._wait_receipt(tx_hash)
        return receipt

    async def fund(self, address: str | None = None) -> list[str]:
        return await self._rpc("tempo_fundAddress", [address or self.account.address])

    async def balance(self, token: str, account: str | None = None) -> int:
        addr = (account or self.account.address).lower().replace("0x", "").zfill(64)
        result = await self._rpc("eth_call", [{"to": token, "data": "0x70a08231" + addr}, "latest"])
        return int(result, 16)

    async def _get_nonce(self) -> int:
        result = await self._rpc("eth_getTransactionCount", [self.account.address, "latest"])
        return int(result, 16)

    async def _wait_receipt(self, tx_hash: str, tries: int = 30) -> TxReceipt:
        for _ in range(tries):
            r = await self._rpc("eth_getTransactionReceipt", [tx_hash], null_ok=True)
            if r is not None:
                return TxReceipt(
                    tx_hash=tx_hash,
                    explorer_base=self._explorer_base,
                    success=int(r.get("status", "0x0"), 16) == 1,
                    block=int(r.get("blockNumber", "0x0"), 16),
                    gas_used=int(r.get("gasUsed", "0x0"), 16),
                    raw=r,
                )
            await asyncio.sleep(1)
        return TxReceipt(tx_hash=tx_hash, explorer_base=self._explorer_base, error="timeout")

    async def _rpc(self, method: str, params: list, null_ok: bool = False) -> Any:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(self.rpc_url, json={
                "jsonrpc": "2.0", "method": method, "params": params, "id": 1,
            })
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC {method}: {data['error'].get('message', data['error'])}")
        result = data.get("result")
        if result is None and not null_ok:
            raise RuntimeError(f"RPC {method}: null result")
        return result
