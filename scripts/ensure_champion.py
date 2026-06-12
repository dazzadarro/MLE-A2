from pathlib import Path

from utils.model_lifecycle import train_and_select_model


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parents[1]
    champion = project_dir / "model_bank" / "champion_model.pkl"
    if champion.exists():
        print(f"Champion model already exists: {champion}")
    else:
        train_and_select_model(project_dir)
