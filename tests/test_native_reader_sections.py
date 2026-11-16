"""Synthetic presentation tests; no source reading or semantic assessment."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_native_reader import fixture, reader

SECTIONS = ('why', 'objective', 'methods', 'findings', 'conclusions', 'key_points', 'limitations')


class NativeReaderSectionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reader-sections-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.observations, self.content, self.bibliography = fixture()
        for language, content in self.content.items():
            content['format'] = 'native-reader-content/1.2'
            record = content['records'][0]
            record['sections'] = {
                name: [{'id': 'section-' + name, 'text': 'Authored ' + name,
                        'status': 'supported', 'reason': 'Synthetic caller annotation, not verified.',
                        'reading_level': record['reading_level'], 'reading_ref': record['reading_ref'],
                        'locator': 'Synthetic section 1'}]
                for name in SECTIONS
            }
            record['sections']['conclusions'][0].update(status='analyst_inference', reason='Tentative interpretation, not author result.')
            record['sections']['limitations'][0].update(status='unknown', reason='Not assessed in this input.', locator=None)

    def prepare(self):
        paths = []
        for name, payload in [('observations', self.observations), ('en', self.content['en']), ('zh', self.content['zh-TW']), ('bib', self.bibliography)]:
            path = self.root / (name + '.json')
            path.write_bytes(reader.canonical(payload))
            paths.append(path)
        return reader.prepare(*paths)

    def rejected(self):
        with self.assertRaises(reader.ReaderError):
            self.prepare()
        self.assertFalse((self.root / 'output').exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX temporary-directory alias probe')
    def test_fixture_canonicalizes_owned_temp_alias_without_relaxing_reader(self):
        actual = self.root / 'actual-temp'
        actual.mkdir()
        alias = self.root / 'linked-temp'
        alias.symlink_to(actual, target_is_directory=True)
        probe = NativeReaderSectionsTests('test_seven_sections_three_states_roundtrip_and_reopen')
        with patch('tests.test_native_reader_sections.tempfile.TemporaryDirectory',
                   return_value=SimpleNamespace(name=str(alias), cleanup=lambda: None)):
            probe.setUp()
        try:
            self.assertEqual(probe.root, actual.resolve())
            probe.prepare()
            # Only this owned test fixture is canonicalized; the production
            # boundary must still refuse a caller-supplied linked path.
            probe.root = alias
            with self.assertRaisesRegex(reader.ReaderError, 'linked paths are not supported'):
                probe.prepare()
        finally:
            probe.doCleanups()

    def test_seven_sections_three_states_roundtrip_and_reopen(self):
        inputs, files, manifest = self.prepare()
        exported = json.loads(files['native-reader.json'])
        self.assertEqual(exported['content'], self.content)
        self.assertEqual(exported['observations'], self.observations)
        self.assertEqual(exported['observations']['completion']['status'], 'partial')
        for language in self.content:
            html = files['reader.' + language + '.html'].decode()
            for name in SECTIONS:
                self.assertIn('Authored ' + name, html)
            self.assertIn('supported', html)
            self.assertIn('analyst_inference', html)
            self.assertIn('unknown', html)
            self.assertIn('Not assessed in this input.', html)
        output = self.root / 'output'
        reader.generate(output, inputs, files, manifest)
        self.assertEqual(json.loads((output / 'native-reader.json').read_bytes())['content'], self.content)
        self.assertNotIn('human_acceptance', exported)
        self.assertNotIn('semantic_support', exported)

    def test_legacy_formats_reject_sections(self):
        for version in ('1.0', '1.1'):
            with self.subTest(version=version):
                self.content['en']['format'] = 'native-reader-content/' + version
                self.rejected()

    def test_section_set_exact_and_nonempty_bounded(self):
        original = copy.deepcopy(self.content)
        for mutate in (
            lambda s: s.pop('why'),
            lambda s: s.update(other=s['why']),
            lambda s: s.update(why=[]),
            lambda s: s.update(why=s['why'] * 13),
            lambda s: s.update(why='not an array'),
        ):
            self.content = copy.deepcopy(original)
            mutate(self.content['en']['records'][0]['sections'])
            self.rejected()

    def test_annotations_strict_and_never_inferred(self):
        original = copy.deepcopy(self.content)
        for key, value in [('status', 'accepted'), ('status', None), ('reason', ''), ('reading_ref', 'different'), ('extra', True), ('locator', None)]:
            with self.subTest(key=key, value=value):
                self.content = copy.deepcopy(original)
                self.content['en']['records'][0]['sections']['why'][0][key] = value
                self.rejected()
        self.content = copy.deepcopy(original)
        del self.content['en']['records'][0]['sections']['why'][0]['status']
        self.rejected()

    def test_no_reading_scope_or_version_upgrade(self):
        original = copy.deepcopy(self.content)
        for mutate in (
            lambda r: r.update(version='v9'),
            lambda r: r.update(reading_level='abstract'),
            lambda r: r['sections']['why'][0].update(reading_level='invalid'),
            lambda r: r['sections']['why'][0].update(reading_level='metadata'),
        ):
            self.content = copy.deepcopy(original)
            mutate(self.content['en']['records'][0])
            self.rejected()
        self.content = copy.deepcopy(original)
        self.content['en']['records'][1]['sections'] = copy.deepcopy(self.content['en']['records'][0]['sections'])
        for items in self.content['en']['records'][1]['sections'].values():
            items[0].update(id=items[0]['id'] + '-abstract', reading_ref='saved:S2')
        self.rejected()  # full-text annotation on an abstract record

    def test_unknown_and_inference_do_not_require_a_locator(self):
        for content in self.content.values():
            record = content['records'][0]
            for name in ('conclusions', 'limitations'):
                record['sections'][name][0]['locator'] = None
        self.prepare()

    def test_cross_language_section_status_and_scope_are_bound(self):
        original = copy.deepcopy(self.content)
        for key, value in [('status', 'analyst_inference'), ('reading_level', 'excerpt'), ('locator', 'Different passage')]:
            with self.subTest(key=key):
                self.content = copy.deepcopy(original)
                self.content['zh-TW']['records'][0]['sections']['why'][0][key] = value
                self.rejected()
        self.content = copy.deepcopy(original)
        sections = self.content['zh-TW']['records'][0]['sections']
        sections['why'], sections['objective'] = sections['objective'], sections['why']
        self.rejected()

    def test_cross_language_prose_may_differ_without_parity_claim(self):
        item = self.content['zh-TW']['records'][0]['sections']['why'][0]
        item.update(text='由呼叫者提供的中文。', reason='僅測呈現，不代表翻譯審查。')
        _, files, _ = self.prepare()
        self.assertIn('由呼叫者提供的中文。', files['reader.zh-TW.html'].decode())
        self.assertIn('不認證實際閱讀', files['reader.zh-TW.html'].decode())

    def test_duplicate_identity_rejected_across_sections_and_flat_claims(self):
        original = copy.deepcopy(self.content)
        for duplicate in ('section-objective', 'CS1'):
            self.content = copy.deepcopy(original)
            self.content['en']['records'][0]['sections']['why'][0]['id'] = duplicate
            self.rejected()

    def test_same_id_cannot_drop_annotation_in_other_language(self):
        record = self.content['zh-TW']['records'][0]
        item = record['sections']['why'][0]
        record['claims'].append({key: item[key] for key in ('id', 'text', 'reading_level', 'reading_ref', 'locator')})
        del record['sections']
        self.rejected()

    def test_missing_sections_stay_missing_and_legacy_bytes_unchanged(self):
        for version in ('1.0', '1.1'):
            with self.subTest(legacy_version=version):
                self.observations, self.content, self.bibliography = fixture()
                for content in self.content.values():
                    content['format'] = 'native-reader-content/' + version
                _, legacy, legacy_manifest = self.prepare()
                for content in self.content.values():
                    content['format'] = 'native-reader-content/1.2'
                _, newer, newer_manifest = self.prepare()
                exported = json.loads(newer['native-reader.json'])
                for language in ('en', 'zh-TW'):
                    for record in exported['content'][language]['records']:
                        self.assertNotIn('sections', record)
                    name = 'reader.' + language + '.html'
                    old = legacy[name].decode()
                    new = newer[name].decode()
                    # The format change alters only these two content-input
                    # digests. Normalize their exact, uniquely occurring values,
                    # not the footer, all hashes, or arbitrary HTML content.
                    for input_language in ('en', 'zh-TW'):
                        old_hash = legacy_manifest['inputs'][input_language]['sha256']
                        new_hash = newer_manifest['inputs'][input_language]['sha256']
                        self.assertNotEqual(old_hash, new_hash)
                        self.assertEqual(old.count(old_hash), 1)
                        self.assertEqual(new.count(new_hash), 1)
                        marker = 'CONTENT_SHA256[' + input_language + ']'
                        old = old.replace(old_hash, marker)
                        new = new.replace(new_hash, marker)
                    self.assertEqual(old, new, (version, language))

    def test_section_prose_reason_and_locator_are_escaped(self):
        for content in self.content.values():
            item = content['records'][0]['sections']['why'][0]
            item.update(text='<script>alert(1)</script>', reason='<img onerror="alert(1)">', locator='<b>section 1</b>')
        _, files, _ = self.prepare()
        for language in self.content:
            html = files['reader.' + language + '.html'].decode()
            self.assertNotIn('<script>', html)
            self.assertNotIn('<img ', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertIn('&lt;b&gt;section 1&lt;/b&gt;', html)


if __name__ == '__main__':
    unittest.main()
