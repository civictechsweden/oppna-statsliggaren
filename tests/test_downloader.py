import unittest
from unittest.mock import patch

import httpx

from services.downloader import DOMAIN, Downloader


GATEWAY = "example.execute-api.eu-north-1.amazonaws.com"


class DownloaderRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        def start(rotator, *args, **kwargs):
            rotator.endpoints = [GATEWAY]

        for mocked in (
            patch.dict("os.environ", {"USE_IP_ROTATOR": "true"}),
            patch("httpx_ip_rotator.rotator.Rotator.start", autospec=True, side_effect=start),
            patch("httpx_ip_rotator.rotator.Rotator.shutdown"),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)
        self.downloader = Downloader()
        self.addAsyncCleanup(self.downloader.aclose)

    async def test_relative_redirects_keep_source_origin_and_use_gateway(self):
        source = DOMAIN + "/link/c9e3e8272516411ab8aeeddbb5cb5aa6.aspx?PeriodId=2025"
        for location, target in (
            ("/statsliggaren/?PeriodId=2025", DOMAIN + "/statsliggaren/?PeriodId=2025"),
            ("../statsliggaren/?PeriodId=2025", DOMAIN + "/statsliggaren/?PeriodId=2025"),
            ("?PeriodId=2026", source.replace("2025", "2026")),
            (DOMAIN + "/statsliggaren/?PeriodId=2025", DOMAIN + "/statsliggaren/?PeriodId=2025"),
        ):
            with self.subTest(location=location):
                requests = []

                async def network(transport, request):
                    requests.append((str(request.url), dict(request.headers)))
                    if len(requests) == 1:
                        return httpx.Response(302, headers={"location": location,
                                                          "set-cookie": "session=area; Path=/; Secure"})
                    if request.url.host != GATEWAY or not request.url.path.startswith("/ProxyStage/"):
                        return httpx.Response(403)
                    return httpx.Response(200, text="year page")

                self.downloader.s.cookies.clear()
                with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", autospec=True, side_effect=network):
                    response = await self.downloader._get_with_retry(source, retries=1)

                expected = httpx.URL(target)
                self.assertEqual(response.text, "year page")
                self.assertEqual(str(response.url), target)
                self.assertEqual(str(response.history[0].url), source)
                self.assertEqual(response.request.headers["host"], "www.statskontoret.se")
                self.assertEqual(len(requests), 2)
                self.assertEqual(requests[0][0], source.replace(DOMAIN, f"https://{GATEWAY}/ProxyStage"))
                self.assertEqual(requests[1][0], str(expected.copy_with(host=GATEWAY, path="/ProxyStage" + expected.path)))
                self.assertEqual(requests[1][1]["host"], GATEWAY)
                self.assertEqual(requests[1][1]["cookie"], "session=area")

    async def test_transport_failure_does_not_mutate_original_request(self):
        request = self.downloader.s.build_request("GET", DOMAIN + "/statsliggaren/",
                                                  headers={"X-Forwarded-For": "192.0.2.1"})
        original_headers = dict(request.headers)
        with patch.object(httpx.AsyncHTTPTransport, "handle_async_request", autospec=True,
                          side_effect=httpx.ReadTimeout("timed out")):
            with self.assertRaises(httpx.ReadTimeout):
                await self.downloader.s.send(request)
        self.assertEqual(str(request.url), DOMAIN + "/statsliggaren/")
        self.assertEqual(dict(request.headers), original_headers)
