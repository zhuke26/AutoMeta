import re


def test_packaged_index_references_fastapi_static_assets(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert re.search(r'src="/static/assets/index-[^"]+\.js"', response.text)
    assert re.search(r'href="/static/assets/index-[^"]+\.css"', response.text)


def test_client_side_routes_fall_back_to_uncached_index(client) -> None:
    response = client.get("/reviews/local-review/extraction")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert '<div id="root"></div>' in response.text


def test_hashed_assets_are_cached_as_immutable(client) -> None:
    index = client.get("/").text
    asset_path = re.search(r'src="(/static/assets/index-[^"]+\.js)"', index)
    assert asset_path is not None

    response = client.get(asset_path.group(1))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_unknown_api_route_is_not_served_by_spa_fallback(client) -> None:
    response = client.get("/api/v1/not-a-real-endpoint")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
