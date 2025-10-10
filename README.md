# Simple Web Browser

A simple web browser implementation in Python that supports:

- HTTP/HTTPS requests
- File URLs
- Data URLs
- View source mode

## Usage

```bash python3 browser.py <url>```

## Examples

Load a webpage
```bash python3 browser.py https://example.org/```

View source
```bash python3 browser.py view-source:https://example.org/```

Open local file
```bash python3 browser.py file:///path/to/file.html```

Data URL
```bash python3 browser.py "data:text/html,<h1>Hello World</h1>"```

## Testing
Run unit tests:

```bash python3 test_browser.py -v```

