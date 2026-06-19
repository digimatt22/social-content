from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


class CopywriterSkillScriptTests(unittest.TestCase):
    def test_normalize_check_and_score_copy_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "brief.json"
            draft_path = Path(tmp) / "draft.txt"
            run_script(
                ".agents/skills/copywriter/scripts/normalize_copy_request.py",
                "--destination",
                "facebook",
                "--audience",
                "gift buyers",
                "--goal",
                "drive shop visits",
                "--details",
                "New 3D printed desk duck in a yellow raincoat",
                "--brand-voice",
                "warm, playful, handmade",
                "--must-include",
                "3D printed,desk duck",
                "--avoid",
                "rubber duck,limited time only",
                "--output",
                str(brief_path),
            )
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(brief["format"], "social post")
            self.assertEqual(brief["destination"], "facebook")

            check = run_script(".agents/skills/copywriter/scripts/check_copy_brief.py", "--brief", str(brief_path))
            self.assertEqual(json.loads(check.stdout)["status"], "ready")

            draft_path.write_text(
                "This 3D printed desk duck brings a little raincoat charm to your shelf. "
                "Shop the new release and tell me who needs one on their desk.",
                encoding="utf-8",
            )
            score = run_script(
                ".agents/skills/copywriter/scripts/score_copy_draft.py",
                "--copy",
                str(draft_path),
                "--brief",
                str(brief_path),
            )
            self.assertEqual(json.loads(score.stdout)["label"], "ready")


class ImageCreatorSkillScriptTests(unittest.TestCase):
    def test_normalize_check_and_manifest_for_both_provider_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "image-brief.json"
            run_script(
                ".agents/skills/image-creator/scripts/normalize_image_request.py",
                "--destination",
                "instagram",
                "--format",
                "square post",
                "--audience",
                "gift buyers",
                "--goal",
                "drive shop visits",
                "--subject",
                "miniature desk duck in a cozy workspace",
                "--brand-style",
                "warm handmade product photo",
                "--provider-path",
                "built-in",
                "--output",
                str(brief_path),
            )
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
            self.assertEqual(brief["aspect_ratio"], "1:1")
            self.assertEqual(brief["provider_path"], "built-in")

            check = run_script(".agents/skills/image-creator/scripts/check_image_brief.py", "--brief", str(brief_path))
            self.assertEqual(json.loads(check.stdout)["status"], "ready")

            magnific = run_script(
                ".agents/skills/image-creator/scripts/build_generation_manifest.py",
                "--product-slug",
                "mailman-duck",
                "--destination",
                "instagram",
                "--target-format",
                "square-product-card",
                "--provider-path",
                "magnific-mcp",
                "--source",
                "assets/products/mailman-duck/source.jpg",
                "--prompt",
                "Place the exact duck in a realistic mailroom scene.",
            )
            magnific_manifest = json.loads(magnific.stdout)
            self.assertEqual(magnific_manifest["provider_path"], "magnific-mcp")
            self.assertIn("Confirm Magnific/Freepik MCP tools", magnific_manifest["handoff_steps"][0])

            builtin = run_script(
                ".agents/skills/image-creator/scripts/build_generation_manifest.py",
                "--product-slug",
                "general",
                "--destination",
                "newsletter",
                "--target-format",
                "hero-image",
                "--provider-path",
                "built-in",
                "--prompt",
                "Warm handmade product scene on a workbench.",
            )
            builtin_manifest = json.loads(builtin.stdout)
            self.assertEqual(builtin_manifest["provider"], "built-in-image-generation")
            self.assertEqual(builtin_manifest["review_state"], "needs_review")


if __name__ == "__main__":
    unittest.main()
