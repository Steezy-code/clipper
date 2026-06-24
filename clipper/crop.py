"""Stage 3 - the camera operator. Track the speaker and crop to 9:16 smoothly.

The trick that separates this from a jittery mess is *smoothing*: we detect the
face position over time, then run a forward+backward exponential average so the
virtual camera glides instead of snapping on every head twitch.
"""
from __future__ import annotations
import subprocess
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from .config import Config
from .ffmpeg_util import even

# YuNet is the higher-quality detector but ships via Git LFS, so we download the real
# binary from the media endpoint. If that fails for any reason we fall back to the Haar
# cascade bundled inside opencv-python - no download, always available.
_YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_YUNET_PATH = Path(__file__).parent / "models" / "face_detection_yunet.onnx"
_DETECT_W = 640  # downscale frames to this width for face detection (speed)


def _try_yunet(w: int, h: int):
    """Return a YuNet detector, or None if the model can't be fetched/loaded."""
    try:
        if not _YUNET_PATH.exists() or _YUNET_PATH.stat().st_size < 10000:
            _YUNET_PATH.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(_YUNET_URL, _YUNET_PATH)
        return cv2.FaceDetectorYN.create(str(_YUNET_PATH), "", (w, h), score_threshold=0.6)
    except Exception:
        return None


def _haar():
    """opencv's built-in frontal-face cascade. Bundled with the pip package."""
    return cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _make_detector(w: int, h: int):
    """(detector, kind) where kind is 'yunet' or 'haar'."""
    yn = _try_yunet(w, h)
    if yn is not None:
        return yn, "yunet"
    return _haar(), "haar"


def _largest_center(detector, kind, frame):
    """Return (cx, cy) of the biggest detected face, or None."""
    if kind == "yunet":
        _, faces = detector.detect(frame)
        if faces is None or not len(faces):
            return None
        f = max(faces, key=lambda f: f[2] * f[3])
        return f[0] + f[2] / 2.0, f[1] + f[3] / 2.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return x + fw / 2.0, y + fh / 2.0


def _crop_plan(w: int, h: int, cfg: Config) -> tuple[int, int, str]:
    """Return (crop_w, crop_h, axis) for the largest 9:16 window that fits."""
    target = cfg.target_w / cfg.target_h
    if w / h > target:           # source is wider -> crop width, slide on x
        crop_h = h
        crop_w = even(h * target)
        return min(crop_w, w), crop_h, "x"
    crop_w = w                   # source is taller -> crop height, slide on y
    crop_h = even(w / target)
    return crop_w, min(crop_h, h), "y"


def _smooth(track: np.ndarray, alpha: float) -> np.ndarray:
    """Two-pass EMA (forward then backward), averaged, to glide without lag."""
    fwd = track.copy()
    for i in range(1, len(fwd)):
        fwd[i] = alpha * track[i] + (1 - alpha) * fwd[i - 1]
    bwd = track.copy()
    for i in range(len(bwd) - 2, -1, -1):
        bwd[i] = alpha * track[i] + (1 - alpha) * bwd[i + 1]
    return (fwd + bwd) / 2.0


def _track_centers(cap, n_frames, w, h, axis, crop_w, crop_h, cfg) -> np.ndarray:
    # ponytail: detect on a ~640px-wide frame, not full res - face detection is the
    # per-frame cost and downscaling cuts it several-fold with no visible accuracy loss.
    scale = min(1.0, _DETECT_W / w)
    dw, dh = max(1, round(w * scale)), max(1, round(h * scale))
    detector, kind = _make_detector(dw, dh)
    full = w if axis == "x" else h
    crop = crop_w if axis == "x" else crop_h
    lo, hi = crop / 2.0, full - crop / 2.0
    default = full / 2.0

    raw = np.full(n_frames, np.nan)
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % cfg.detect_every == 0:
            small = cv2.resize(frame, (dw, dh)) if scale < 1.0 else frame
            center = _largest_center(detector, kind, small)
            if center is not None:
                cx, cy = center[0] / scale, center[1] / scale
                raw[idx] = np.clip(cx if axis == "x" else cy, lo, hi)
        idx += 1

    # forward-fill detections, fall back to centre, then smooth
    last = default
    for i in range(n_frames):
        if np.isnan(raw[i]):
            raw[i] = last
        else:
            last = raw[i]
    return np.clip(_smooth(raw, cfg.smooth_alpha), lo, hi)


def _zoom_track(n_frames: int, fps: float, triggers, cfg: Config) -> np.ndarray:
    """Per-frame zoom factor (1.0 = none, up to 1+zoom_amount). Each trigger makes a
    trapezoid bump (ease in, hold, ease out); triggers within zoom_gap are skipped."""
    z = np.ones(n_frames)
    if not triggers or cfg.zoom_amount <= 0:
        return z
    rise, hold, fall = max(1, int(0.25 * fps)), max(1, int(0.2 * fps)), max(1, int(0.4 * fps))
    last = -1e9
    for t in triggers:
        if t - last < cfg.zoom_gap:
            continue
        last = t
        c = int(round(t * fps))
        for k in range(-rise, hold + fall):
            i = c + k
            if i < 0 or i >= n_frames:
                continue
            if k < 0:
                f = (k + rise) / rise          # ease in
            elif k < hold:
                f = 1.0                         # hold
            else:
                f = max(0.0, 1 - (k - hold) / fall)  # ease out
            z[i] = max(z[i], 1.0 + cfg.zoom_amount * f)
    return z


def reframe(clip_path: str, dst: str, cfg: Config, ass_path: str | None = None,
            zoom_at: list[float] | None = None) -> str:
    """Crop clip_path to vertical, following the speaker, audio preserved.

    If ass_path is given, the captions are burned in this same encode pass instead of
    a separate ffmpeg round trip - one decode+encode per clip instead of two.
    zoom_at is a list of timestamps (seconds) to punch-in on.
    """
    cap = cv2.VideoCapture(clip_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    crop_w, crop_h, axis = _crop_plan(w, h, cfg)
    centers = _track_centers(cap, n_frames, w, h, axis, crop_w, crop_h, cfg)
    zoom = _zoom_track(n_frames, fps, zoom_at if cfg.punch_zoom else None, cfg)

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y",
           "-f", "rawvideo", "-pixel_format", "bgr24",
           "-video_size", f"{cfg.target_w}x{cfg.target_h}", "-framerate", f"{fps:.4f}",
           "-i", "-", "-i", clip_path,
           "-map", "0:v:0", "-map", "1:a:0?"]
    if ass_path:
        esc = ass_path.replace("\\", "/").replace(":", "\\:")
        cmd += ["-vf", f"ass='{esc}'"]
    cmd += ["-c:v", cfg.video_codec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", dst]
    ff = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        c = centers[i] if i < len(centers) else centers[-1]
        zf = zoom[i] if i < len(zoom) else 1.0
        zw = max(2, min(w, int(round(crop_w / zf))))   # zoom in = take a smaller window
        zh = max(2, min(h, int(round(crop_h / zf))))
        if axis == "x":
            x0 = int(round(c - zw / 2.0)); y0 = (h - zh) // 2
        else:
            y0 = int(round(c - zh / 2.0)); x0 = (w - zw) // 2
        x0 = max(0, min(x0, w - zw)); y0 = max(0, min(y0, h - zh))
        window = frame[y0:y0 + zh, x0:x0 + zw]
        out = cv2.resize(window, (cfg.target_w, cfg.target_h), interpolation=cv2.INTER_AREA)
        ff.stdin.write(out.tobytes())

    cap.release()
    ff.stdin.close()
    ff.wait()
    return dst
