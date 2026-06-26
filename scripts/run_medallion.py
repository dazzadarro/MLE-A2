import argparse
from pathlib import Path
import sys

import pyspark

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from utils.data_processing_bronze_table import build_bronze_tables
from utils.data_processing_gold_table import build_gold_tables
from utils.data_processing_silver_table import build_silver_tables


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild Bronze, Silver and Gold even when the completed Gold stores exist.",
    )
    args = parser.parse_args()
    project_dir = PROJECT_DIR
    required_gold_stores = [
        project_dir / "datamart" / "gold" / "feature_store",
        project_dir / "datamart" / "gold" / "label_store",
        project_dir / "datamart" / "gold" / "model_feature_store",
    ]

    # The medallion tables are shared inputs for monthly inference. Reusing a
    # complete store prevents every Airflow backfill month rebuilding all data.
    if not args.force and all(path.exists() for path in required_gold_stores):
        print("Completed Gold stores already exist; medallion rebuild skipped.")
        return

    spark = (
        pyspark.sql.SparkSession.builder.appName("mle_a2_medallion")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    try:
        build_bronze_tables(project_dir, spark)
        build_silver_tables(project_dir, spark)
        build_gold_tables(
            project_dir,
            spark,
            end_date="2024-12-01",
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
