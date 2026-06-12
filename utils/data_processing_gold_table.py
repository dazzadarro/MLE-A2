import math
import re
from pathlib import Path

import pyspark.sql.functions as F
from pyspark.sql import Row
from pyspark.sql.functions import col
from pyspark.sql.types import DoubleType, StringType, StructField, StructType


LEAKAGE_COLUMNS = {
    "due_amt",
    "paid_amt",
    "overdue_amt",
    "balance",
    "installments_missed",
    "first_missed_date",
    "dpd",
}

ID_DATE_SPLIT_COLUMNS = {
    "loan_id",
    "Customer_ID",
    "loan_start_date",
    "snapshot_date",
    "data_split",
}

# Keep categorical encoding intentionally small for assignment runtime and readability.
# Occupation can be high cardinality, so it is capped to the top N train categories.
MAX_CATEGORIES_PER_FEATURE = 10


def _read_silver(project_dir, table_name, spark):
    path = Path(project_dir) / "datamart" / "silver" / table_name
    return spark.read.parquet(str(path))


def _safe_divide(numerator, denominator):
    return F.when((denominator.isNotNull()) & (denominator != 0), numerator / denominator).otherwise(None)


def _credit_history_months(column_name):
    years = F.regexp_extract(col(column_name).cast(StringType()), r"(\d+)\s+Years?", 1)
    months = F.regexp_extract(col(column_name).cast(StringType()), r"(\d+)\s+Months?", 1)
    years_num = F.when(years == "", 0).otherwise(years.cast("int"))
    months_num = F.when(months == "", 0).otherwise(months.cast("int"))
    return years_num * 12 + months_num


def _loan_type_count(column_name):
    clean_text = F.regexp_replace(col(column_name).cast(StringType()), r"\s+and\s+", ", ")
    return F.when(col(column_name).isNull(), 0).otherwise(F.size(F.split(clean_text, ",")))


def _clean_category_expr(column_name):
    value = F.trim(col(column_name).cast(StringType()))
    return (
        F.when(value.isNull() | value.isin("", "_", "!@9#%8", "nan", "None", "null"), "Unknown")
        .when(F.regexp_replace(value, "_", "") == "", "Unknown")
        .otherwise(value)
    )


def _sanitize_token(value):
    value = str(value)
    value = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    return value[:80] or "Unknown"


def _materialize_parquet(df, path, partition_cols=None):
    """Write then re-read to cut long Spark lineage before expensive downstream work."""
    writer = df.write.mode("overwrite")
    if partition_cols:
        writer = writer.partitionBy(*partition_cols)
    writer.parquet(str(path))
    return df.sparkSession.read.parquet(str(path))


def build_loan_daily(lms):
    """Derive repayment performance fields for labels only."""
    return (
        lms.withColumn("mob", col("installment_num"))
        .withColumn(
            "installments_missed",
            F.when(
                (col("due_amt").isNotNull()) & (col("due_amt") > 0) & (col("overdue_amt") > 0),
                F.ceil(col("overdue_amt") / col("due_amt")),
            ).otherwise(F.lit(0)).cast("int"),
        )
        .withColumn(
            "first_missed_date",
            F.when(col("installments_missed") > 0, F.add_months(col("snapshot_date"), -1 * col("installments_missed"))),
        )
        .withColumn(
            "dpd",
            F.when(col("installments_missed") > 0, F.datediff(col("snapshot_date"), col("first_missed_date")))
            .otherwise(F.lit(0))
            .cast("int"),
        )
    )


def build_loan_application(lms, start_date=None, end_date=None):
    loan_application = (
        lms.filter(col("installment_num") == 0)
        .select("loan_id", "Customer_ID", "loan_start_date", "snapshot_date", "tenure", "loan_amt")
        .dropDuplicates(["loan_id"])
    )
    if start_date:
        loan_application = loan_application.filter(col("snapshot_date") >= F.to_date(F.lit(start_date)))
    if end_date:
        loan_application = loan_application.filter(col("snapshot_date") <= F.to_date(F.lit(end_date)))
    return loan_application


