"""Policy registry: policy name -> dispatch fn(station, series).

Every policy returns the same schema as dispatch_greedy (see agents/prompts/add-policy.md).
Registering a new policy here makes it available to run.py and future services.
"""

from __future__ import annotations

from typing import Any, Callable

from src.dispatch_dumb import dispatch_dumb
from src.dispatch_greedy import dispatch_greedy
from src.dispatch_opt import dispatch_opt

REGISTRY: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "dumb": dispatch_dumb,
    "greedy": dispatch_greedy,
    "milp": dispatch_opt,
}


def get_policy(name: str) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]:
    return REGISTRY[name]
