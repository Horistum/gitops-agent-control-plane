#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = {}
        self.elapsed = {}
        self.successes = []

    def startTest(self, test):
        self.started[test.id()] = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        self.elapsed[test.id()] = max(0.0, time.monotonic() - self.started.get(test.id(), time.monotonic()))
        super().stopTest(test)

    def addSuccess(self, test):
        self.successes.append(test)
        super().addSuccess(test)


def junit(result: RecordingResult) -> Path:
    failures = {test.id(): text for test, text in result.failures}
    errors = {test.id(): text for test, text in result.errors}
    skipped = {test.id(): reason for test, reason in result.skipped}
    all_tests = {}
    for test in result.successes:
        all_tests[test.id()] = test
    for test, _ in result.failures + result.errors + result.skipped:
        all_tests[test.id()] = test

    suite = ET.Element(
        "testsuite",
        name="reference",
        tests=str(result.testsRun),
        failures=str(len(result.failures)),
        errors=str(len(result.errors)),
        skipped=str(len(result.skipped)),
    )
    for test_id in sorted(all_tests):
        test = all_tests[test_id]
        classname, _, name = test_id.rpartition(".")
        case = ET.SubElement(
            suite,
            "testcase",
            classname=classname,
            name=name,
            time=f"{result.elapsed.get(test_id, 0.0):.6f}",
        )
        if test_id in failures:
            ET.SubElement(case, "failure", message="assertion failed").text = failures[test_id]
        elif test_id in errors:
            ET.SubElement(case, "error", message="test error").text = errors[test_id]
        elif test_id in skipped:
            ET.SubElement(case, "skipped", message=skipped[test_id])

    out = ROOT / "build" / "test-results" / "reference" / "TEST-reference.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(out, encoding="utf-8", xml_declaration=True)
    return out


def main() -> int:
    discovered = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult)
    result = runner.run(discovered)
    path = junit(result)
    print(f"JUnit: {path.relative_to(ROOT)}")
    if result.testsRun < 1:
        print("No tests executed", file=sys.stderr)
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
