import os
import subprocess


def main() -> None:
    """
    Railway sometimes runs the start command without a shell, so `$PORT` won't expand.
    Read PORT from env and pass it to gunicorn as a concrete value.
    """
    port = os.environ.get("PORT", "5000").strip()
    if not port.isdigit():
        raise SystemExit(f"Invalid PORT: {port!r}. Expected a numeric string.")

    print(f"[start.py] Starting gunicorn on 0.0.0.0:{port}", flush=True)

    subprocess.run(
        [
            "python",
            "-m",
            "gunicorn",
            "server:app",
            "--bind",
            f"0.0.0.0:{port}",
            "--workers",
            "1",
            "--threads",
            "8",
            "--timeout",
            "0",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()

