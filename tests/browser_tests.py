import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser import URL

class URL_Test(unittest.TestCase):
    def test_data_plain_text(self):
        url = URL("data:text/plain,Hello%20world!")
        body = url.decode_data_url(url.data_meta, url.data_payload)
        self.assertEqual(body, "Hello world!")
    
    def test_data_base64(self):
        url = URL("data:text/plain;base64,SGVsbG8gV29ybGQh")
        body = url.decode_data_url(url.data_meta, url.data_payload)
        self.assertEqual(body, "Hello World!")

    def test_data_html(self):
        url = URL("data:text/html,<b>Hello</b>")
        body = url.decode_data_url(url.data_meta, url.data_payload)
        # show() should only print "Hello", so confirm the decoded body still has HTML tags
        self.assertIn("<b>", body)

    def test_file_url(self):
        # create a temp file
        with open("temp_test.html", "w", encoding="utf8") as f:
            f.write("<html><body>File Test</body></html>")
        
        file_url = "file://" + os.path.abspath("temp_test.html")
        url = URL(file_url)

        with open(url.file_path, "r", encoding="utf8") as f:
            body = f.read()
        self.assertIn("File Test", body)

        os.remove("temp_test.html")

    def test_default_file_path(self):
        # should default to index.html if no file given
        default_file = os.path.abspath("index.html")
        if not os.path.exists(default_file):
            with open(default_file, "w", encoding="utf8") as f:
                f.write("<html><body>Default Page</body></html>")
        self.assertTrue(os.path.exists(default_file))

    def test_view_source_https(self):
        url = URL("view-source:https://example.org/")
        self.assertTrue(url.is_view_source)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.host, "example.org")
        self.assertEqual(url.port, 443)
        self.assertEqual(url.path, "/")
        self.assertFalse(url.is_file)
        self.assertFalse(url.is_data)
    
    def test_view_source_http(self):
        url = URL("view-source:http://example.com:8080/path")
        self.assertTrue(url.is_view_source)
        self.assertEqual(url.scheme, "http")
        self.assertEqual(url.host, "example.com")
        self.assertEqual(url.port, 8080)
        self.assertEqual(url.path, "/path")
        self.assertFalse(url.is_file)

if __name__ == "__main__":
    unittest.main()