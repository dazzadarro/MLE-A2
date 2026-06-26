import argparse
import json
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Train and evaluate challengers even when a governed champion exists.",
    )
    args = parser.parse_args()

    project_dir = PROJECT_DIR
    champion = project_dir / "model_bank" / "champion_model.pkl"
    registry_path = project_dir / "model_bank" / "model_registry.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8-sig"))
        if registry_path.exists()
        else {}
    )
    if champion.exists() and registry and not args.force_refresh:
        print(f"Champion model already exists and will be reused: {champion}")
    else:
        print("Champion missing or refresh requested; evaluating fresh challengers.")
        from utils.model_lifecycle import train_and_select_model

        train_and_select_model(project_dir)
