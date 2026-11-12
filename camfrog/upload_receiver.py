#!/usr/bin/env python3
"""Tiny one-shot upload receiver so the Windows guest can hand files to the host."""
import os
import http.server
import socketserver

OUT = "/tmp/guest-upload"
PORT = 8099
os.makedirs(OUT, exist_ok=True)

PAGE = b"""<!doctype html><html><body style="font-family:sans-serif">
<h2>Upload capture</h2>
<form method="POST" action="/upload" enctype="multipart/form-data">
<input type="file" name="file"><button type="submit">Upload</button>
</form></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def _save(self, name, data):
        name = os.path.basename(name) or "upload.bin"
        path = os.path.join(OUT, name)
        with open(path, "wb") as f:
            f.write(data)
        self.log_message("saved %s (%d bytes)", path, len(data))
        return path

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n) if n else b""
        p = self._save(self.path.strip("/") or "upload.bin", data)
        body = f"saved {p} {len(data)} bytes\n".encode()
        self.send_response(201)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        ctype = self.headers.get("Content-Type", "")
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        name, data = "upload.bin", raw
        if ctype.startswith("multipart/form-data") and "boundary=" in ctype:
            b = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
            for part in raw.split(b"--" + b):
                if b"filename=" not in part:
                    continue
                head, _, body = part.partition(b"\r\n\r\n")
                fn = head.split(b"filename=")[1].split(b";")[0].strip().strip(b'"')
                name = fn.decode("utf-8", "replace") or "upload.bin"
                data = body.rstrip(b"\r\n")
                break
        p = self._save(name, data)
        body = f"saved {p} {len(data)} bytes\n".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *a):
        with open("/tmp/guest-upload/server.log", "a") as f:
            f.write("%s %s\n" % (self.address_string(), fmt % a))


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with S(("0.0.0.0", PORT), H) as httpd:
        print(f"listening on 0.0.0.0:{PORT}, saving to {OUT}", flush=True)
        httpd.serve_forever()
