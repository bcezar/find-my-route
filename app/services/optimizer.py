from __future__ import annotations

from typing import Optional

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.config import settings

# OR-Tools works with integers; scale km values to preserve decimals
_SCALE = 1000


def optimize_route(
    distance_matrix: list[list[float]],
    start_index: int = 0,
    end_index: Optional[int] = None,
) -> list[int]:
    """Returns indices of `distance_matrix` in optimized visit order.

    If end_index is provided, the route is fixed to end at that node.
    """
    n = len(distance_matrix)
    if n <= 2:
        return list(range(n))

    int_matrix = [[round(d * _SCALE) for d in row] for row in distance_matrix]

    if end_index is not None:
        manager = pywrapcp.RoutingIndexManager(n, 1, [start_index], [end_index])
    else:
        manager = pywrapcp.RoutingIndexManager(n, 1, start_index)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_idx, to_idx):
        return int_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

    transit_cb = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    # For small routes PATH_CHEAPEST_ARC is already near-optimal; cap GLS time.
    timeout = 1 if n <= 15 else settings.tsp_timeout_seconds

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.seconds = timeout

    solution = routing.SolveWithParameters(search_params)
    if not solution:
        return list(range(n))

    order = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))

    if end_index is not None:
        order.append(manager.IndexToNode(index))

    return order
