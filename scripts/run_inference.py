import argparse
from pathlib import Path

from utils.model_lifecycle import run_monthly_inference


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshotdate", required=True)
    args = parser.parse_args()
    run_monthly_inference(Path(__file__).resolve().parents[1], args.snapshotdate)
