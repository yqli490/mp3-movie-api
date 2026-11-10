import logging
import pandas as pd

logger = logging.getLogger(__name__)


def remove_duplicates(df):
    """Remove duplicate rows."""
    before = len(df)
    df = df.drop_duplicates()
    after = len(df)

    logger.debug(f"remove_duplicates: {before} -> {after} rows")

    return df


def handle_missing(df, axis="rows"):
    """Drop rows or columns containing missing values."""
    if axis == "rows":
        before = len(df)
        df = df.dropna()
        after = len(df)
        logger.debug(f"handle_missing: {before} -> {after} rows")
    elif axis == "columns":
        before = df.shape[1]
        df = df.dropna(axis=1)
        after = df.shape[1]
        logger.debug(f"handle_missing: {before} -> {after} columns")
    else:
        logger.error(f"Unsupported axis: {axis}")
        raise ValueError(f"Unsupported axis: {axis}")

    return df


def remove_outliers(df, columns, method, threshold):
    """Remove outliers from the specified numeric columns."""
    if method not in ["iqr", "zscore"]:
        logger.error(f"Unsupported outlier method: {method}")
        raise ValueError(f"Unsupported outlier method: {method}")

    for column in columns:
        if column not in df.columns:
            logger.warning(f"Column not found: {column}")
            continue

        if not pd.api.types.is_numeric_dtype(df[column]):
            logger.warning(f"Column not numeric: {column}")
            continue

        before = len(df)

        if method == "iqr":
            q1 = df[column].quantile(0.25)
            q3 = df[column].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr
            df = df[(df[column] >= lower) & (df[column] <= upper)]
        elif method == "zscore":
            mean = df[column].mean()
            std = df[column].std()
            z_scores = (df[column] - mean) / std
            df = df[z_scores.abs() <= threshold]

        after = len(df)
        removed = before - after

        logger.debug(f"{column}: method={method}, threshold={threshold}, removed={removed}")

    return df


def process_data(df, config):
    """Apply the processing steps enabled in the configuration."""
    processing = config["processing"]

    if processing.get("remove_duplicates"):
        df = remove_duplicates(df)

    missing = processing.get("missing", {})
    if missing.get("enabled"):
        df = handle_missing(df, axis=missing.get("axis", "rows"))

    outliers = processing.get("outliers", {})
    if outliers.get("enabled"):
        df = remove_outliers(
            df,
            columns=outliers.get("columns"),
            method=outliers.get("method"),
            threshold=outliers.get("threshold")
        )

    return df


def create_cleaning_report(df_before, df_after):
    """Return a dictionary summarizing the cleaning results."""
    rows_before = len(df_before)
    rows_after = len(df_after)
    columns_before = df_before.shape[1]
    columns_after = df_after.shape[1]

    report = {
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_removed": rows_before - rows_after,
        "columns_before": columns_before,
        "columns_after": columns_after,
        "columns_removed": columns_before - columns_after
    }

    return report