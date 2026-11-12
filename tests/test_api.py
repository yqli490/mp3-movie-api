from pathlib import Path

import pandas as pd
import pytest

import main
from src import MovieStorage


def test_movies_persist(client, test_storage, uploaded_movies):
    # A second storage object on the same file proves the data is on disk.
    reopened = MovieStorage(test_storage.db_path)
    movies = reopened.get()

    original = pd.read_csv(Path("fixtures") / "sample_movies.csv")

    assert len(movies) == 20
    assert reopened.count_movies() == 20
    assert list(movies.columns) == ["title", "release_year", "rating", "genre"]
    assert movies["title"].tolist() == original["title"].tolist()

    stored = reopened.select_columns(["title"], limit=100)
    stored_ids = [row["id"] for row in stored]

    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    api_ids = [row["id"] for row in response.json()["data"]]

    assert stored_ids == list(range(1, 21))
    assert api_ids == list(range(1, 21))


def test_cache_and_processing(client, uploaded_movies, processing_body):
    # Fill the cache for two different limits.
    first_responses = {}
    for limit in (100, 1):
        response = client.get("/movies", params={"limit": limit})
        assert response.status_code == 200
        assert main.cache.get(limit) == response.json()
        first_responses[limit] = response.json()

    # Repeating limit=100 returns the same cached response.
    repeat = client.get("/movies", params={"limit": 100})
    assert repeat.status_code == 200
    assert repeat.json() == first_responses[100]

    # Processing clears every cached entry.
    response = client.post("/movies/process", json=processing_body)
    assert response.status_code == 200
    body = response.json()
    assert body["validation_rows_removed"] == 0
    assert body["cleaning_report"]["rows_before"] == 20
    assert body["cleaning_report"]["rows_after"] == 16
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    # The next retrieval shows the updated data and is cached again.
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 16

    titles = [row["title"] for row in body["data"]]
    ids = [row["id"] for row in body["data"]]
    assert titles == [f"Movie {chr(ord('A') + i)}" for i in range(16)]
    assert ids == list(range(1, 17))
    assert main.cache.get(100) == body


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    def fail_if_called(*args, **kwargs):
        pytest.fail("A cache hit should not query the database")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)

    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == first.json()