"""Health and measured accuracy: what the app's dashboard and upload page read first."""
from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, HTTPException

from gdot_earthwork import __version__

from . import settings

router = APIRouter()


@router.get("/api/health")
def health():
    deps = {"tesseract": shutil.which("tesseract") is not None}
    return {"ok": all(deps.values()), "version": __version__, "dependencies": deps,
            "max_upload_mb": settings.MAX_UPLOAD_MB}


@router.get("/api/accuracy")
def accuracy():
    """Measured accuracy per plan-set format (written by tools.accuracy_report)."""
    try:
        with open(settings.ACCURACY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise HTTPException(404, "No accuracy report has been generated.") from None
