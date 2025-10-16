import unittest
import socket
from unittest.mock import Mock, patch, MagicMock

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser import URL

class TestKeepAlive(unittest.TestCase):
    
    def setUp(self):
        """Clear socket cache before each test"""
        URL.socket_cache.clear()
    
    def tearDown(self):
        """Clean up sockets after each test"""
        URL.close_all_sockets()
    
    def test_socket_cache_starts_empty(self):
        """Test that socket cache is initially empty"""
        self.assertEqual(len(URL.socket_cache), 0)
    
    def test_socket_cache_key_format(self):
        """Test that socket cache key is (scheme, host, port)"""
        url = URL("https://example.org/")
        cache_key = (url.scheme, url.host, url.port)
        self.assertEqual(cache_key, ('https', 'example.org', 443))
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_first_request_creates_socket(self, mock_ssl_ctx, mock_socket):
        """Test that first request creates a new socket"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        url = URL("https://example.org/")
        
        # Should start with empty cache
        self.assertEqual(len(URL.socket_cache), 0)
        
        # Make request
        body = url.request()
        
        # Should have created socket
        mock_socket.assert_called_once()
        mock_sock.connect.assert_called_once_with(('example.org', 443))
        
        # Should have cached the socket
        self.assertEqual(len(URL.socket_cache), 1)
        cache_key = ('https', 'example.org', 443)
        self.assertIn(cache_key, URL.socket_cache)
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_second_request_reuses_socket(self, mock_ssl_ctx, mock_socket):
        """Test that second request to same server reuses socket"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock recv to simulate alive connection (BlockingIOError = no data yet)
        mock_wrapped_sock.recv.side_effect = BlockingIOError()
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            # Second request
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        # First request
        url1 = URL("https://example.org/")
        url1.request()
        
        # Should have created 1 socket
        self.assertEqual(mock_socket.call_count, 1)
        self.assertEqual(len(URL.socket_cache), 1)
        
        # Second request to same server
        url2 = URL("https://example.org/")
        url2.request()
        
        # Should still only have 1 socket (reused)
        self.assertEqual(mock_socket.call_count, 1)
        self.assertEqual(len(URL.socket_cache), 1)
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_different_servers_create_different_sockets(self, mock_ssl_ctx, mock_socket):
        """Test that requests to different servers create different sockets"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            # Second request
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            # Third request
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        # Request to server 1
        url1 = URL("https://example.org/")
        url1.request()
        
        # Request to server 2
        url2 = URL("https://example.com/")
        url2.request()
        
        # Request to server 3
        url3 = URL("https://google.com/")
        url3.request()
        
        # Should have created 3 sockets
        self.assertEqual(mock_socket.call_count, 3)
        self.assertEqual(len(URL.socket_cache), 3)
        
        # Check all cache keys exist
        self.assertIn(('https', 'example.org', 443), URL.socket_cache)
        self.assertIn(('https', 'example.com', 443), URL.socket_cache)
        self.assertIn(('https', 'google.com', 443), URL.socket_cache)
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_different_ports_create_different_sockets(self, mock_ssl_ctx, mock_socket):
        """Test that same host but different ports create different sockets"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            # Second request
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        # Request to port 443
        url1 = URL("https://example.org/")
        url1.request()
        
        # Request to port 8443
        url2 = URL("https://example.org:8443/")
        url2.request()
        
        # Should have created 2 sockets
        self.assertEqual(mock_socket.call_count, 2)
        self.assertEqual(len(URL.socket_cache), 2)
        
        # Check both cache keys exist
        self.assertIn(('https', 'example.org', 443), URL.socket_cache)
        self.assertIn(('https', 'example.org', 8443), URL.socket_cache)
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_http_and_https_same_host_different_sockets(self, mock_ssl_ctx, mock_socket):
        """Test that HTTP and HTTPS to same host create different sockets"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            # Second request
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        mock_sock.makefile.return_value = mock_response
        
        # HTTPS request
        url1 = URL("https://example.org/")
        url1.request()
        
        # HTTP request to same host
        url2 = URL("http://example.org/")
        url2.request()
        
        # Should have created 2 sockets
        self.assertEqual(len(URL.socket_cache), 2)
        
        # Check both cache keys exist
        self.assertIn(('https', 'example.org', 443), URL.socket_cache)
        self.assertIn(('http', 'example.org', 80), URL.socket_cache)
    
    def test_close_all_sockets_clears_cache(self):
        """Test that close_all_sockets clears the cache"""
        # Manually add mock sockets to cache
        mock_sock1 = MagicMock()
        mock_sock2 = MagicMock()
        
        URL.socket_cache[('https', 'example.org', 443)] = mock_sock1
        URL.socket_cache[('https', 'example.com', 443)] = mock_sock2
        
        self.assertEqual(len(URL.socket_cache), 2)
        
        # Close all sockets
        URL.close_all_sockets()
        
        # Cache should be empty
        self.assertEqual(len(URL.socket_cache), 0)
        
        # Sockets should have been closed
        mock_sock1.close.assert_called_once()
        mock_sock2.close.assert_called_once()
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_dead_socket_is_replaced(self, mock_ssl_ctx, mock_socket):
        """Test that a dead socket is replaced with a new one"""
        # Setup mocks
        mock_sock_old = MagicMock()
        mock_sock_new = MagicMock()
        mock_socket.side_effect = [mock_sock_old, mock_sock_new]
        
        mock_wrapped_sock_old = MagicMock()
        mock_wrapped_sock_new = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.side_effect = [
            mock_wrapped_sock_old,
            mock_wrapped_sock_new
        ]
        
        # Mock the response for first request
        mock_response_old = MagicMock()
        mock_response_old.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response_old.read.return_value = b"Hello, World!"
        mock_wrapped_sock_old.makefile.return_value = mock_response_old
        
        # First request succeeds
        mock_wrapped_sock_old.recv.side_effect = BlockingIOError()
        url1 = URL("https://example.org/")
        url1.request()
        
        self.assertEqual(len(URL.socket_cache), 1)
        
        # Simulate socket dying (recv returns empty bytes = connection closed)
        mock_wrapped_sock_old.recv.side_effect = None
        mock_wrapped_sock_old.recv.return_value = b''
        
        # Mock the response for second request
        mock_response_new = MagicMock()
        mock_response_new.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response_new.read.return_value = b"Hello, World!"
        mock_wrapped_sock_new.makefile.return_value = mock_response_new
        mock_wrapped_sock_new.recv.side_effect = BlockingIOError()
        
        # Second request should detect dead socket and create new one
        url2 = URL("https://example.org/")
        url2.request()
        
        # Should have created 2 sockets total (old one died)
        self.assertEqual(mock_socket.call_count, 2)
        
        # Old socket should have been closed
        mock_wrapped_sock_old.close.assert_called()
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_request_uses_http_1_1(self, mock_ssl_ctx, mock_socket):
        """Test that requests use HTTP/1.1 for keep-alive"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        url = URL("https://example.org/path")
        url.request()
        
        # Check that the request sent contains HTTP/1.1
        sent_data = mock_wrapped_sock.send.call_args[0][0].decode('utf8')
        self.assertIn("GET /path HTTP/1.1", sent_data)
        self.assertIn("Connection: keep-alive", sent_data)
    
    @patch('socket.socket')
    @patch('ssl.create_default_context')
    def test_reads_exact_content_length(self, mock_ssl_ctx, mock_socket):
        """Test that request reads exactly Content-Length bytes"""
        # Setup mocks
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_wrapped_sock = MagicMock()
        mock_ssl_ctx.return_value.wrap_socket.return_value = mock_wrapped_sock
        
        # Mock the response
        mock_response = MagicMock()
        mock_response.readline.side_effect = [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n"
        ]
        mock_response.read.return_value = b"Hello, World!"
        mock_wrapped_sock.makefile.return_value = mock_response
        
        url = URL("https://example.org/")
        body = url.request()
        
        # Should have called read with exact content length
        mock_response.read.assert_called_with(13)
        self.assertEqual(body, "Hello, World!")

if __name__ == "__main__":
    unittest.main(verbosity=2)