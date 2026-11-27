from pathlib import Path
import tempfile
import unittest

import httpx

from scripts.benchmark_docling_letters import convert, evaluate, expected_content


XHTML = '''<html><body><table><tr><td>Letterhead</td></tr></table>
<h1>Letter</h1><p>Opening paragraph.</p><h2>Activities</h2><h3>Assignment</h3>
<p>Preserve this important assignment.</p><table><tr><td colspan="2">Amount</td></tr>
<tr><td>Funding</td><td>1 234</td></tr></table></body></html>'''


def result():
    return {
        "documents": [{"errors": [], "content": {"json_content": {
            "texts": [{"text": "Letter Activities Assignment Opening paragraph. Preserve this important assignment.", "content_layer": "body"}],
            "tables": [{"content_layer": "body", "data": {"table_cells": [
                {"text": "Amount", "row_span": 1, "col_span": 2},
                {"text": "Funding", "row_span": 1, "col_span": 1},
                {"text": "1 234", "row_span": 1, "col_span": 1},
            ]}}],
        }}}],
        "chunks": [{"chunk_index": 0, "num_tokens": 60,
                    "headings": ["Letter", "Activities", "Assignment"],
                    "raw_text": "Opening paragraph. Preserve this important assignment.\n| Amount | Amount |\n| Funding | 1 234 |"}],
    }


class QualityTests(unittest.TestCase):
    def test_preserves_prose_tables_paths_and_structured_span(self):
        expected = expected_content(XHTML)
        namespaced = XHTML.replace("<html>", '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml">', 1)
        self.assertEqual(expected_content(namespaced), expected)
        self.assertNotIn("Letterhead", expected["cells"])
        self.assertEqual(expected["headings"][-1], ["Letter", "Activities", "Assignment"])
        report = evaluate(XHTML, result())
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["expected_spans"], 1)
        self.assertEqual(report["document_spans"], 1)
        self.assertEqual(report["tiny_chunks_under_200_chars"], 1)

    def test_reports_content_loss_even_if_chunk_and_table_counts_match(self):
        converted = result()
        converted["chunks"][0]["raw_text"] = "Opening paragraph. Funding Amount 999"
        converted["documents"][0]["content"]["json_content"]["texts"] = []
        report = evaluate(XHTML, converted)
        self.assertEqual(report["status"], "review")
        self.assertIn("Preserve this important assignment.", report["issues"]["paragraphs_missing_from_chunks"])
        self.assertEqual(report["issues"]["numeric_cells_missing_from_chunks"], ["1 234"])
        self.assertEqual(len(report["issues"]["paragraphs_missing_from_document"]), 2)

    def test_reports_path_budget_and_span_loss(self):
        converted = result()
        converted["chunks"][0].update(headings=["Letter", "Assignment"], num_tokens=1537)
        converted["documents"][0]["content"]["json_content"]["tables"][0]["data"]["table_cells"][0]["col_span"] = 1
        issues = evaluate(XHTML, converted)["issues"]
        self.assertEqual(issues["over_budget_chunks"], [0])
        self.assertEqual(issues["unexpected_chunk_heading_paths"], [["Letter", "Assignment"]])
        self.assertTrue(issues["heading_paths_missing_from_chunks"])
        self.assertTrue(issues["spans_missing_from_document"])

    def test_table_cell_heading_is_inline_not_section(self):
        source = XHTML.replace("Amount</td>", "<h4>Amount</h4></td>")
        self.assertEqual(expected_content(source)["headings"], expected_content(XHTML)["headings"])

    def test_empty_section_is_diagnostic_rather_than_content_loss(self):
        source = XHTML.replace("<h2>Activities</h2>", "<h2>Empty section</h2><h2>Activities</h2>")
        converted = result()
        converted["documents"][0]["content"]["json_content"]["texts"][0]["text"] += " Empty section"
        report = evaluate(source, converted)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["diagnostics"]["empty_section_heading_paths_absent_from_chunks"], [["Letter", "Empty section"]])


class AsyncServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_poll_result_and_resume_saved_handle(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if request.url.path == "/v1/convert/file/async":
                return httpx.Response(200, json={"task_id": "convert-job"})
            if request.url.path == "/v1/chunk/hybrid/file/async":
                self.assertIn(b'microsoft/harrier-oss-v1-0.6b', request.content)
                self.assertIn(b'include_converted_doc', request.content)
                self.assertIn(b'json_docling', request.content)
                self.assertIn(b'chunking_use_markdown_tables', request.content)
                return httpx.Response(200, json={"task_id": "test-job"})
            if "/poll/" in request.url.path:
                return httpx.Response(200, json={"task_status": "success"})
            if request.url.path.endswith("convert-job"):
                return httpx.Response(200, json={"document": {"json_content": result()["documents"][0]["content"]["json_content"]}})
            return httpx.Response(200, json=result())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as client:
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                first = await convert(client, XHTML, 1, directory)
                second = await convert(client, XHTML, 1, directory)
                self.assertEqual(first, second)
                self.assertEqual(calls.count("/v1/chunk/hybrid/file/async"), 1)
                with self.assertRaisesRegex(ValueError, "different input"):
                    await convert(client, XHTML.replace("Funding", "Changed"), 1, directory)

    async def test_explicit_service_failure_surfaces(self):
        def handler(request):
            if request.url.path.endswith("/async"):
                return httpx.Response(200, json={"task_id": "bad-job"})
            return httpx.Response(200, json={"task_status": "failure", "error_message": "broken table"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as client:
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(RuntimeError, "broken table"):
                    await convert(client, XHTML, 1, Path(temporary))


if __name__ == "__main__":
    unittest.main()
