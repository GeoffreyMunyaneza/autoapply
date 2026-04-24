import shutil
import unittest
from pathlib import Path

from services.config import prepare_config


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = REPO_ROOT / "output" / "test_prepare_config"


class PrepareConfigTests(unittest.TestCase):
    def test_prepare_config_preserves_absolute_paths_and_creates_directories(self) -> None:
        shutil.rmtree(TEST_ROOT, ignore_errors=True)
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            root = TEST_ROOT
            tracker = root / "tracker.xlsx"
            resumes = root / "resumes"
            pending = root / "pending"
            screenshots = root / "screenshots"

            prepared = prepare_config(
                {
                    "output": {
                        "tracker_file": str(tracker),
                        "resumes_folder": str(resumes),
                        "pending_folder": str(pending),
                    },
                    "submission": {
                        "screenshots_folder": str(screenshots),
                    },
                }
            )

            self.assertEqual(prepared["output"]["tracker_file"], str(tracker))
            self.assertEqual(prepared["output"]["resumes_folder"], str(resumes))
            self.assertEqual(prepared["output"]["pending_folder"], str(pending))
            self.assertEqual(prepared["submission"]["screenshots_folder"], str(screenshots))
            self.assertTrue(prepared["review"]["auto_approve"])
            self.assertTrue(resumes.exists())
            self.assertTrue(pending.exists())
            self.assertTrue(screenshots.exists())
        finally:
            shutil.rmtree(TEST_ROOT, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
