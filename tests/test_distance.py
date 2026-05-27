from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.distance import build_distance_matrix, haversine_km

SP_PAULISTA = (-23.5615, -46.6565)
SP_SE = (-23.5504, -46.6339)


# --- haversine (pure, sync) ---

def test_haversine_same_point():
    assert haversine_km(SP_PAULISTA, SP_PAULISTA) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    dist = haversine_km(SP_PAULISTA, SP_SE)
    assert 2.0 < dist < 4.0


def test_haversine_symmetric():
    assert haversine_km(SP_PAULISTA, SP_SE) == pytest.approx(
        haversine_km(SP_SE, SP_PAULISTA), rel=1e-6
    )


# --- build_distance_matrix (async, OSRM or Haversine fallback) ---

@pytest.mark.asyncio
async def test_build_matrix_uses_osrm_when_available():
    fake_distances = [[0, 3500, 2100], [3500, 0, 1800], [2100, 1800, 0]]
    osrm_response = {"code": "Ok", "distances": fake_distances}

    with patch("app.services.distance.settings") as mock_settings, \
         patch("app.services.distance.httpx.AsyncClient") as mock_client_cls:
        mock_settings.osrm_base_url = "http://fake-osrm"

        mock_response = MagicMock()
        mock_response.json.return_value = osrm_response
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        coords = [SP_PAULISTA, SP_SE, (-23.548, -46.638)]
        matrix = await build_distance_matrix(coords)

    # OSRM returns meters → converted to km
    assert matrix[0][1] == pytest.approx(3.5)
    assert matrix[1][2] == pytest.approx(1.8)
    assert matrix[0][0] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_build_matrix_falls_back_to_haversine_when_osrm_unavailable():
    with patch("app.services.distance.settings") as mock_settings:
        mock_settings.osrm_base_url = None

        coords = [SP_PAULISTA, SP_SE]
        matrix = await build_distance_matrix(coords)

    assert len(matrix) == 2
    assert matrix[0][0] == pytest.approx(0.0)
    assert matrix[1][1] == pytest.approx(0.0)
    assert 2.0 < matrix[0][1] < 4.0


@pytest.mark.asyncio
async def test_build_matrix_falls_back_to_haversine_on_osrm_error():
    with patch("app.services.distance.settings") as mock_settings, \
         patch("app.services.distance._osrm_matrix", new_callable=AsyncMock) as mock_osrm:
        mock_settings.osrm_base_url = "http://fake-osrm"
        mock_osrm.return_value = None  # OSRM failed

        coords = [SP_PAULISTA, SP_SE]
        matrix = await build_distance_matrix(coords)

    assert 2.0 < matrix[0][1] < 4.0


@pytest.mark.asyncio
async def test_build_matrix_shape():
    with patch("app.services.distance.settings") as mock_settings:
        mock_settings.osrm_base_url = None
        coords = [SP_PAULISTA, SP_SE, (-23.548, -46.638)]
        matrix = await build_distance_matrix(coords)

    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
