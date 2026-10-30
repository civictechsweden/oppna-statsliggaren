import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from zipfile import ZipFile

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from services.artifacts import convert_attachments, converted_path, download_files, file_specs, upload_files
from services.parser import Parser
import statsliggaren
from scripts import build_letters_parquet as builder


class PublicationTests(unittest.TestCase):
    def test_office_conversion_preserves_originals_and_validates_derivatives(self):
        def convert(command, **kwargs):
            out = Path(command[command.index('--outdir') + 1])
            extension = command[command.index('--convert-to') + 1]
            for source in command[command.index('--outdir') + 2:]:
                with ZipFile(out / Path(source).with_suffix('.' + extension).name, 'w') as archive:
                    archive.writestr('word/document.xml' if extension == 'docx' else 'xl/workbook.xml', '<xml/>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'attachments/2026').mkdir(parents=True)
            paths = ['attachments/2026/1.doc', 'attachments/2026/2.xls']
            for path in paths:
                (root/path).write_bytes(b'original')
            with patch('services.artifacts.subprocess.run', side_effect=convert):
                result = convert_attachments(root, paths)
            self.assertEqual(result, ['attachments/2026/1.docx', 'attachments/2026/2.xlsx'])
            for path in paths:
                self.assertEqual((root/path).read_bytes(), b'original')
                self.assertTrue((root/converted_path(path)).exists())

    def test_failed_conversion_does_not_replace_existing_derivative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'attachments/2026').mkdir(parents=True)
            (root/'attachments/2026/1.doc').write_bytes(b'original')
            (root/'attachments/2026/1.docx').write_bytes(b'previous')
            os.utime(root/'attachments/2026/1.docx', (1, 1))
            with patch('services.artifacts.subprocess.run'), self.assertRaisesRegex(RuntimeError, 'did not convert'):
                convert_attachments(root, ['attachments/2026/1.doc'])
            self.assertEqual((root/'attachments/2026/1.docx').read_bytes(), b'previous')

    def test_original_files_use_ids_and_extensions_and_share_attachment_ids(self):
        specs = file_specs(
            {1: {"pdf": "True", "year": "2026"}, 2: {"pdf": "False", "year": "2026"}},
            [{"id": "7", "rbid": "1", "name": "First.DOCX"},
             {"id": "7", "rbid": "2", "name": "First.DOCX"}],
            {1},
        )
        self.assertEqual(set(specs), {"letters/2026/1.pdf", "attachments/2026/7.docx"})
        self.assertTrue(specs["attachments/2026/7.docx"][1])
        self.assertIn("HelaBrevet", specs["letters/2026/1.pdf"][0])

    def test_latest_id_is_numeric_and_case_insensitive(self):
        response = Mock(text='?rbid=9999&amp;x=y ?RBID=10000&amp;x=y')
        self.assertEqual(Parser.parse_latest_remote_rbid(response), 10000)

    def test_file_uploads_are_batched(self):
        api = Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [f"{i}.pdf" for i in range(251)]
            for name in paths:
                (root / name).write_bytes(b"%PDF")
            upload_files(api, "owner/data", root, paths)
        self.assertEqual([len(c.kwargs["operations"]) for c in api.create_commit.call_args_list], [250, 1])

    def test_refreshed_payload_replaces_existing_parquet_row(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "letters.parquet"
            pq.write_table(pa.Table.from_pylist([{"id": 1, "department": "Old", "html": "old", "xhtml": "old", "md": "old"}]), output)
            current = {"id": 1, "department": "New", "html": "new", "xhtml": "new", "md": "new"}
            with patch('sys.argv', ['builder', '--output', str(output)]), \
                 patch.object(builder, '_load_metadata', return_value=(["department"], {1: {"department": "New"}})), \
                 patch.object(builder, '_letter_ids', return_value=[1]), \
                 patch.object(builder, '_build_rows', return_value=[current]):
                builder.main()
            self.assertEqual(pq.read_table(output).to_pylist(), [current])

    def test_missing_payloads_must_be_fetched_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "letters.parquet"
            pq.write_table(pa.Table.from_pylist([{"id": 1, "html": "old", "xhtml": "old", "md": "old"}]), output)
            downloader = Mock(aclose=AsyncMock())
            with patch('sys.argv', ['builder', '--output', str(output)]), \
                 patch.object(builder, '_load_metadata', return_value=([], {1: {}, 2: {}})), \
                 patch.object(builder, '_letter_ids', return_value=[]), \
                 patch.object(builder, 'Downloader', return_value=downloader), \
                 patch.object(builder, 'get_metadatas', new=AsyncMock(return_value=([], [], {}))):
                with self.assertRaisesRegex(RuntimeError, 'Missing letter payloads'):
                    builder.main()
            self.assertEqual(pq.read_table(output)['id'].to_pylist(), [1])


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_source_file_is_reported_and_not_created(self):
        downloader = Mock(_get_with_retry=AsyncMock(return_value=httpx.Response(200)), aclose=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch('services.artifacts.Downloader', return_value=downloader):
            root = Path(directory)
            paths = await download_files({'attachments/2026/1.xls': ('https://example/1', False)}, root, set())
            self.assertEqual(paths, [])
            self.assertIn('empty_response', (root/'unavailable_files.json').read_text())

    async def test_existing_remote_files_are_skipped_but_refreshed_files_are_downloaded(self):
        response = httpx.Response(200, content=b"%PDF-new", headers={"content-type": "application/pdf"})
        downloader = Mock(_get_with_retry=AsyncMock(return_value=response), aclose=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch('services.artifacts.Downloader', return_value=downloader):
            paths = await download_files({'letters/2026/1.pdf': ('https://example/1', False), 'letters/2026/2.pdf': ('https://example/2', True)}, Path(directory), {'letters/2026/1.pdf', 'letters/2026/2.pdf'})
            self.assertEqual(paths, ['letters/2026/2.pdf'])
            self.assertEqual((Path(directory)/'letters/2026/2.pdf').read_bytes(), b'%PDF-new')
        downloader._get_with_retry.assert_awaited_once_with('https://example/2')

    async def test_html_error_page_does_not_overwrite_original(self):
        downloader = Mock(_get_with_retry=AsyncMock(return_value=httpx.Response(200, content=b'<html>Error</html>', headers={'content-type': 'text/html'})), aclose=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch('services.artifacts.Downloader', return_value=downloader):
            root = Path(directory);(root/'letters/2026').mkdir(parents=True);(root/'letters/2026/1.pdf').write_bytes(b'%PDF-old')
            with self.assertRaisesRegex(ValueError, 'Expected a document file'):
                await download_files({'letters/2026/1.pdf': ('https://example/1', True)}, root, set())
            self.assertEqual((root/'letters/2026/1.pdf').read_bytes(), b'%PDF-old')

    async def test_unavailable_file_is_reported_and_not_created(self):
        downloader = Mock(_get_with_retry=AsyncMock(return_value=httpx.Response(404)), aclose=AsyncMock())
        with tempfile.TemporaryDirectory() as directory, patch('services.artifacts.Downloader', return_value=downloader):
            paths = await download_files({'letters/2026/1.pdf': ('https://example/1', False)}, Path(directory), set())
            self.assertEqual(paths, [])
            self.assertFalse((Path(directory)/'letters/2026/1.pdf').exists())


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_includes_gaps_older_than_the_last_hundred(self):
        rows = [{"rbid": "100", "date": "2025-12-18"}, {"rbid": "1500", "date": "2026-10-22"}]
        with patch.object(statsliggaren, "get_local_metadata", return_value=rows), \
             patch.object(statsliggaren, "get_latest_remote_rbid", new=AsyncMock(return_value=1500)):
            ids = await statsliggaren.get_rbids_to_fetch(Mock(), "2025-01-01")
        self.assertIn(101, ids)
        self.assertIn(100, ids)
        self.assertIn(1500, ids)
        self.assertEqual(len(ids), len(set(ids)))
