"""artifact.py

Persistência simples de artifacts em JSON.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict


def _safe_slug(value: str) -> str:
    cleaned = "".join(ch for ch in value.lower() if ch.isalnum() or ch in ("-", "_"))
    return cleaned[:32] if cleaned else "item"


def save_analysis_artifact(payload: Dict, base_dir: str) -> str:
    os.makedirs(base_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    subject = payload.get("ticker") or payload.get("startup_name") or payload.get("mode", "analysis")
    slug = _safe_slug(str(subject))
    filename = f"analysis-{slug}-{timestamp}.json"
    path = os.path.join(base_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
