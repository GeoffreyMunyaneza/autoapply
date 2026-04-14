"""
review.py — Interactive CLI for reviewing and approving/rejecting pending tailored resumes.

Usage:
  python review.py              # review all pending resumes interactively
  python review.py --list       # list pending resumes without prompting
  python review.py --approve-all  # approve everything in pending/ (fast path)
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from core.tracker import update_status


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_pending(pending_folder: Path) -> list[Path]:
    """Return sorted list of pending .docx files."""
    if not pending_folder.exists():
        return []
    return sorted(pending_folder.glob("*.docx"))


def _print_diff(diff_file: Path) -> None:
    """Print the diff file with simple ANSI colour if the terminal supports it."""
    if not diff_file.exists():
        print("  (no diff file found)")
        return

    try:
        text = diff_file.read_text(encoding="utf-8")
    except Exception:
        print("  (could not read diff file)")
        return

    supports_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    RED = "\033[31m" if supports_color else ""
    GREEN = "\033[32m" if supports_color else ""
    CYAN = "\033[36m" if supports_color else ""
    RESET = "\033[0m" if supports_color else ""

    for line in text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            print(f"{CYAN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}")
        elif line.startswith("+"):
            print(f"{GREEN}{line}{RESET}")
        else:
            print(line)


def _open_in_word(docx_path: Path) -> None:
    """Try to open the docx in Word (best-effort)."""
    try:
        subprocess.Popen(["start", "", str(docx_path)], shell=True)
    except Exception:
        pass


def review_one(
    docx_path: Path,
    output_folder: Path,
    tracker_path: str,
    open_word: bool = False,
) -> str:
    """
    Interactively review a single pending resume.
    Returns: "approved" | "rejected" | "skipped" | "quit"
    """
    diff_file = docx_path.with_suffix(".diff.txt")

    print("\n" + "=" * 70)
    print(f"  {docx_path.name}")
    print("=" * 70)
    _print_diff(diff_file)

    if open_word:
        _open_in_word(docx_path)

    while True:
        choice = input("\n  [a]pprove  [r]eject  [o]pen in Word  [s]kip  [q]uit → ").strip().lower()
        if choice in ("a", "approve"):
            # Move docx to resumes folder
            dest = output_folder / docx_path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            counter = 1
            while dest.exists():
                dest = output_folder / f"{docx_path.stem}_{counter}.docx"
                counter += 1
            shutil.move(str(docx_path), str(dest))
            # Clean up diff file
            if diff_file.exists():
                diff_file.unlink()
            # Update tracker: find by filename stem (company_title_type_date)
            _update_tracker_by_filename(tracker_path, docx_path.name, "Queued")
            print(f"  ✓ Approved → {dest.name}")
            return "approved"

        elif choice in ("r", "reject"):
            docx_path.unlink(missing_ok=True)
            if diff_file.exists():
                diff_file.unlink()
            _update_tracker_by_filename(tracker_path, docx_path.name, "Skipped")
            print("  ✗ Rejected — removed from pending")
            return "rejected"

        elif choice in ("o", "open"):
            _open_in_word(docx_path)

        elif choice in ("s", "skip"):
            print("  → Skipped (stays in pending)")
            return "skipped"

        elif choice in ("q", "quit"):
            print("  → Quitting review session")
            return "quit"

        else:
            print("  Invalid — enter a, r, o, s, or q")


def _update_tracker_by_filename(tracker_path: str, filename: str, status: str) -> None:
    """
    Find the tracker row whose Resume Path ends with filename and update its status.
    Falls back gracefully if not found.
    """
    try:
        import openpyxl
        from pathlib import Path as _P
        p = _P(tracker_path)
        if not p.exists():
            return
        wb = openpyxl.load_workbook(tracker_path)
        ws = wb.active
        from core.tracker import COLUMNS, STATUS_COLORS
        from openpyxl.styles import PatternFill

        status_col = COLUMNS.index("Status") + 1
        resume_col = COLUMNS.index("Resume Path") + 1
        id_col = COLUMNS.index("ID") + 1
        color = STATUS_COLORS.get(status, "FFFFFF")
        fill = PatternFill(start_color=color, end_color=color, fill_type="solid")

        for row in ws.iter_rows(min_row=2):
            resume_val = str(row[resume_col - 1].value or "")
            if filename.replace(".docx", "") in resume_val:
                row[status_col - 1].value = status
                for cell in row:
                    cell.fill = fill
                wb.save(tracker_path)
                return
    except Exception:
        pass  # Tracker update is best-effort during review


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="AutoApply — Resume Review CLI")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--list", action="store_true", help="List pending resumes and exit")
    parser.add_argument("--approve-all", action="store_true", help="Approve all pending resumes without prompting")
    parser.add_argument("--open-word", action="store_true", help="Auto-open each resume in Word when reviewing")
    args = parser.parse_args()

    config = load_config(args.config)
    output_cfg = config["output"]
    pending_folder = Path(output_cfg.get("pending_folder", "output/pending"))
    resumes_folder = Path(output_cfg["resumes_folder"])
    tracker_path = output_cfg["tracker_file"]

    pending = _find_pending(pending_folder)

    if not pending:
        print("No pending resumes to review.")
        return

    print(f"\nFound {len(pending)} resume(s) pending review in {pending_folder}/")

    if args.list:
        for p in pending:
            diff = p.with_suffix(".diff.txt")
            n_changes = "?"
            if diff.exists():
                try:
                    n_changes = sum(1 for l in diff.read_text(encoding="utf-8").splitlines() if l.startswith("[Paragraph"))
                except Exception:
                    pass
            print(f"  {p.name}  ({n_changes} changed paragraphs)")
        return

    if args.approve_all:
        approved = 0
        for docx_path in pending:
            dest = resumes_folder / docx_path.name
            resumes_folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(docx_path), str(dest))
            diff_file = docx_path.with_suffix(".diff.txt")
            if diff_file.exists():
                diff_file.unlink()
            _update_tracker_by_filename(tracker_path, docx_path.name, "Queued")
            approved += 1
        print(f"Approved all {approved} pending resume(s) → {resumes_folder}/")
        return

    # Interactive review
    approved = rejected = skipped = 0
    for docx_path in pending:
        result = review_one(docx_path, resumes_folder, tracker_path, open_word=args.open_word)
        if result == "approved":
            approved += 1
        elif result == "rejected":
            rejected += 1
        elif result == "skipped":
            skipped += 1
        elif result == "quit":
            break

    print(f"\nReview complete — approved: {approved}, rejected: {rejected}, skipped: {skipped}")
    remaining = len(_find_pending(pending_folder))
    if remaining:
        print(f"{remaining} resume(s) still pending. Run `python review.py` to continue.")


if __name__ == "__main__":
    main()
