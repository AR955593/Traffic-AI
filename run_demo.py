import os
import sys
import subprocess
import time

def print_header(title):
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60 + "\n")

def run_step():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(project_dir, "models")
    data_path = os.path.join(project_dir, "data", "raw_traffic_weather.csv")

    # Step 1: Check/Generate Dataset
    if not os.path.exists(data_path):
        print_header("Step 1: Generating Synthetic 7-Day Dataset")
        subprocess.run([sys.executable, os.path.join(project_dir, "data", "generate_dataset.py")], check=True)
    else:
        print("[OK] Dataset ready.")

    # Step 2: Check/Train ML Models
    gb_model_path = os.path.join(models_dir, "gradient_boosting_regressor.joblib")
    if not os.path.exists(gb_model_path):
        print_header("Step 2: Training ML Models (HistGB, Random Forest, PyTorch LSTM)")
        subprocess.run([sys.executable, os.path.join(project_dir, "src", "train_models.py")], check=True)
    else:
        print("[OK] Pre-trained AI/ML models loaded.")

    # Step 3: Run Automated Verification Tests
    print_header("Step 3: Running Automated Test Suite")
    subprocess.run([sys.executable, "-u", os.path.join(project_dir, "tests", "test_traffic_platform.py")], check=True)

    # Step 4: Start FastAPI Backend & Live Dashboard
    print_header("Step 4: Launching Traffic AI Platform")
    print("------------------------------------------------------------")
    print(" > Desktop Control Room:  http://127.0.0.1:8000")
    print(" > Mobile Phone App:      http://127.0.0.1:8000 (Responsive)")
    print(" > OpenAPI Docs:          http://127.0.0.1:8000/docs")
    print(" > WebSocket Stream:      ws://127.0.0.1:8000/api/v1/ws/traffic")
    print("------------------------------------------------------------")
    print("Press Ctrl+C to stop the server.\n")

    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"], cwd=project_dir)
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")

if __name__ == "__main__":
    run_step()
