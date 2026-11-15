import pytest
import cv2
import numpy as np

from marimapper.detector import find_led_in_image, draw_led_detections
from marimapper.camera import Camera
from utils import get_test_dir


def test_basic_image_loading():

    mock_camera = Camera(
        get_test_dir("MariMapper-Test-Data/9_point_box/cam_0/capture_0000.png")
    )

    detection = find_led_in_image(mock_camera.read())
    assert detection.u() == pytest.approx(0.40294844632768356)
    assert detection.v() == pytest.approx(0.40294844632768356)


def test_none_found():

    mock_camera = Camera(
        get_test_dir("MariMapper-Test-Data/9_point_box/cam_0/capture_%04d.png")
    )

    for frame_id in range(24):
        frame = mock_camera.read()
        if frame_id in [7, 15, 23]:
            led_detection = find_led_in_image(frame)
            assert led_detection is None


def test_draw_results():

    mock_camera = Camera(
        get_test_dir("MariMapper-Test-Data/9_point_box/cam_0/capture_%04d.png")
    )
    frame = mock_camera.read()
    led_detection = find_led_in_image(frame)
    draw_led_detections(frame, led_detection)


@pytest.mark.parametrize("width,height", [(640, 480), (1920, 1080), (3840, 2160)])
def test_detection_coordinates_preserve_geometry_at_capture_resolution(width, height):
    # Both axes use image width, with vertical padding to a square. Changing
    # capture size must not stretch a widescreen map or change this convention.
    image = np.zeros((height, width, 3), dtype=np.uint8)
    center = (width // 3, height // 4)
    cv2.circle(image, center, 8, (255, 255, 255), -1)
    point = find_led_in_image(image)
    assert point.u() == pytest.approx(center[0] / width)
    assert point.v() == pytest.approx((center[1] + (width - height) / 2) / width)

    rendered = draw_led_detections(image, point)
    # The preview marker must land on the same sensor pixel as the detection.
    assert tuple(rendered[center[1], center[0]]) == (0, 255, 0)
