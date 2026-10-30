"""Is a file really in iCloud (uploaded), or still on its way?"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.utils import icloud_status


class UploadDetailsTest(unittest.TestCase):
    def test_bytes_per_file(self):
        root = Path(tempfile.mkdtemp())
        a, b, c = root / "a.cbz", root / "b.cbz", root / "c.cbz"
        for f, n in ((a, 100), (b, 200), (c, 50)):
            f.write_bytes(b"x" * n)
        out = (f"uploaded\t{a}\nuploading\t{b}\t150\t200\nerror\t{c}\tno account\n")
        run = lambda cmd, **kw: SimpleNamespace(returncode=0, stdout=out)
        d = icloud_status.upload_details([a, b, c], run=run, helper=Path("/bin/helper"))
        self.assertEqual(d[str(a)], {"state": "uploaded", "done": 100, "size": 100})
        self.assertEqual(d[str(b)], {"state": "uploading", "done": 150, "size": 200})
        self.assertEqual(d[str(c)], {"state": "error: no account", "done": 0, "size": 50})
        s = icloud_status.summarize_details(d)
        self.assertEqual((s["uploaded"], s["uploading"], s["retrying"], s["done_bytes"], s["total_bytes"]),
                         (1, 1, 1, 250, 350))


class UploadStatusTest(unittest.TestCase):
    def test_parses_helper_output(self):
        calls = []
        def run(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="uploaded\t/a.cbz\nuploading\t/b.cbz\n"
                                                        "waiting\t/c.cbz\nerror\t/d.cbz\tquota full\n")
        got = icloud_status.upload_status([Path("/a.cbz"), Path("/b.cbz"), Path("/c.cbz"), Path("/d.cbz")],
                                          run=run, helper=Path("/bin/helper"))
        self.assertEqual(calls[0], ["/bin/helper", "/a.cbz", "/b.cbz", "/c.cbz", "/d.cbz"])
        self.assertEqual(got, {"/a.cbz": "uploaded", "/b.cbz": "uploading", "/c.cbz": "waiting",
                               "/d.cbz": "error: quota full"})

    def test_unknown_when_helper_missing_or_failing(self):
        def run(cmd, **kw):
            raise OSError("no helper")
        self.assertEqual(icloud_status.upload_status([Path("/a.cbz")], run=run, helper=Path("/x")),
                         {"/a.cbz": "unknown"})
        self.assertEqual(icloud_status.upload_status([], run=run, helper=Path("/x")), {})

    def test_summary_treats_errors_as_retrying(self):
        s = icloud_status.summarize({"/a": "uploaded", "/b": "uploading", "/c": "waiting",
                                     "/d": "error: no account", "/e": "error: no account", "/f": "unknown"})
        self.assertEqual(s, {"total": 6, "uploaded": 1, "uploading": 1, "waiting": 2, "retrying": 2,
                             "pending": 5, "reasons": {"no account": 2}})

    def test_item_state(self):
        self.assertEqual([icloud_status.item_state(x) for x in
                          ("uploaded", "uploading", "waiting", "unknown", "error: x", "missing")],
                         ["uploaded", "uploading", "waiting", "waiting", "retrying", "missing"])

if __name__ == "__main__":
    unittest.main()
