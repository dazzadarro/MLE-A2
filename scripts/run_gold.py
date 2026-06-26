import argparse
from pathlib import Path
import sys

import pyspark

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from utils.data_processing_gold_table import build_gold_tables


def spark_session(app_name):
    return (
        pyspark.sql.SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .getOrCreate()
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    required_outputs = [
        PROJECT_DIR / "datamart" / "gold" / "feature_store",
        PROJECT_DIR / "datamart" / "gold" / "label_store",
        PROJECT_DIR / "datamart" / "gold" / "model_feature_store",
    ]
    if not args.force and all(path.exists() for path in required_outputs):
        print("Gold stores already exist; Gold rebuild skipped.")
        return

    spark = spark_session("mle_a2_gold")
    spark.sparkContext.setLogLevel("ERROR")
    try:
        build_gold_tables(
            PROJECT_DIR,
            spark,
            end_date="2024-12-01",
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
