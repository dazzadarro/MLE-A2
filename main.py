import argparse
import shutil
from pathlib import Path

import pyspark

from utils.data_processing_bronze_table import build_bronze_tables
from utils.data_processing_gold_table import build_gold_tables
from utils.data_processing_silver_table import build_silver_tables
from utils.model_lifecycle import (
    calculate_monthly_monitoring,
    run_monthly_inference,
    train_and_select_model,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run CS611 Assignment 2 end-to-end ML pipeline.")
    parser.add_argument("--start-date", default=None, help="Optional application snapshot start date, YYYY-MM-DD.")
    parser.add_argument(
        "--end-date",
        default="2024-12-01",
        help="Optional application snapshot end date, YYYY-MM-DD. Default keeps the A2 modelling window to Dec 2024.",
    )
    parser.add_argument("--profile", action="store_true", help="Print row counts for each layer.")
    parser.add_argument(
        "--skip-model-feature-store",
        action="store_true",
        help="Run only the human-readable medallion stores.",
    )
    parser.add_argument("--skip-ml", action="store_true", help="Skip training, inference and monitoring.")
    return parser.parse_args()


def reset_datamart(project_dir):
    datamart_path = Path(project_dir) / "datamart"
    if datamart_path.exists():
        shutil.rmtree(datamart_path)
    datamart_path.mkdir(parents=True, exist_ok=True)


def create_spark_session():
    return (
        pyspark.sql.SparkSession.builder.appName("mle_a2_end_to_end_pipeline")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .getOrCreate()
    )


def main():
    args = parse_args()
    project_dir = Path(__file__).resolve().parent

    print("\n--- Assignment 2 end-to-end ML pipeline starting ---\n")
    reset_datamart(project_dir)

    spark = create_spark_session()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        build_bronze_tables(project_dir, spark, profile=args.profile)
        build_silver_tables(project_dir, spark, profile=args.profile)
        gold_outputs = build_gold_tables(
            project_dir,
            spark,
            start_date=args.start_date,
            end_date=args.end_date,
            profile=args.profile,
            skip_model_feature_store=args.skip_model_feature_store,
        )

        feature_store = gold_outputs["feature_store"]
        label_store = gold_outputs["label_store"]

        if args.profile:
            print("\nFeature-store splits:")
            feature_store.groupBy("data_split").count().orderBy("data_split").show(truncate=False)

            print("\nLabel-store preview:")
            label_store.orderBy("loan_id").show(10, truncate=False)

        print("\nDatamart created successfully:")
        print(project_dir / "datamart" / "bronze")
        print(project_dir / "datamart" / "silver")
        print(project_dir / "datamart" / "gold")
    finally:
        spark.stop()

    if not args.skip_ml and not args.skip_model_feature_store:
        print("\n--- Model training and champion selection ---\n")
        train_and_select_model(project_dir)
        print("\n--- Monthly batch inference ---\n")
        run_monthly_inference(project_dir)
        print("\n--- P0/P1, PSI and CSI monitoring ---\n")
        calculate_monthly_monitoring(project_dir)

    print("\n--- Assignment 2 pipeline completed ---\n")


if __name__ == "__main__":
    main()
