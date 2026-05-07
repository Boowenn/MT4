from __future__ import annotations

import os
from typing import Any, Dict, List

from .crossover import crossover_seed
from .mutation import mutate_seed
from .schema import DEFAULT_ELITE_COUNT, DEFAULT_POPULATION_SIZE
from .seed_generator import initial_seed_pool


def population_size() -> int:
    try:
        return max(4, min(64, int(os.environ.get("QG_GA_POPULATION_SIZE", DEFAULT_POPULATION_SIZE))))
    except Exception:
        return DEFAULT_POPULATION_SIZE


def elite_count() -> int:
    try:
        return max(1, min(8, int(os.environ.get("QG_GA_ELITE_COUNT", DEFAULT_ELITE_COUNT))))
    except Exception:
        return DEFAULT_ELITE_COUNT


def build_population(generation_number: int, previous_elites: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    size = population_size()
    if generation_number <= 1 or not previous_elites:
        return initial_seed_pool(size)
    population: List[Dict[str, Any]] = []
    elites = [row.get("strategyJson") for row in previous_elites if isinstance(row.get("strategyJson"), dict)]
    population.extend(elites[: elite_count()])
    offset = 1
    while len(population) < size and elites:
        parent = elites[(offset - 1) % len(elites)]
        seed_id = f"GA-USDJPY-G{generation_number:04d}-M{offset:04d}"
        population.append(mutate_seed(parent, seed_id, generation_number, offset))
        offset += 1
        if len(elites) > 1 and len(population) < size:
            left = elites[(offset - 2) % len(elites)]
            right = elites[(offset - 1) % len(elites)]
            crossed = crossover_seed(left, right, f"GA-USDJPY-G{generation_number:04d}-C{offset:04d}", generation_number, offset)
            if crossed:
                population.append(crossed)
            offset += 1
    if len(population) < size:
        population.extend(initial_seed_pool(size - len(population)))
    return population[:size]

