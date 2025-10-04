import subprocess, sys, os, datetime

HERE = os.path.dirname(__file__)
APP = os.path.join(HERE, "activate_this.py")

def run(cmd):
    print(">", " ".join(cmd))
    return subprocess.call(cmd, cwd=HERE)

def main():
    # 1) Pull latest
    run(["git", "pull", "--rebase"])

    # 2) Stage
    run(["git", "add", "-A"])

    # 3) Commit (if changes)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rc = run(["git", "commit", "-m", f"Auto update {ts}"])
    if rc != 0:
        print("(No new changes to commit.)")

    # 4) Push
    run(["git", "push"])

    # 5) Launch Streamlit with current Python
    run([sys.executable, "-m", "streamlit", "run", APP])

if __name__ == "__main__":
    main()
