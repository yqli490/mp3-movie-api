import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movie API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a CSV upload and replace the stored movie collection."""
    extension = Path(file.filename or "").suffix.lower()
    if extension != ".csv":
        logger.warning(f"Unsupported file format: {extension}")
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    contents = await file.read()

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
        logger.warning(f"Cannot read CSV: {error}")
        raise HTTPException(status_code=400, detail="Cannot read the uploaded CSV")

    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        logger.warning(f"Unexpected columns: {list(df.columns)}")
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have exactly these columns: {MOVIE_COLUMNS}"
        )

    if df.empty:
        logger.warning("Uploaded CSV has no data rows")
        raise HTTPException(status_code=400, detail="CSV contains no data rows")

    df = df[MOVIE_COLUMNS]

    storage.save(df)
    cache.invalidate()
    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")

    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": df.shape[1],
        "column_names": list(df.columns),
    }


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies and the total count."""
    cached = cache.get(limit)
    if cached is not None:
        logger.info(f"Retrieved movies from cache: returned_rows={len(cached['data'])}")
        return cached

    data = storage.select_columns(MOVIE_COLUMNS, limit)
    total_rows = storage.count_movies()
    response = {"data": data, "total_rows": total_rows}
    cache.set(limit, response)

    logger.info(f"Retrieved movies: returned_rows={len(data)}")
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1)
):
    """Return selected fields for movies at or above a minimum rating."""
    try:
        results = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    logger.info(
        f"Queried movies: columns={columns}, min_rating={min_rating}, "
        f"returned_rows={len(results)}"
    )
    return results


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies using MP1 functions."""
    df = storage.get()
    if df.empty:
        logger.warning("No movies to process")
        raise HTTPException(
            status_code=400, detail="No movies stored; upload a CSV first"
        )

    settings = config.model_dump()
    required_columns = settings["validation"]["required_columns"]
    numeric_columns = settings["validation"]["numeric_columns"]

    for col in numeric_columns:
        if col not in df.columns:
            logger.warning(f"Numeric column not found: {col}")
            raise HTTPException(
                status_code=400, detail=f"Numeric column not found: {col}"
            )

    try:
        validated = validate_dataframe(df, required_columns, numeric_columns)
        validation_rows_removed = len(df) - len(validated)
        validated_copy = validated.copy()

        processed = process_data(validated, settings)
        report = create_cleaning_report(validated_copy, processed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    storage.save(processed)
    cache.invalidate()

    logger.info(
        f"Processed movies: validation_removed={validation_rows_removed}, "
        f"rows_before={report['rows_before']}, rows_after={report['rows_after']}"
    )

    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": report,
    }