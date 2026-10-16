"""Optional real Facenet runtime check using synthetic pixels, never a person.

This downloads model weights on first run. It verifies the actual FaceManager
backend import and inference, not biometric accuracy or a physical camera.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DEEPFACE_HOME", str(PROJECT_ROOT / ".models"))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def main():
    import numpy as np
    from face_manager import FaceManager

    manager = FaceManager(faces_dir=str(PROJECT_ROOT / "faces"))
    embedding = manager._represent(np.zeros((160, 160, 3), dtype=np.uint8))
    if embedding.shape != (128,) or not np.isfinite(embedding).all():
        raise RuntimeError("Facenet geçerli 128 boyutlu embedding döndürmedi.")
    print("Facenet gerçek model kontrolü geçti: 128 sonlu değer; sentetik görüntü.")


if __name__ == "__main__":
    main()
