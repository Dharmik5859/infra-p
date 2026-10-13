"""
A multipart/form-data upload streamed straight to disk.

FastAPI's UploadFile only reaches the endpoint after the whole body has been
parsed into a temporary file, so a size limit or a wrong file type would only
be noticed after gigabytes had arrived, and the file would then be copied
once more. Here the body is parsed as it is received: the wanted part's bytes
go directly into the job's upload file, the request is refused as soon as it
passes MAX_UPLOAD_MB or plainly is not a PDF, and other form fields are
skipped without being kept.
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

from . import settings
from .jobs import PDF_MAGIC, UploadWriter, too_large

# what a form adds around the file: boundaries, part headers, small fields
FORM_OVERHEAD = 1 << 20


class _Part:
    """python-multipart callbacks: they only record (headers, the wanted
    part's bytes); the caller writes between reads, where errors can be
    raised cleanly."""

    def __init__(self, field: str) -> None:
        self.field = field.encode()
        self.header = [b"", b""]
        self.disposition = b""
        self.wanted = False         # is the part being read the file
        self.parts = 0              # parts named `field` seen
        self.filename = ""
        self.pending: list[bytes] = []
        self.ended = False          # the closing boundary arrived

    def callbacks(self) -> dict:
        return {"on_part_begin": self.begin, "on_header_field": self.header_field,
                "on_header_value": self.header_value, "on_header_end": self.header_end,
                "on_headers_finished": self.headers_finished, "on_part_data": self.data,
                "on_part_end": self.part_end, "on_end": self.end}

    def begin(self) -> None:
        self.disposition = b""

    def header_field(self, data: bytes, start: int, end: int) -> None:
        self.header[0] += data[start:end]

    def header_value(self, data: bytes, start: int, end: int) -> None:
        self.header[1] += data[start:end]

    def header_end(self) -> None:
        if self.header[0].lower() == b"content-disposition":
            self.disposition = self.header[1]
        self.header = [b"", b""]

    def headers_finished(self) -> None:
        _, options = parse_options_header(self.disposition)
        self.wanted = options.get(b"name") == self.field
        if self.wanted:
            self.parts += 1
            self.filename = options.get(b"filename", b"").decode("utf-8", "replace")

    def data(self, data: bytes, start: int, end: int) -> None:
        if self.wanted:
            self.pending.append(data[start:end])

    def part_end(self) -> None:
        self.wanted = False

    def end(self) -> None:
        self.ended = True


async def receive_pdf(request: Request, field: str = "file") -> tuple[str, str]:
    """Stream the PDF in form field `field` to its own temporary folder.
    Returns (file name as sent, path); raises 400 (no such field, empty, not a
    PDF, malformed form) or 413 (past MAX_UPLOAD_MB)."""
    ctype, params = parse_options_header(request.headers.get("content-type"))
    if ctype != b"multipart/form-data" or not params.get(b"boundary"):
        raise HTTPException(400, f'Send the plan set as multipart/form-data, in the form field "{field}".')
    limit = (settings.MAX_UPLOAD_MB << 20) + FORM_OVERHEAD
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        # refused before reading a byte: a client that sent "Expect: 100-continue"
        # (curl does for big files) never uploads it at all
        raise too_large()

    part = _Part(field)
    parser = MultipartParser(params[b"boundary"], part.callbacks())
    received = 0
    with UploadWriter() as out:
        try:
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    raise too_large()
                parser.write(chunk)
                if part.parts > 1:
                    raise HTTPException(400, "Send one plan set per request.")
                for data in part.pending:
                    out.write(data)
                part.pending.clear()
                if not out.looks_like_pdf():
                    raise HTTPException(400, "That file is not a PDF.")
        except MultipartParseError as e:
            raise HTTPException(400, f"Malformed multipart form: {e}") from None
        if not part.parts:
            raise HTTPException(400, f'No file in the form field "{field}".')
        if not part.ended:
            raise HTTPException(400, "The upload ended before the form was complete.")
        if out.size == 0:
            raise HTTPException(400, "The uploaded file is empty.")
        if out.head != PDF_MAGIC:
            raise HTTPException(400, "That file is not a PDF.")
    name = part.filename.replace("\\", "/").rsplit("/", 1)[-1] or "plan-set.pdf"
    return name, out.path
