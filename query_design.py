"""Separate comparable anchor queries from seeded exploratory queries."""

import random


def period_terms(core: list[str], exploratory: list[str], budget: int, seed: int, period: int) -> list[tuple[str, str]]:
    """Keep anchors every period and draw optional terms without replacement.

    The plan is deterministic for a given period and seed. Only anchor-query
    results should be used for direct comparisons between periods.
    """
    budget = max(1, int(budget))
    fixed = list(dict.fromkeys(term for term in core if term))[:budget]
    fixed_keys = {term.casefold() for term in fixed}
    pool = list(dict.fromkeys(term for term in exploratory if term and term.casefold() not in fixed_keys))
    rng = random.Random(f"{seed}:{period}")
    sampled = rng.sample(pool, min(budget - len(fixed), len(pool)))
    return [(term, "anchor") for term in fixed] + [(term, "exploratory") for term in sampled]
