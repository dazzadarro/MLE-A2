from datetime import datetime
from pathlib import Path

import pyspark.sql.functions as F


def parse_first_of_month_dates(start_date_str: str, end_date_str: str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    if start_date.day != 1 or end_date.day != 1:
        raise ValueError("Start and end dates must be first day of the month, in YYYY-MM-DD format.")

    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime("%Y-%m-%d"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return dates


def ensure_directory(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def validate_expected_columns(df, expected_columns, source_path):
    actual_columns = df.columns
    missing = [c for c in expected_columns if c not in actual_columns]
    extra = [c for c in actual_columns if c not in expected_columns]

    if missing:
        raise ValueError(
            f"Header validation failed for {source_path}. Missing columns: {missing}"
        )

    if extra:
        print(
            f"Warning: unexpected columns present in {source_path}: {extra}. "
            f"Pipeline will continue with expected columns."
        )


def validate_unique_keys(df, key_columns, table_name):
    if not key_columns:
        return

    duplicate_example = (
        df.groupBy(*key_columns)
        .count()
        .filter(F.col("count") > 1)
        .limit(1)
        .collect()
    )
    if duplicate_example:
        raise ValueError(
            f"Duplicate key values found in {table_name} for keys {key_columns}"
        )


def log_dataframe_profile(df, table_name, snapshot_date_str, numeric_columns=None, key_columns=None):
    print(f"\n=== Profile for {table_name} snapshot {snapshot_date_str} ===")
    print(f"Total rows: {df.count():,}")
    print("Schema:")
    df.printSchema()

    columns = df.columns
    null_blank_exprs = []
    for column_name in columns:
        null_blank_exprs.append(
            F.sum(
                F.when(
                    F.col(column_name).isNull()
                    | (F.trim(F.col(column_name).cast("string")) == ""),
                    1,
                ).otherwise(0)
            ).alias(column_name)
        )

    if null_blank_exprs:
        print("Null / blank counts:")
        df.select(*null_blank_exprs).show(1, truncate=False)

    if key_columns:
        print(f"Validating unique key columns: {key_columns}")
        try:
            validate_unique_keys(df, key_columns, table_name)
            print("Unique key validation passed.")
        except ValueError as error:
            print(f"Key validation warning: {error}")

    if numeric_columns:
        existing_numeric_columns = [c for c in numeric_columns if c in columns]
        if existing_numeric_columns:
            print("Numeric summary statistics:")
            stats = df.select(*[
                F.mean(F.col(c).cast("double")).alias(c)
                for c in existing_numeric_columns
            ] + [
                F.stddev(F.col(c).cast("double")).alias(f"{c}_stddev")
                for c in existing_numeric_columns
            ])
            stats.show(truncate=False)
            for column_name in existing_numeric_columns:
                numeric_df = df.select(F.col(column_name).cast("double").alias(column_name))
                non_null_df = numeric_df.filter(F.col(column_name).isNotNull())
                if non_null_df.rdd.isEmpty():
                    print(f"Skipping quantiles for {column_name}: no convertible numeric values")
                    continue
                quantiles = non_null_df.approxQuantile(column_name, [0.25, 0.5, 0.75], 0.05)
                if len(quantiles) == 3:
                    q1, q2, q3 = quantiles
                    iqr = q3 - q1
                    lower = q1 - 1.5 * iqr
                    upper = q3 + 1.5 * iqr
                    outlier_count = non_null_df.filter(
                        (F.col(column_name) < lower) | (F.col(column_name) > upper)
                    ).count()
                    print(
                        f"{column_name}: q1={q1}, median={q2}, q3={q3}, "
                        f"lower={lower}, upper={upper}, outliers={outlier_count}"
                    )

    print(f"=== End profile for {table_name} snapshot {snapshot_date_str} ===\n")
