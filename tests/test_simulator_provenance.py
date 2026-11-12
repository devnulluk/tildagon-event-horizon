import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("horizon_hash_provenance", Path(__file__).resolve().parents[1] / "simulator/provenance.py")
provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance)


class ProvenanceTests(unittest.TestCase):
    def test_line_endings_change_exact_hash_but_not_git_canonical_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "app.py"
            file.write_bytes(b"x=1\ny=2\n")
            lf, raw_lf = provenance.source_hashes(directory)
            file.write_bytes(b"x=1\r\ny=2\r\n")
            crlf, raw_crlf = provenance.source_hashes(directory)
            self.assertEqual(lf, crlf)
            self.assertNotEqual(raw_lf, raw_crlf)
            self.assertEqual(lf, raw_lf)

    def test_hashes_are_a_snapshot_of_only_runtime_python_files(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "app.py"
            file.write_bytes(b"old\n")
            (Path(directory) / "config.json").write_text("{}")
            before, raw = provenance.source_hashes(directory)
            file.write_bytes(b"new\n")
            after, unused = provenance.source_hashes(directory)
            self.assertEqual(set(before), {"app.py"})
            self.assertNotEqual(before, after)
            self.assertEqual(before, raw)


if __name__ == "__main__":
    unittest.main()