def build_financial_features(financials):
    return (
        financials.withColumn("Credit_History_Months", _credit_history_months("Credit_History_Age"))
        .withColumn("Num_Loan_Types", _loan_type_count("Type_of_Loan"))
        .withColumn("Debt_to_Income_Ratio", _safe_divide(col("Outstanding_Debt"), col("Annual_Income")))
        .withColumn(
            "EMI_to_Monthly_Income_Ratio",
            _safe_divide(col("Total_EMI_per_month"), col("Monthly_Inhand_Salary")),
        )
    )


def build_clickstream_features(clickstream):
    clickstream_columns = [f"fe_{i}" for i in range(1, 21)]
    return clickstream.groupBy("Customer_ID", "snapshot_date").agg(
        *[F.avg(col(column_name)).alias(column_name) for column_name in clickstream_columns]
    )


def build_label_store(loan_daily, loan_application):
    # Label store uses future repayment performance. These outcome fields must never flow into feature_store.
    mob6_labels = (
        loan_daily.filter(col("mob") == 6)
        .withColumn("label", F.when(col("dpd") >= 30, 1).otherwise(0).cast("int"))
        .withColumn("label_def", F.lit("30dpd_6mob"))
        .select(
            "loan_id",
            "Customer_ID",
            col("snapshot_date").alias("label_observation_date"),
            "label",
            "label_def",
        )
        .dropDuplicates(["loan_id"])
    )

    application_dates = loan_application.select(
        "loan_id",
        col("snapshot_date").alias("application_snapshot_date"),
    )

    return (
        mob6_labels.join(application_dates, "loan_id", "inner")
        .select(
            "loan_id",
            "Customer_ID",
            col("application_snapshot_date").alias("snapshot_date"),
            "label_observation_date",
            "label",
            "label_def",
        )
        .dropDuplicates(["loan_id"])
    )


def _date_from_string(value):
    return value if value else None


def _validate_override_dates(dates, override_map):
    available = {str(date) for date in dates}
    missing = {name: value for name, value in override_map.items() if value and value not in available}
    if missing:
        formatted = ", ".join([f"{name}={value}" for name, value in missing.items()])
        raise ValueError(f"Split override date(s) not present in feature_store snapshot dates: {formatted}")


def _build_split_mapping(feature_store, spark, validation_date=None, test_date=None, oot_date=None):
    date_rows = feature_store.select("snapshot_date").distinct().orderBy("snapshot_date").collect()
    dates = [row["snapshot_date"] for row in date_rows]
    if len(dates) < 4:
        raise ValueError("At least 4 distinct application snapshot dates are required for train/validation/test/OOT split.")

    override_map = {
        "validation_date": _date_from_string(validation_date),
        "test_date": _date_from_string(test_date),
        "oot_date": _date_from_string(oot_date),
    }
    _validate_override_dates(dates, override_map)

    oot_value = oot_date or str(dates[-1])
    non_oot_dates = [date for date in dates if str(date) != oot_value]

    n_dates = len(non_oot_dates)
    train_cut = max(1, math.floor(n_dates * 0.8))
    validation_cut = max(train_cut + 1, math.floor(n_dates * 0.9))
    validation_cut = min(validation_cut, n_dates - 1)

    split_by_date = {}
    for date in non_oot_dates[:train_cut]:
        split_by_date[str(date)] = "train"
    for date in non_oot_dates[train_cut:validation_cut]:
        split_by_date[str(date)] = "validation"
    for date in non_oot_dates[validation_cut:]:
        split_by_date[str(date)] = "test"
    split_by_date[oot_value] = "oot"

    # Explicit dates win over the automatic chronological assignment.
    if validation_date:
        split_by_date[validation_date] = "validation"
    if test_date:
        split_by_date[test_date] = "test"
    if oot_date:
        split_by_date[oot_date] = "oot"

    rows = [(date_value, split_name) for date_value, split_name in split_by_date.items()]
    return spark.createDataFrame(rows, ["snapshot_date_str", "data_split"]).withColumn(
        "snapshot_date", F.to_date(col("snapshot_date_str"))
    ).drop("snapshot_date_str")


