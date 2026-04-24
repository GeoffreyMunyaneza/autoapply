import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from core.scraper import Job
from services.pipeline import run_pipeline


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = REPO_ROOT / "output" / "test_pipeline_review_mode"


class PipelineReviewModeTests(unittest.TestCase):
    def test_run_pipeline_marks_pending_review_when_resume_is_saved_to_pending_folder(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            root = TEST_ROOT
            pending_dir = root / "pending"
            resumes_dir = root / "resumes"
            tracker_file = root / "tracker.xlsx"

            job = Job(
                id="job-1",
                title="Machine Learning Engineer",
                company="Example Corp",
                location="Remote",
                description="Long enough description for testing",
                url="https://example.com/jobs/1",
                source="linkedin",
            )

            config = {
                "search": {
                    "queries": [{"query": "Machine Learning Engineer", "resume_type": "ml"}],
                    "sources": ["linkedin"],
                    "location": "United States",
                    "results_per_query": 5,
                    "hours_old": 24,
                    "remote_only": False,
                },
                "filter": {"exclude_keywords": [], "min_description_length": 0},
                "output": {
                    "tracker_file": str(tracker_file),
                    "resumes_folder": str(resumes_dir),
                    "pending_folder": str(pending_dir),
                },
                "resumes": {"ml": str(root / "base_resume.docx")},
                "review": {"auto_approve": False},
                "cover_letter": {"auto_generate": False},
                "notifications": {"windows_toast": False, "email": {"enabled": False}},
                "submission": {"enabled": False, "screenshots_folder": str(root / "screenshots")},
                "user_profile": {},
            }

            add_job_calls = []

            with (
                patch("services.pipeline.scrape_jobs", return_value=[job]),
                patch("services.pipeline.load_seen_ids", return_value=set()),
                patch("services.pipeline.select_resume_type", return_value="ml"),
                patch("services.pipeline.passes_filter", return_value=(True, "")),
                patch("services.pipeline.score_job", return_value=0.91),
                patch(
                    "services.pipeline.tailor_resume",
                    return_value=(str(pending_dir / "Example_Corp_MLE.docx"), ""),
                ),
                patch("services.pipeline.add_job", side_effect=lambda **kwargs: add_job_calls.append(kwargs)),
                patch("services.pipeline.notify_new_jobs"),
                patch("services.pipeline.notify_pipeline_complete"),
            ):
                new_count = run_pipeline(config, api_key="fake-key")

            self.assertEqual(new_count, 1)
            self.assertEqual(len(add_job_calls), 1)
            self.assertEqual(add_job_calls[0]["status"], "Pending Review")
        finally:
            shutil.rmtree(TEST_ROOT, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
