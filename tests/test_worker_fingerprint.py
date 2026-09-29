"""Worker source changes invalidate saved runtime authority in every profile."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_runtime.store import runtime_fingerprint


class WorkerFingerprintTests(unittest.TestCase):
    def test_worker_source_is_part_of_runtime_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / 'agent_worker'
            worker.mkdir()
            source = worker / '__init__.py'
            source.write_text('# reviewed worker\n')
            transport = worker / 'transport.py'
            transport.write_text('# reviewed transport\n')
            with patch('agent_runtime.store.agent_worker.__file__', str(source)):
                before = runtime_fingerprint()
                transport.write_text('# changed transport\n')
                self.assertNotEqual(before, runtime_fingerprint())


if __name__ == '__main__':
    unittest.main()
