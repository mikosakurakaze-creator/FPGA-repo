"""Data identity, safe extraction and deterministic holdout regressions."""
import hashlib
from io import BytesIO
from pathlib import Path
import random
import tempfile
import unittest
import zipfile
from PIL import Image
from .data import extract_images, partition, safe_member


class DataTests(unittest.TestCase):
    @staticmethod
    def entries():
        result = []
        for i in range(30):
            name = f'Fog/foggy-{i+1:03d}.jpg'
            result.append({'member': name, 'sha256': f'image-{i}',
                           'rank': hashlib.sha256(('Fog:'+name).encode()).hexdigest()})
        # The duplicate of the approved image must remain held out as well.
        result.append({'member': 'Fog/duplicate-of-approved.jpg', 'sha256': 'image-0', 'rank': '0'*64})
        return result

    def test_holdout_duplicates_and_deterministic_reordering(self):
        entries = self.entries()
        partitions = partition(entries, 10, 5, 'foggy-001.jpg')
        self.assertNotIn('image-0', {e['sha256'] for e in partitions[0]})
        self.assertEqual(sum(e['sha256'] == 'image-0' for e in partitions[1]), 2)
        hashes = [{e['sha256'] for e in group} for group in partitions]
        self.assertFalse(hashes[0] & hashes[1] or hashes[1] & hashes[2] or hashes[0] & hashes[2])
        random.Random(24).shuffle(entries)
        other = partition(entries, 10, 5, 'foggy-001.jpg')
        self.assertEqual([{e['member'] for e in p} for p in partitions], [{e['member'] for e in p} for p in other])

    def test_missing_holdout_and_insufficient_members_fail(self):
        with self.assertRaises(ValueError):
            partition(self.entries(), 10, 5, 'missing.jpg')
        with self.assertRaises(ValueError):
            partition(self.entries(), 100, 5, 'foggy-001.jpg')

    def test_unsafe_paths_rejected(self):
        for name in ('../evil.jpg', '/absolute.jpg', 'C:/evil.jpg', r'..\evil.jpg', 'dir./evil.jpg', '//server/file.jpg'):
            with self.assertRaises(ValueError, msg=name):
                safe_member(name)

    def test_extraction_preserves_image_bytes_and_ignores_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            buffer = BytesIO()
            Image.new('RGB', (7, 5), (10, 20, 30)).save(buffer, format='PNG')
            raw = buffer.getvalue()
            archive = root/'source.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('Fog/sample.png', raw)
                z.writestr('Fog/sample.xml', b'<detection />')
            result = extract_images(archive, 'Fog', root/'out', 'zip-identity')
            self.assertEqual(len(result), 1)
            entry = result[0]
            self.assertEqual((entry['height'], entry['width']), (5, 7))
            self.assertEqual(entry['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(Path(entry['path']).read_bytes(), raw)
            self.assertFalse(list((root/'out').rglob('*.xml')))
            with self.assertRaises(ValueError):
                extract_images(archive, 'Fog', root/'out', 'zip-identity')

    def test_archive_traversal_and_symlink_never_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, symlink in (('../outside.png', False), ('link.png', True)):
                archive = root/('link.zip' if symlink else 'traversal.zip')
                info = zipfile.ZipInfo(name)
                if symlink:
                    info.create_system = 3
                    info.external_attr = 0o120777 << 16
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr(info, b'invalid-image')
                with self.assertRaises(ValueError):
                    extract_images(archive, 'Fog', root/'out', 'identity')
            self.assertFalse((root/'outside.png').exists())


if __name__ == '__main__':
    unittest.main()
