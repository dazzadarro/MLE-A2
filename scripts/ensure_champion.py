import json
from pathlib import Path

from utils.model_lifecycle import train_and_select_model, training_signature


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parents[1]
    champion = project_dir / "model_bank" / "champion_model.pkl"
    registry_path = project_dir / "model_bank" / "model_registry.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.exists()
        else {}
    )
    current_signature = training_signature(project_dir)
    if champion.exists() and registry.get("training_signature") == current_signature:
        print(f"Champion model already exists: {champion}")
    else:
        print("Model code or training data changed; evaluating fresh challengers.")
        train_and_select_model(project_dir)
