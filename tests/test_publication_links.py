"""Regression checks for rendered-document heading links."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


source = load('check_publication')
distribution = load('check_distribution')


class PublicationLinkTests(unittest.TestCase):
    def test_duplicate_headings_and_fenced_examples(self):
        text = '# Same heading\n## Same heading\n```markdown\n# Not a heading\n```\n## Same heading\n'
        self.assertEqual({'same-heading', 'same-heading-1', 'same-heading-2'}, source.markdown_anchors(text))

    def test_inline_formatting_explicit_ids_and_closing_hashes(self):
        text = '## The `core` and [API](README.md) ###\n<a id="custom-anchor"></a>\n'
        self.assertEqual({'the-core-and-api', 'custom-anchor'}, source.markdown_anchors(text))

    def test_existing_document_does_not_make_missing_fragment_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in distribution.source_files(ROOT).items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (root / 'docs/bad-heading.md').write_text('# Existing\n[Missing](README.md#absent)\n[Local](#absent)\n[Valid](#existing)\n')
            (root / 'docs/README.md').write_text('# Present\n')
            failures = source.inspect_source(root)
            self.assertEqual(2, sum('Broken document heading link' in row for row in failures))

    def test_all_current_publication_documents_and_aliases_resolve(self):
        self.assertEqual([], source.inspect_source(ROOT))


if __name__ == '__main__':
    unittest.main()