def assign_data_split(feature_store, spark, validation_date=None, test_date=None, oot_date=None):
    split_mapping = _build_split_mapping(feature_store, spark, validation_date, test_date, oot_date)
    return feature_store.join(F.broadcast(split_mapping), "snapshot_date", "left")


def _numeric_feature_columns(df):
    return [
        column_name
        for column_name, dtype in df.dtypes
        if column_name not in ID_DATE_SPLIT_COLUMNS
        and column_name not in LEAKAGE_COLUMNS
        and dtype in {"int", "bigint", "double", "float", "decimal"}
    ]


def _categorical_feature_columns(df):
    excluded = ID_DATE_SPLIT_COLUMNS | LEAKAGE_COLUMNS | {"Name", "SSN", "Type_of_Loan"}
    return [column_name for column_name, dtype in df.dtypes if column_name not in excluded and dtype == "string"]


def _empty_numeric_metadata(spark):
    schema = StructType(
        [
            StructField("feature_name", StringType(), False),
            StructField("train_median", DoubleType(), True),
            StructField("lower_cap", DoubleType(), True),
            StructField("upper_cap", DoubleType(), True),
            StructField("train_mean", DoubleType(), True),
            StructField("train_stddev", DoubleType(), True),
        ]
    )
    return spark.createDataFrame([], schema)


def _fit_numeric_preprocessing(feature_store, numeric_columns, spark):
    train_df = feature_store.filter(col("data_split") == "train")
    if not numeric_columns:
        return [], _empty_numeric_metadata(spark)

    # Important runtime fix: calculate quantiles for all numeric columns in one Spark job,
    # instead of scanning the train set once per column.
    quantiles_by_column = train_df.approxQuantile(numeric_columns, [0.01, 0.5, 0.99], 0.01)

    quantile_stats = {}
    capped_expressions = []
    for column_name, quantiles in zip(numeric_columns, quantiles_by_column):
        if len(quantiles) < 3:
            lower_cap, median, upper_cap = 0.0, 0.0, 0.0
        else:
            lower_cap, median, upper_cap = [float(value) for value in quantiles]
        quantile_stats[column_name] = {
            "train_median": median,
            "lower_cap": lower_cap,
            "upper_cap": upper_cap,
        }
        capped = F.least(
            F.greatest(F.coalesce(col(column_name).cast(DoubleType()), F.lit(median)), F.lit(lower_cap)),
            F.lit(upper_cap),
        ).alias(column_name)
        capped_expressions.append(capped)

    capped_train = train_df.select(*capped_expressions)
    aggregate_expressions = []
    for column_name in numeric_columns:
        aggregate_expressions.append(F.mean(col(column_name)).alias(f"{column_name}__mean"))
        aggregate_expressions.append(F.stddev_pop(col(column_name)).alias(f"{column_name}__stddev"))
    aggregate_row = capped_train.agg(*aggregate_expressions).collect()[0].asDict()

    metadata_rows = []
    fitted_stats = []
    for column_name in numeric_columns:
        mean_value = aggregate_row.get(f"{column_name}__mean")
        stddev_value = aggregate_row.get(f"{column_name}__stddev")
        if stddev_value is None or float(stddev_value) == 0.0:
            stddev_value = 1.0

        stats = {
            "feature_name": column_name,
            **quantile_stats[column_name],
            "train_mean": float(mean_value or 0.0),
            "train_stddev": float(stddev_value),
        }
        metadata_rows.append(Row(**stats))
        fitted_stats.append(stats)

    metadata_df = spark.createDataFrame(metadata_rows)
    return fitted_stats, metadata_df


def _apply_numeric_preprocessing(feature_store, numeric_stats):
    original_columns = [col(column_name) for column_name in feature_store.columns]
    standardized_columns = []

    # Build all standardized columns in a single select to avoid a very deep withColumn plan.
    for stats in numeric_stats:
        column_name = stats["feature_name"]
        median = stats["train_median"]
        lower_cap = stats["lower_cap"]
        upper_cap = stats["upper_cap"]
        mean_value = stats["train_mean"]
        stddev_value = stats["train_stddev"]
        capped = F.least(
            F.greatest(F.coalesce(col(column_name).cast(DoubleType()), F.lit(median)), F.lit(lower_cap)),
            F.lit(upper_cap),
        )
        standardized_columns.append(((capped - F.lit(mean_value)) / F.lit(stddev_value)).alias(f"{column_name}_std"))

    return feature_store.select(*original_columns, *standardized_columns)


