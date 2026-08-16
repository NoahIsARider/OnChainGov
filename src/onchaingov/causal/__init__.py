"""Causal inference templates: DID, PSM-DID, placebo, event study."""

from onchaingov.causal.did import DIDResult, did_estimate
from onchaingov.causal.event_study import EventStudyResult, event_study_estimate
from onchaingov.causal.placebo import PlaceboResult, in_space_placebo, in_time_placebo
from onchaingov.causal.psm_did import (
    MatchResult,
    match_units,
    propensity_scores,
    psm_did_estimate,
)

__all__ = [
    "DIDResult",
    "EventStudyResult",
    "MatchResult",
    "PlaceboResult",
    "did_estimate",
    "event_study_estimate",
    "in_space_placebo",
    "in_time_placebo",
    "match_units",
    "propensity_scores",
    "psm_did_estimate",
]
