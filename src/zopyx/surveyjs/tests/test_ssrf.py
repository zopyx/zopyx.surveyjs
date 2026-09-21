import socket
import unittest
from unittest.mock import patch

from zopyx.surveyjs.ssrf import validate_post_endpoint_url


class PostEndpointValidationTests(unittest.TestCase):
    def test_allows_public_http_endpoint(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with patch("zopyx.surveyjs.ssrf.socket.getaddrinfo", return_value=addresses):
            self.assertEqual(
                validate_post_endpoint_url(" https://example.com/submit "),
                "https://example.com/submit",
            )

    def test_rejects_non_http_scheme_before_dns(self):
        with patch("zopyx.surveyjs.ssrf.socket.getaddrinfo") as getaddrinfo:
            with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
                validate_post_endpoint_url("file:///etc/passwd")
        getaddrinfo.assert_not_called()

    def test_rejects_private_dns_result(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 80))]
        with patch("zopyx.surveyjs.ssrf.socket.getaddrinfo", return_value=addresses):
            with self.assertRaisesRegex(ValueError, "blocked address"):
                validate_post_endpoint_url("http://internal.example/submit")

    def test_rejects_unresolvable_host(self):
        with patch(
            "zopyx.surveyjs.ssrf.socket.getaddrinfo",
            side_effect=socket.gaierror,
        ):
            with self.assertRaisesRegex(ValueError, "could not be resolved"):
                validate_post_endpoint_url("https://missing.example/submit")

    def test_strict_mode_requires_an_exact_or_wildcard_host_match(self):
        with patch(
            "zopyx.surveyjs.ssrf.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
            ],
        ):
            self.assertEqual(
                validate_post_endpoint_url(
                    "https://hooks.example.com/submit",
                    mode="allowlist",
                    allowlist=["*.example.com"],
                ),
                "https://hooks.example.com/submit",
            )
            with self.assertRaisesRegex(ValueError, "allowlist"):
                validate_post_endpoint_url(
                    "https://other.example.net/submit",
                    mode="allowlist",
                    allowlist=["*.example.com"],
                )

    def test_strict_mode_does_not_allow_the_wildcard_apex(self):
        with patch(
            "zopyx.surveyjs.ssrf.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
            ],
        ):
            with self.assertRaisesRegex(ValueError, "allowlist"):
                validate_post_endpoint_url(
                    "https://example.com/submit",
                    mode="allowlist",
                    allowlist=["*.example.com"],
                )


if __name__ == "__main__":
    unittest.main()