def _empty_categorical_metadata(spark):
    schema = StructType(
        [
            StructField("feature_name", StringType(), False),
            StructField("category_value", StringType(), False),
            StructField("encoded_column_name", StringType(), False),
        ]
    )
    return spark.createDataFrame([], schema)


def _fit_categorical_preprocessing(feature_store, categorical_columns, spark, max_categories=MAX_CATEGORIES_PER_FEATURE):
    train_df = feature_store.filter(col("data_split") == "train")
    mappings = []
    metadata_rows = []

    for column_name in categorical_columns:
        cleaned_train = train_df.select(_clean_category_expr(column_name).alias(column_name))
        category_rows = (
            cleaned_train.groupBy(column_name)
            .count()
            .orderBy(F.desc("count"), F.asc(column_name))
            .limit(max_categories)
            .collect()
        )

        categories = [str(row[column_name]) for row in category_rows if row[column_name] is not None]
        for required_category in ["Unknown", "Other"]:
            if required_category not in categories:
                categories.append(required_category)

        encoded_columns = []
        used_names = set()
        for category_value in categories:
            base_name = f"{column_name}_{_sanitize_token(category_value)}"
            encoded_column_name = base_name
            suffix = 1
            while encoded_column_name in used_names:
                suffix += 1
                encoded_column_name = f"{base_name}_{suffix}"
            used_names.add(encoded_column_name)
            encoded_columns.append((category_value, encoded_column_name))
            metadata_rows.append(
                Row(
                    feature_name=column_name,
                    category_value=str(category_value),
                    encoded_column_name=encoded_column_name,
                )
            )
        mappings.append({"feature_name": column_name, "categories": categories, "encoded_columns": encoded_columns})

    metadata_df = spark.createDataFrame(metadata_rows) if metadata_rows else _empty_categorical_metadata(spark)
    return mappings, metadata_df


def _apply_categorical_preprocessing(feature_store, categorical_mappings):
    original_columns = [col(column_name) for column_name in feature_store.columns]
    encoded_expressions = []

    # Build one-hot columns in a single select to avoid many nested withColumn calls.
    for mapping in categorical_mappings:
        column_name = mapping["feature_name"]
        categories = mapping["categories"]
        known_categories = [category for category in categories if category != "Other"]
        cleaned_value = _clean_category_expr(column_name)
        encoded_value = F.when(cleaned_value.isin(known_categories), cleaned_value).otherwise(F.lit("Other"))

        for category_value, encoded_column_name in mapping["encoded_columns"]:
            encoded_expressions.append(
                F.when(encoded_value == F.lit(category_value), F.lit(1)).otherwise(F.lit(0)).alias(encoded_column_name)
            )

    return feature_store.select(*original_columns, *encoded_expressions)


def build_model_feature_store(feature_store, project_dir, spark):
    numeric_columns = _numeric_feature_columns(feature_store)
    categorical_columns = _categorical_feature_columns(feature_store)

    numeric_stats, numeric_metadata = _fit_numeric_preprocessing(feature_store, numeric_columns, spark)
    categorical_mappings, categorical_metadata = _fit_categorical_preprocessing(feature_store, categorical_columns, spark)

    metadata_root = Path(project_dir) / "datamart" / "gold" / "preprocessing_metadata"
    numeric_metadata.write.mode("overwrite").parquet(str(metadata_root / "numeric_stats"))
    categorical_metadata.write.mode("overwrite").parquet(str(metadata_root / "categorical_mappings"))

    model_feature_store = _apply_numeric_preprocessing(feature_store, numeric_stats)
    model_feature_store = _apply_categorical_preprocessing(model_feature_store, categorical_mappings)

    # Recheck after preprocessing to ensure outcome/leakage fields were not reintroduced.
    leakage_present = [column_name for column_name in LEAKAGE_COLUMNS if column_name in model_feature_store.columns]
    if leakage_present:
        raise ValueError(f"Leakage columns found in model_feature_store: {leakage_present}")

    output_path = Path(project_dir) / "datamart" / "gold" / "model_feature_store"
    model_feature_store = _materialize_parquet(model_feature_store, output_path, ["data_split", "snapshot_date"])
    print(f"gold/model_feature_store -> {output_path}")
    return model_feature_store


