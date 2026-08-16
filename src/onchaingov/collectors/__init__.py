"""Data collectors for on-chain governance research."""

from onchaingov.collectors.base import Collector, RawEvent
from onchaingov.collectors.evm_rpc import EVMRPCCollector
from onchaingov.collectors.snapshot import SnapshotCollector
from onchaingov.collectors.steemit import SteemitCollector
from onchaingov.collectors.tally import TallyCollector

__all__ = [
    "Collector",
    "EVMRPCCollector",
    "RawEvent",
    "SnapshotCollector",
    "SteemitCollector",
    "TallyCollector",
]
