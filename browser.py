import socket
import ssl
import base64
import urllib.parse
import os

class URL:
    """A class to parse and handle URLs, including file, data, http, and https schemes."""
    
    # socket cache for keep-alive connections
    socket_cache = {}

    # HTTP response cache
    http_cache = {}

    # max redirects to prevent infinite loops
    MAX_REDIRECTS = 10

    def __init__(self, url):
        """Parse the given URL and initialize attributes."""

        self.is_file = False
        self.is_data = False
        self.is_view_source = False

        url = url.strip() # strip white space

        # -- VIEW SOURCE --
        if url.startswith("view-source:"):
            self.is_view_source = True
            inner_url = url[len("view-source:"):].lstrip() # strip spaces after prefix

            inner = URL(inner_url)
            
            self.scheme = inner.scheme
            self.is_file = inner.is_file
            self.file_path = getattr(inner, "file_path", None)
            self.is_data = inner.is_data
            self.data_meta = getattr(inner, "data_meta", None)
            self.data_payload = getattr(inner, "data_payload", None)
            self.host = getattr(inner, "host", None)
            self.port = getattr(inner, "port", None)
            self.path = getattr(inner, "path", None)

            return 

        # -- DATA --
        if url.startswith("data:"):
            # store the raw meta and payload parts for later
            self.scheme = "data"
            self.is_data = True

            # everything after data
            data_rest = url[5:]

            # split at the first comma into metadata and data payload
            if ',' in data_rest:
                meta, payload = data_rest.split(',', 1)
            else:
                meta, payload = '', ''
                
            self.data_meta = meta
            self.data_payload = payload

            return

        # --- SCHEME/SPLIT ---

        if "://" in url:
            self.scheme, url = url.split("://", 1)
        else:
            # if no scheme treat as file path
            self.scheme = "file"
            self.is_file = True
            self.file_path = os.path.normpath(url)
            return

        # --- FILE URL ---

        # if the url given is a file, then set is_file to true, then get the file path which is everything after
        # 'file://'
        if self.scheme == "file":
            self.is_file = True
            self.file_path = url

            # remove leading slash on Windows drive letters like /C:/...
            if self.file_path.startswith("/") and len(self.file_path) > 2 and self.file_path[2] == ":":
                self.file_path = self.file_path[1:]

            # normalize slashes for safety
            self.file_path = os.path.normpath(self.file_path)

            # if the user never sumitted a path to a file, this is a default
            if self.file_path.strip() == "":
                self.file_path = os.path.normpath(
                    "C:/Users/matas/PersonalProjects/Browser/index.html"
                )

            return

        # --- HTTP/HTTPS ---

        assert self.scheme in ["http", "https"]

        # usually the ports for http are 80, and 443 for https
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        # Get the host from the path, the host comes after the first '/'
        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)

        # if the URL comes with a custom port then extract that port out of the url
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

        self.path = "/" + url

    def decode_data_url(self, meta, payload):
        """Decode a data URL and return the content as a string."""

        # decode a data url payload
        # meta: part before the comma
        # payload: part after the comma

        is_base64 = False
        charset = None

        parts = meta.split(";") if meta else []

        # first part might be a mediatype (e.g. "text/html") - we dont really need it
        for p in parts[1:]: # skips mediatype at index 0
            if p.lower() == 'base64':
                is_base64 = True
            elif p.lower().startswith('charset='):
                charset = p.split('=', 1)[1]
        
        # decode payload bytes
        try:
            if is_base64:
                raw = base64.b64decode(payload, validate=False)
            else:
                # precent-decode to bytes
                raw = urllib.parse.unquote_to_bytes(payload)
        except Exception:
            # fallback: treat as raw bytes of the literal payload
            raw = payload.encode('utf-8', errors='replace')
        
        # Choose charset: prefer explicit, otherwise try utf-8 then latin-1
        if not charset:
            # RFC 2397 default for text/* is US-ASCII, but UTF-8 is more practical
            for cs in ('utf-8', 'latin-1'):
                try:
                    return raw.decode(cs)
                except Exception:
                    continue
            return raw.decode('utf-8', errors='replace')
        else:
            try:
                return raw.decode(charset, errors='replace')
            except Exception:
                return raw.decode('utf-8', errors='replace')
            
    def get_socket(self):
        """Get or create a socket for this host:port, with keep-alive."""
        cache_key = (self.scheme, self.host, self.port)

        # try to use existing socket from cache
        if cache_key in URL.socket_cache:
            s = URL.socket_cache[cache_key]
            # check if socket is still valid by seeing if its readable

            try:
                # peek at the socket, if theres unexpected data. connection was closed
                s.setblocking(False)
                data = s.recv(1, socket.MSG_PEEK)
                s.setblocking(True)

                if data == b'':
                    # Socket is closed by server
                    raise Exception("Socket closed")

                # if it gets here and theres still data its unusal                
            except BlockingIOError:
                # no data available, socket is still open
                s.setblocking(True)
                return s
            except Exception:
                # some other error, close and remove from cache
                try:
                    s.close()
                except Exception:
                    pass
                del URL.socket_cache[cache_key]
                # fall through to create a new socket

        # create a new socket
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )

        # Connect to the host on port 80
        s.connect((self.host, self.port))

        # if its https, you wrap the socket with a TLS layer for encryption
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        
        # cache the new socket
        URL.socket_cache[cache_key] = s
        return s

    def resolve_redirect_location(self, location):
        """Resolve a redirect location to an absolute URL."""
        
        # if location is a full URL, return as is
        if "://" in location:
            return location
        
        # if location starts with '/', its absolute path on the same host
        if location.startswith("/"):
            return f"{self.scheme}://{self.host}:{self.port}{location}"
        
        # otherwise its a relative path
        base_path = self.path.rsplit("/", 1)[0]  # remove last segment
        return f"{self.scheme}://{self.host}:{self.port}{base_path}/{location}"

    def request(self, redirect_count=0):
        """Make an HTTP request and return the response body as a string."""

        if redirect_count > URL.MAX_REDIRECTS:
            raise Exception(f"Too many redirects (limit: {URL.MAX_REDIRECTS})")

        s = self.get_socket()

        request = "GET {} HTTP/1.1\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: keep-alive\r\n"
        request += "User-Agent: user\r\n"
        request += "\r\n"
        s.send(request.encode("utf8")) # important to send raw bits and bytes

        # read server response in binary mode
        response = s.makefile("rb", newline=None)

        # read status line
        status_line = response.readline().decode("utf8")
        version, status, explanation = status_line.split(" ", 2)
        
        status_code = int(status)

        # read headers
        response_headers = {}
        while True:
            line = response.readline().decode("utf8")
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # check for unsupported headers
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        if 300 <= status_code < 400:
            # handle redirects
            if "location" not in response_headers:
                raise Exception(f"Redirect status {status_code} but no Location header")
            
            content_length = response_headers.get("content-length")
            if content_length:
                # read and discard body
                response.read(int(content_length))
            
            location = response_headers["location"]

            redirect_url_str = self.resolve_redirect_location(location)
            redirect_url = URL(redirect_url_str)

            return redirect_url.request(redirect_count + 1)

        # read content based on content-length
        content_length = response_headers.get("content-length")
        if content_length:
            body_bytes = response.read(int(content_length))
        else:
            # fallback, read all
            body_bytes = response.read()
            # if no content-length, we can reuse connection
            cache_key = (self.scheme, self.host, self.port)

            if cache_key in URL.socket_cache:
                try:
                    URL.socket_cache[cache_key].close()
                except Exception:
                    pass
                del URL.socket_cache[cache_key]
        
        # decode body to string and dont close the socket, its cached for later use
        body = body_bytes.decode("utf8", errors="replace")
        return body

    def show(self, body):
        """Display the body content as plain text."""

        # to create a very simple web browser, take the page html and print all the text, but not the tags
        # it goes through the request body char by char and checks if its between a pair of <>
        # when its not in a tag it prints the text between the tags
        
        output = ""
        in_tag = False
        for c in body:
            if c == "<":
                in_tag = True
            elif c == ">":
                in_tag = False
            elif not in_tag:
                output += c

        output = output.replace("&lt;", "<").replace("&gt;", ">")

        print(output, end="")

    def load(self):
        """Load the URL and display its content."""

        # now we can load a URL and show the data
        # also a function to open and read files

        # Handle data URLs
        if getattr(self, "is_data", False):
            body = self.decode_data_url(self.data_meta, self.data_payload)
            self.show(body)
            return
    
        # Handle file URLs
        if self.is_file:
            with open(self.file_path, "r", encoding="utf8") as f:
                body = f.read()
            if self.is_view_source:
                print(body)  # print raw html
            else:
                self.show(body)  # print text
            return
        
        # Handle HTTP/HTTPS URLs
        body = self.request()
        if self.is_view_source:
            print(body)  # print raw html
        else:
            self.show(body)  # print text
    
    @classmethod
    def close_all_sockets(cls):
        """Close all cached sockets."""
        for s in cls.socket_cache.values():
            try:
                s.close()
            except Exception:
                pass
        cls.socket_cache.clear()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        url.load()

    # Optional: test with multiple requests to same server
    # Uncomment to test keep-alive
    print("\n\n=== Second request (should reuse socket) ===\n")
    url2 = URL("https://example.org/")
    url2.load()

    URL.close_all_sockets()