def build_gold_tables(
    project_dir,
    spark,
    start_date=None,
    end_date=None,
    validation_date=None,
    test_date=None,
    oot_date=None,
    split_mode="auto_chronological_80_10_10_oot",
    profile=False,
    skip_model_feature_store=False,
):
    if split_mode != "auto_chronological_80_10_10_oot":
        raise ValueError("Only split_mode='auto_chronological_80_10_10_oot' is currently supported.")

    attributes = _read_silver(project_dir, "attributes", spark)
    financials = _read_silver(project_dir, "financials", spark)
    clickstream = _read_silver(project_dir, "clickstream", spark)
    lms = _read_silver(project_dir, "lms", spark)

    loan_daily = build_loan_daily(lms)
    loan_application = build_loan_application(lms, start_date=start_date, end_date=end_date)
    financial_features = build_financial_features(financials)
    clickstream_features = build_clickstream_features(clickstream)

    feature_store = (
        loan_application.join(
            attributes.select("Customer_ID", "snapshot_date", "Age", "Occupation"),
            ["Customer_ID", "snapshot_date"],
            "left",
        )
        .join(
            financial_features.select(
                "Customer_ID",
                "snapshot_date",
                "Annual_Income",
                "Monthly_Inhand_Salary",
                "Num_Bank_Accounts",
                "Num_Credit_Card",
                "Interest_Rate",
                "Num_of_Loan",
                "Delay_from_due_date",
                "Num_of_Delayed_Payment",
                "Changed_Credit_Limit",
                "Num_Credit_Inquiries",
                "Outstanding_Debt",
                "Credit_Utilization_Ratio",
                "Total_EMI_per_month",
                "Amount_invested_monthly",
                "Monthly_Balance",
                "Credit_Mix",
                "Payment_of_Min_Amount",
                "Payment_Behaviour",
                "Credit_History_Months",
                "Num_Loan_Types",
                "Debt_to_Income_Ratio",
                "EMI_to_Monthly_Income_Ratio",
            ),
            ["Customer_ID", "snapshot_date"],
            "left",
        )
        .join(clickstream_features, ["Customer_ID", "snapshot_date"], "left")
        .withColumn("Loan_to_Income_Ratio", _safe_divide(col("loan_amt"), col("Annual_Income")))
        .dropDuplicates(["loan_id"])
    )

    # Feature store contains application-time predictors only. Future repayment fields stay in loan_daily/label_store.
    leakage_present = [column_name for column_name in LEAKAGE_COLUMNS if column_name in feature_store.columns]
    if leakage_present:
        raise ValueError(f"Leakage columns found in feature_store: {leakage_present}")

    feature_store = assign_data_split(feature_store, spark, validation_date, test_date, oot_date)

    feature_output_path = Path(project_dir) / "datamart" / "gold" / "feature_store"
    feature_store = _materialize_parquet(feature_store, feature_output_path, ["data_split", "snapshot_date"])
    message = f"gold/feature_store -> {feature_output_path}"
    if profile:
        message = f"{message} ({feature_store.count():,} rows)"
    print(message)

    label_store = build_label_store(loan_daily, loan_application)
    label_output_path = Path(project_dir) / "datamart" / "gold" / "label_store"
    label_store = _materialize_parquet(label_store, label_output_path, ["snapshot_date"])
    message = f"gold/label_store -> {label_output_path}"
    if profile:
        message = f"{message} ({label_store.count():,} rows)"
    print(message)

    model_feature_store = None
    if not skip_model_feature_store:
        model_feature_store = build_model_feature_store(feature_store, project_dir, spark)

    return {
        "feature_store": feature_store,
        "label_store": label_store,
        "model_feature_store": model_feature_store,
    }
