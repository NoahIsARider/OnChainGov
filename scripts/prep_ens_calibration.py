#!/usr/bin/env python3
"""Prepare ENS DAO calibration + counterfactual datasets for MatchaFlow DAO.

Reads OnChainGov raw snapshot events for ens.eth, computes participation &
concentration metrics (incl. vp-weighted HHI/Gini/top-share), and writes:
  - baseline ENS calibration parquet (compatible with dao/dao_calibration.py)
  - counterfactual "low-participation ENS" parquet (voter subset)
Output goes to the OnChainGov data dir; the case study lives in MatchaFlow.
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

REPO = '/home/ubuntu/.openclaw/workspace/noah-space/onchaingov-review/workspace'
RAW = os.path.join(REPO, 'data/raw/snapshot_ens.eth.parquet')
OUT = os.path.join(REPO, 'data/indicators')


def _p(r):
    """parse payload/raw cell (dict or JSON string)."""
    if isinstance(r, dict):
        return r
    if isinstance(r, str):
        try:
            return json.loads(r)
        except Exception:
            return {}
    return {}


def load_events():
    df = pd.read_parquet(RAW)
    proposals = df[df['event_type'] == 'proposal']
    votes = df[df['event_type'] == 'vote']
    return proposals, votes


def metrics(proposals, votes):
    """participation + concentration metrics (OnChainGov-compatible + vp-based)."""
    n_prop = len(proposals)
    n_voters = votes['entity_address'].nunique()
    n_votes = len(votes)
    avg_votes_per_proposal = n_votes / n_prop if n_prop else 0.0
    voting_intensity = n_votes / n_voters if n_voters else 0.0

    # vp-weighted concentration
    vp = votes.groupby('entity_address')['raw'].apply(
        lambda s: s.apply(lambda x: _p(x).get('vp', 0.0)).sum())
    shares = vp.values / vp.values.sum() if vp.sum() > 0 else np.zeros(len(vp))
    hhi = float((shares ** 2).sum())
    gini = _gini(shares)
    top10 = float(np.sort(shares)[::-1][:max(1, len(shares) // 10)].sum())
    top1 = float(np.sort(shares)[::-1][:1].sum())
    eff_n = 1.0 / hhi if hhi > 0 else float(len(shares))

    return {
        'space_id': 'ens.eth',
        'vote_count': int(n_votes),
        'voter_count': int(n_voters),
        'proposal_count': int(n_prop),
        'participation_rate': np.nan,
        'voting_intensity': float(voting_intensity),
        'avg_votes_per_proposal': float(avg_votes_per_proposal),
        'hhi': hhi,
        'gini': gini,
        'top10_share': top10,
        'top1_share': top1,
        'effective_voter_count': eff_n,
    }


def _gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    cum = np.cumsum(x) / x.sum()
    return float((n + 1 - 2 * np.sum(cum)) / n)


def main():
    proposals, votes = load_events()
    m = metrics(proposals, votes)
    print('=== ENS baseline ===')
    for k, v in m.items():
        print(f'  {k}: {v}')

    df = pd.DataFrame([m])
    df.to_parquet(os.path.join(OUT, 'snapshot_ens.eth_participation.parquet'), index=False)
    print(f'\nwrote {OUT}/snapshot_ens.eth_participation.parquet')

    # ---- counterfactual: low-participation ENS (only voters with few votes) ----
    vc = votes.groupby('entity_address')['entity_id'].count().sort_values()
    low_voters = vc.index[:40]  # bottom-40 most active voters (light participation)
    votes_low = votes[votes['entity_address'].isin(low_voters)]
    # proposals: keep those with >= 5 votes in the low subset
    prop_counts = votes_low.groupby(
        votes_low['raw'].apply(lambda x: _p(x).get('proposal_id', '')))['entity_id'].count()
    active_props = set(prop_counts[prop_counts >= 5].index)
    votes_low2 = votes_low[votes_low['raw'].apply(lambda x: _p(x).get('proposal_id', '')).isin(active_props)]

    m2 = dict(metrics(proposals, votes_low2))
    m2['space_id'] = 'ens.eth_lowpart'
    print('\n=== ENS counterfactual (low participation) ===')
    for k, v in m2.items():
        print(f'  {k}: {v}')
    pd.DataFrame([m2]).to_parquet(
        os.path.join(OUT, 'snapshot_ens.eth_lowpart_participation.parquet'), index=False)
    print(f'wrote {OUT}/snapshot_ens.eth_lowpart_participation.parquet')

    # ---- calibration dump (for MatchaFlow dao_calibration) ----
    cal = {
        'ens.eth': {
            'participation_level': 'high' if m['avg_votes_per_proposal'] > 15 else ('medium' if m['avg_votes_per_proposal'] > 5 else 'low'),
            'concentration_level': 'low' if m['hhi'] < 0.1 else ('medium' if m['hhi'] < 0.3 else 'high'),
            'hhi': m['hhi'], 'gini': m['gini'], 'top10_share': m['top10_share'],
            'top1_share': m['top1_share'],
        },
        'ens.eth_lowpart': {
            'participation_level': 'high' if m2['avg_votes_per_proposal'] > 15 else ('medium' if m2['avg_votes_per_proposal'] > 5 else 'low'),
            'concentration_level': 'low' if m2['hhi'] < 0.1 else ('medium' if m2['hhi'] < 0.3 else 'high'),
            'hhi': m2['hhi'], 'gini': m2['gini'], 'top10_share': m2['top10_share'],
            'top1_share': m2['top1_share'],
        },
    }
    with open(os.path.join(OUT, 'ens_calibration.json'), 'w') as f:
        json.dump(cal, f, indent=2, ensure_ascii=False)
    print(f'wrote {OUT}/ens_calibration.json')


if __name__ == '__main__':
    main()
