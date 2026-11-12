# MP3: Movie API with SQLite and Caching

This project is a FastAPI application that stores one movie collection in a SQLite table and serves it through a REST API. A client uploads a CSV of movies with `POST /upload`, which validates the columns and replaces the stored collection in a single transaction. `GET /movies` returns stored movies and the total count, `GET /movies/search` filters movies by minimum rating using SQL, and `POST /movies/process` validates and cleans the stored collection with the MP1 pipeline functions in `data_pipeline/`. The code is organized into `main.py` (endpoints), `src/database.py` (connections and table creation), `src/storage.py` (SQL storage and queries), `src/cache.py` (a fakeredis cache), `src/models.py`, and `src/middleware.py` (request IDs and logging). Because the data lives in SQLite, it survives a server restart. Responses from `GET /movies` are cached for 90 seconds per `limit`, and the cache is cleared after every successful upload or processing run so a client never sees outdated results.

## Run the API

```bash
python -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## Run the tests

```bash
python -m pytest tests -v
```

## Sample processing request

`POST /movies/process` after uploading `fixtures/sample_movies.csv`:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {"enabled": true, "columns": ["rating"], "method": "iqr", "threshold": 1.5}
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```