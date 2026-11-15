import threading
import time
from argparse import ArgumentTypeError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy
import pytest
from unittest.mock import Mock
from marimapper.camera import Camera, is_network_stream, parse_device
from utils import get_test_dir


def test_valid_device():

    cam = Camera(
        get_test_dir("MariMapper-Test-Data/9_point_box/cam_0/capture_%04d.png")
    )

    image = cam.read()

    assert image.shape[0] == 480
    assert image.shape[1] == 640
    assert image.shape[2] >= 3


def test_invalid_device():

    with pytest.raises(RuntimeError):
        Camera(device_id="bananas")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0", 0),
        ("1", 1),
        (" 2 ", 2),
        ("http://192.168.1.20:8080/mjpegfeed", "http://192.168.1.20:8080/mjpegfeed"),
        (" http://phone.local:4747/video ", "http://phone.local:4747/video"),
        ("http://[fe80::1]:4747/video", "http://[fe80::1]:4747/video"),
        ("rtsp://camera.local/stream", "rtsp://camera.local/stream"),
        ("RTMP://camera.local/live", "RTMP://camera.local/live"),
    ],
)
def test_parse_device(text, expected):
    assert parse_device(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "-1", "192.168.1.20:4747", "http://", "ftp://camera.local/x", "not a device"],
)
def test_parse_device_rejects_garbage(text):
    with pytest.raises(ArgumentTypeError):
        parse_device(text)


def test_is_network_stream():
    assert is_network_stream("http://192.168.1.20:4747/video")
    assert is_network_stream("RTSP://camera.local/stream")
    assert not is_network_stream(0)
    assert not is_network_stream("capture_%04d.png")


class _FakeStream(BaseHTTPRequestHandler):
    """Serves an MJPEG stream on /video, the way many IP cameras and phone apps do."""

    jpeg = b""

    def do_GET(self):
        if self.path != "/video":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        header = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
        try:
            while True:
                self.wfile.write(header % len(self.jpeg) + self.jpeg + b"\r\n")
                time.sleep(0.02)
        except OSError:
            pass  # the camera disconnected

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_stream():
    picture = numpy.zeros((480, 640, 3), dtype=numpy.uint8)
    picture[200:280, 300:380] = 255  # a bright square, like a lit LED
    _FakeStream.jpeg = cv2.imencode(".jpg", picture)[1].tobytes()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeStream)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_network_device(fake_stream):

    cam = Camera(parse_device(f"http://127.0.0.1:{fake_stream}/video"))

    image = cam.read()

    assert image.shape[0] == 480
    assert image.shape[1] == 640
    assert image.shape[2] >= 3
    assert image[240, 340].min() > 200  # the bright square made it through
    assert image[10, 10].max() < 50  # and so did the dark background


def test_unreachable_network_device():

    with pytest.raises(RuntimeError):
        Camera(parse_device("http://127.0.0.1:1/video"))  # nothing listens on port 1


@pytest.fixture
def webcam(monkeypatch):
    device = Mock()
    device.isOpened.return_value = True
    device.get.return_value = 0
    device.set.return_value = True
    device.read.return_value = (True, numpy.zeros((1080, 1920, 3), numpy.uint8))
    monkeypatch.setattr(cv2, "VideoCapture", lambda *args: device)
    return device


def test_requested_resolution_checks_actual_frame(webcam):
    cam = Camera(1, resolution=(1920, 1080), fourcc="MJPG")
    assert cam.read().shape == (1080, 1920, 3)
    assert webcam.set.call_args_list == [
        ((cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),),
        ((cv2.CAP_PROP_FRAME_WIDTH, 1920),),
        ((cv2.CAP_PROP_FRAME_HEIGHT, 1080),),
    ]


def test_resolution_fallback_is_rejected_and_camera_released(webcam):
    with pytest.raises(RuntimeError, match="3840x2160.*1920x1080"):
        Camera(1, resolution=(3840, 2160))
    webcam.release.assert_called_once()


def test_capture_format_rejection_releases_camera(webcam):
    webcam.set.return_value = False
    with pytest.raises(RuntimeError, match="capture format"):
        Camera(1, fourcc="MJPG")
    webcam.release.assert_called_once()


def test_requested_resolution_requires_readable_frame(webcam):
    webcam.read.return_value = (False, None)
    with pytest.raises(Exception, match="Failed to read image"):
        Camera(1, resolution=(1920, 1080))
    webcam.release.assert_called_once()


@pytest.mark.parametrize("resolution", [(0, 1080), (1920, -1), (1920,)])
def test_invalid_resolution(resolution):
    with pytest.raises(ValueError, match="resolution"):
        Camera(1, resolution=resolution)


def test_network_stream_resolution_must_be_set_at_source():
    with pytest.raises(ValueError, match="local webcam"):
        Camera("http://camera.local/video", resolution=(1920, 1080))


def test_camera_cli_resolution_options():
    import argparse
    from marimapper.scripts.arg_tools import add_camera_args

    parser = argparse.ArgumentParser()
    add_camera_args(parser)
    args = parser.parse_args(["--resolution", "3840", "2160", "--fourcc", "MJPG"])
    assert args.resolution == [3840, 2160]
    assert args.fourcc == "MJPG"
    for options in [["--resolution", "0", "1080"], ["--fourcc", "MJPEG"]]:
        with pytest.raises(SystemExit):
            parser.parse_args(options)


def test_detector_releases_camera_after_scan_error(monkeypatch):
    from functools import partial
    from marimapper.detector_process import DetectorProcess

    camera = Mock()
    constructor = Mock(return_value=camera)
    monkeypatch.setattr("marimapper.detector_process.Camera", constructor)
    detector = DetectorProcess(
        device=1,
        dark_exposure=-2,
        threshold=80,
        backend_factory=partial(Mock),
        resolution=(3840, 2160),
        fourcc="MJPG",
    )
    monkeypatch.setattr(
        detector, "_detect_with_camera", Mock(side_effect=RuntimeError("scan failed"))
    )
    with pytest.raises(RuntimeError, match="scan failed"):
        detector._detect(Mock())
    constructor.assert_called_once_with(1, (3840, 2160), "MJPG")
    camera.reset.assert_called_once()
    camera.device.release.assert_called_once()
