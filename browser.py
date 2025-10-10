import socket
import ssl
import base64
import urllib.parse
import os

class URL:
    def __init__(self, url):
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

    def request(self):
        # establish a socket
        # address family is INET, tells how to find the other computer
        # type describes the convo between the 2 computers
        # protocol describes the steps which the 2 computers establish a connection
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

        # now theres a connection, now we just gotta send data using the send method
        # very important to use \r\n for new lines
        # important to put two \r\n newlines at the end so that you send that blank line at the end
        # if you forget, the other computer will keep waiting until you send that newline
        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: close\r\n"
        request += "User-Agent: user\r\n"
        request += "\r\n"
        s.send(request.encode("utf8")) # important to send raw bits and bytes

        # read server response using makefile
        # returns a file-like object with every byte we recieve from the server
        # we turn those bytes into a string using utf8, and informing the weird line endings
        response = s.makefile("r", encoding="utf8", newline="\r\n")

        # split response into pieces, first line is the status
        # dont check the version of http if its the same as yours since some servers are misconfigured to 1.1
        # even when talking in 1.0
        status_line = response.readline()
        version, status, explanation = status_line.split(" ", 2)

        # after status, its the headers
        # split each line at the first colon
        # fill a map of header names to values
        # headers are case-insensitive, so normalize them to lowercase
        # and strip off any white-space 
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        # make sure these headers are not present
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        # the usual way to get the sent data is everything after the headers
        content = response.read()
        s.close()

        # its the body were going to display so return that
        return content

    def show(self, body):
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

if __name__ == "__main__":
    import sys
    url = URL(sys.argv[1])
    url.load()
    

