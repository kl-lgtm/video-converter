import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


class MediaTests(unittest.TestCase):
    def test_media_service_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec('media'), '缺少转换服务 media.py')

    def test_destination_protects_source_and_existing_file(self):
        from media import validate_destination
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '中文 输入.mp4'
            source.write_bytes(b'original')
            with self.assertRaises(ValueError):
                validate_destination(source, source)
            target = Path(folder) / '已存在.mp4'
            target.write_bytes(b'keep')
            with self.assertRaises(ValueError):
                validate_destination(source, target)
            self.assertEqual(target.read_bytes(), b'keep')
            with self.assertRaises(ValueError):
                validate_destination(source, Path(folder) / 'missing' / 'out.mp4')

    def test_parameters_keep_paths_separate_and_audio_optional(self):
        from media import conversion_arguments
        source = Path('中文 folder') / 'input.mp4'
        target = Path('output folder') / 'temp.mkv'
        args = conversion_arguments(source, target, '均衡', 2)
        self.assertIn(str(source), args)
        self.assertEqual(args[-1], str(target))
        self.assertIn('0:2', args)
        self.assertIn('0:a:0?', args)
        self.assertIn('libx264', args)

    def test_publish_never_overwrites_a_racing_destination(self):
        from media import publish_output
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder) / 'partial.mp4'
            target = Path(folder) / 'final.mp4'
            temp.write_bytes(b'new')
            target.write_bytes(b'keep')
            with self.assertRaises(OSError):
                publish_output(temp, target)
            self.assertEqual(target.read_bytes(), b'keep')

    def test_progress_handles_unknown_and_clamps_before_verification(self):
        from media import progress_percent
        self.assertIsNone(progress_percent('1000000', None))
        self.assertIsNone(progress_percent('N/A', 5))
        self.assertEqual(progress_percent('1000000', 2), 50)
        self.assertEqual(progress_percent('9000000', 2), 99)


if __name__ == '__main__':
    unittest.main()
