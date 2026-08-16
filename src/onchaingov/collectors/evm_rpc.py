"""EVM RPC collector for on-chain governance events (Transfer/Delegate/Vote).

This collector reads token transfer events, delegation events, and on-chain
proposal events from an EVM-compatible chain via a JSON-RPC endpoint using
the web3.py library. It is designed to be used with a contract ABI; common
ABIs for ERC-20 and governance contracts are bundled.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from onchaingov.collectors.base import Collector, RawEvent

# Minimal ERC-20 Transfer event ABI fragment
ERC20_TRANSFER_ABI = json.loads(
    """
[
  {
    "anonymous": false,
    "inputs": [
      {"indexed": true, "name": "from", "type": "address"},
      {"indexed": true, "name": "to", "type": "address"},
      {"indexed": false, "name": "value", "type": "uint256"}
    ],
    "name": "Transfer",
    "type": "event"
  }
]
"""
)


class EVMRPCCollector(Collector):
    """Collect on-chain events by scanning a contract's event logs."""

    source_name = "evm"

    def __init__(
        self,
        out_dir: str | Path | None = None,
        *,
        rpc_url: str | None = None,
        contract_address: str | None = None,
        abi: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(out_dir)
        self.rpc_url = rpc_url
        self.contract_address = contract_address
        self.abi = abi or ERC20_TRANSFER_ABI
        self._web3 = None

    def _client(self):
        if self._web3 is None:
            if self.rpc_url is None:
                raise ValueError("rpc_url is not configured")
            from web3 import Web3

            self._web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self._web3.is_connected():
                raise ConnectionError(f"Cannot connect to RPC endpoint: {self.rpc_url}")
        return self._web3

    def run(
        self,
        *,
        from_block: int,
        to_block: int | None = None,
        contract_address: str | None = None,
        event_name: str = "Transfer",
        batch_size: int = 2000,
    ) -> list[RawEvent]:
        """Scan event logs for a contract over a block range.

        Args:
            from_block: Start block (inclusive).
            to_block: End block (inclusive). Defaults to the current block.
            contract_address: Overrides the constructor-provided address.
            event_name: ABI event name to scan for.
            batch_size: Number of blocks scanned per request.

        Returns:
            List of RawEvent with event_type = event_name (lowercased).
        """
        if self.rpc_url is None:
            raise ValueError("rpc_url is not configured")
        if contract_address is None:
            contract_address = self.contract_address
        if contract_address is None:
            raise ValueError("contract_address is not configured")
        if to_block is None:
            to_block = self._client().eth.block_number

        contract = self._client().eth.contract(address=contract_address, abi=self.abi)
        events: list[RawEvent] = []
        start = from_block
        while start <= to_block:
            end = min(start + batch_size - 1, to_block)
            try:
                entries = contract.events[event_name].get_logs(fromBlock=start, toBlock=end)
            except Exception as exc:  # pragma: no cover - network dependent
                raise RuntimeError(f"get_logs failed for blocks {start}-{end}: {exc}") from exc
            for log in entries:
                events.append(
                    RawEvent(
                        source=self.source_name,
                        event_type=event_name.lower(),
                        entity_id=f"{log.transactionHash.hex()}-{log.logIndex}",
                        entity_address=self._args_to_address(log.get("args")),
                        timestamp=self._block_to_time(log.blockNumber),
                        payload={
                            "block_number": log.blockNumber,
                            "tx_hash": log.transactionHash.hex(),
                            "log_index": log.logIndex,
                            "args": {
                                k: (str(v) if hasattr(v, "hex") else v)
                                for k, v in (log.get("args") or {}).items()
                            },
                        },
                        raw=dict(log),
                    )
                )
            if end >= to_block:
                break
            start = end + 1
        return events

    def _block_to_time(self, block_number: int) -> datetime:
        block = self._client().eth.get_block(block_number)
        return datetime.fromtimestamp(block.timestamp, tz=timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _args_to_address(args: Any) -> str | None:
        if not args:
            return None
        to = args.get("to") or args.get("voter") or args.get("from")
        return to if isinstance(to, str) else None
