"""Real HTTP API test engine using only Python's standard library.

Run `python api_test_engine.py` inside WSL. The suite starts Django's live HTTP
server against an isolated test DB and temporary media directory; it does not
write to the development or deployed database and never prints credentials.
"""
import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: dict
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def multipart_body(fields, files):
    """Build binary-safe multipart/form-data with CRLF framing."""
    boundary = "photoblog-" + uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    for name, (filename, content_type, content) in files.items():
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(), content, b"\r\n",
        ])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class PhotoBlogHTTPClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.token = None

    def request(self, method, path, data=None, content_type=None, authenticated=True):
        headers = {"Accept": "application/json"}
        if self.token and authenticated:
            headers["Authorization"] = f"Token {self.token}"
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return HTTPResult(response.status, dict(response.headers.items()), response.read())

    def authenticate(self, username, password):
        data = json.dumps({"username": username, "password": password}).encode()
        result = self.request("POST", "/api-token-auth/", data, "application/json", authenticated=False)
        if result.status == 200:
            self.token = result.json()["token"]
        return result

    def post_photo(self, title, text, image_bytes, filename="photo.png", content_type="image/png"):
        body, multipart_type = multipart_body(
            {"title": title, "text": text}, {"image": (filename, content_type, image_bytes)}
        )
        return self.request("POST", "/api_root/Post/", body, multipart_type)


if __name__ == "__main__":
    import os
    import sys
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line([
        sys.argv[0], "test", "blog.tests.test_http_engine", "blog.tests.test_single_owner_http",
        "blog.tests.test_content_http",
        "--verbosity", "2",
    ])
