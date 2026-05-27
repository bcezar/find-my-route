from app.services.optimizer import optimize_route


def test_optimize_two_points():
    matrix = [[0.0, 1.0], [1.0, 0.0]]
    order = optimize_route(matrix, start_index=0)
    assert order == [0, 1]


def test_optimize_returns_all_indices():
    matrix = [
        [0.0, 1.0, 5.0],
        [1.0, 0.0, 2.0],
        [5.0, 2.0, 0.0],
    ]
    order = optimize_route(matrix, start_index=0)
    assert sorted(order) == [0, 1, 2]


def test_optimize_starts_at_given_index():
    matrix = [
        [0.0, 1.0, 5.0],
        [1.0, 0.0, 2.0],
        [5.0, 2.0, 0.0],
    ]
    order = optimize_route(matrix, start_index=1)
    assert order[0] == 1


def test_optimize_known_shortest():
    # 0 -> 1 (1 km) -> 2 (2 km) = 3 km total (optimal)
    # 0 -> 2 (5 km) -> 1 (2 km) = 7 km (suboptimal)
    matrix = [
        [0.0, 1.0, 5.0],
        [1.0, 0.0, 2.0],
        [5.0, 2.0, 0.0],
    ]
    order = optimize_route(matrix, start_index=0)
    assert order == [0, 1, 2]


def test_optimize_with_fixed_end():
    # 4 nodes: start=0, end=3, visit 1 and 2 in between
    # optimal: 0 -> 1 (1) -> 2 (2) -> 3 (1) = 4 km
    # suboptimal: 0 -> 2 (5) -> 1 (2) -> 3 (4) = 11 km
    matrix = [
        [0.0, 1.0, 5.0, 9.0],
        [1.0, 0.0, 2.0, 4.0],
        [5.0, 2.0, 0.0, 1.0],
        [9.0, 4.0, 1.0, 0.0],
    ]
    order = optimize_route(matrix, start_index=0, end_index=3)
    assert order[0] == 0
    assert order[-1] == 3
    assert sorted(order) == [0, 1, 2, 3]


def test_optimize_return_to_origin():
    # start=0, end=4 (duplicate of 0 — same coords, different index)
    matrix = [
        [0.0, 1.0, 5.0, 0.0],
        [1.0, 0.0, 2.0, 1.0],
        [5.0, 2.0, 0.0, 5.0],
        [0.0, 1.0, 5.0, 0.0],
    ]
    order = optimize_route(matrix, start_index=0, end_index=3)
    assert order[0] == 0
    assert order[-1] == 3
