"""Install the pinned high-accuracy Korean and English Tesseract models."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
COMMIT = "e12c65a915945e4c28e237a9b52bc4a8f39a0cec"
MODELS = {
    "kor.traineddata": "f888d4038348a0c3d25151e7f452bda0d74ca275b18cab146798bcbb94084fff",
    "eng.traineddata": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def install() -> None:
    target_dir = ROOT / "tools" / "tessdata"
    scratch = ROOT / "_work"
    target_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    for name, expected in MODELS.items():
        target = target_dir / name
        if target.is_file() and sha256(target) == expected:
            print(f"{name}: pinned model already installed")
            continue
        url = f"https://github.com/tesseract-ocr/tessdata_best/raw/{COMMIT}/{name}"
        temp_path = None
        try:
            request = Request(url, headers={"User-Agent": "DOCULENS-model-setup/1.0"})
            with urlopen(request, timeout=60) as response, tempfile.NamedTemporaryFile(
                dir=scratch, prefix=f"{name}.", suffix=".download", delete=False
            ) as temp:
                temp_path = Path(temp.name)
                while block := response.read(1024 * 1024):
                    temp.write(block)
            actual = sha256(temp_path)
            if actual != expected:
                raise RuntimeError(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")
            os.replace(temp_path, target)
            temp_path = None
            print(f"{name}: installed and verified")
        except (OSError, URLError, TimeoutError, RuntimeError) as exc:
            raise RuntimeError(f"정밀 OCR 모델 {name} 설치 실패 ({url}): {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        install()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
