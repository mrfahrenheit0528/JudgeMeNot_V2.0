import os
import sys
import subprocess

def main():
    # Ensure we are running from the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    print("=" * 60)
    print(" JUDGEMENOT V2.0 - SYSTEM AUDIT RUNNER")
    print("=" * 60)
    print("Initializing test suite...")

    # Build the pytest command
    # Using the virtual environment's python/pytest if available
    venv_pytest = os.path.join(project_root, '.venv', 'Scripts', 'pytest.exe')
    
    if os.path.exists(venv_pytest):
        pytest_cmd = [venv_pytest]
    else:
        pytest_cmd = [sys.executable, "-m", "pytest"]
    
    report_path = os.path.join(project_root, "reports", "audit_report.html")

    pytest_args = [
        "tests/test_audit.py",
        "-v",
        f"--html={report_path}",
        "--self-contained-html"
    ]

    print(f"\nRunning tests and generating report at: {report_path}")
    print("-" * 60)

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root

    try:
        # Run pytest
        result = subprocess.run(pytest_cmd + pytest_args, capture_output=False, text=True, env=env)
        
        print("-" * 60)
        if result.returncode == 0:
            print("[SUCCESS] SYSTEM AUDIT PASSED: All core features verified successfully.")
        else:
            print("[FAILED] SYSTEM AUDIT FAILED: One or more tests did not pass.")
            
        print(f"\nDetailed comprehensive HTML report available at:\n -> file:///{report_path.replace(chr(92), '/')}")

    except Exception as e:
        print(f"Error running the audit suite: {e}")

if __name__ == "__main__":
    main()
