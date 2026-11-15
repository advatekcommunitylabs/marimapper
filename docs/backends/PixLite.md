# Advatek PixLite Mk3

Use a PixLite Mk3 controller that supports API v1.9. Configure the pixel
outputs in Advatek Assistant first. MariMapper subtracts leading null pixels
and counts each group as one logical LED, including any partial group at the
end of a string. LED 0 starts on the first output with logical LEDs. The count
continues in port order, skipping empty and all-null outputs.

At startup it reads every port from the controller. An A4 has 4 outputs in
normal mode or 8 in expanded mode. An E16 has 16 or 32. It checks the selected
pixel type against the controller's supported color types, input format and
expanded-mode capability.

RGB, RGBW and RGBWX use 3, 4 and 5 input channels per logical pixel at 8-bit
resolution, or 6, 8 and 10 at 16-bit resolution. This channel footprint does
not change the number of scan points. Test colors are sent as 8-bit values,
independently of the configured live input format.

The backend sends logical pixel numbers to test mode. The controller applies
null pixels, grouping, zigzag and reverse mapping itself, as described in
section 7.1 of the PixLite Mk3 Management Guide V20260618. Physical verification
for outputs with null pixels and grouping is pending.

Run these commands with your controller's address:

```sh
marimapper_check_backend pixlite --server <controller-address>
marimapper pixlite --server <controller-address>
```

For this draft, install the contribution branch using Python 3.12:

```sh
python -m pip install "git+https://github.com/advatekcommunitylabs/marimapper.git@codex/pixlite-mk3"
```

Run the backend checker separately for the A4 and E16. It prints the detected
port layout and blinks logical LED 0. Use `--reference_led <index>` to check
another logical LED, then Ctrl+C to return to live mode. Add `--verbose` to
the scan command to see its port layout too.

If illuminated pixels are too dim for the camera, increase `--brightness`
from its default of 64, up to 255. This sets the test RGB level while leaving
the controller's saved intensity settings in place.

For a high-resolution local webcam, request the capture size explicitly. For
example, with 41 connected logical LEDs on the first output:

```sh
marimapper_check_camera --device 1 --resolution 3840 2160 --fourcc MJPG --exposure -2 --threshold 80
marimapper pixlite --server <controller-address> --device 1 --resolution 3840 2160 --fourcc MJPG --exposure -2 --threshold 80 --brightness 255 --start 0 --end 40
```

The UGREEN CM930 was checked delivering actual 3840x2160 frames with MJPG.
Other cameras may need a different size or format. MariMapper checks a real
frame and stops if the requested resolution is not delivered. Omitting these
options keeps the camera's default capture format and size. Network stream
resolution must be configured at its source.

Test one port at a time. Set `--start` and `--end` to that port's logical index
range, using the counts reported at startup with `--verbose`. The example
above scans indices 0 through 40 only. It does not change the controller's
configured string length or select later ports. MariMapper cannot determine
how many pixels are physically connected from the configured count.

Higher resolution does not by itself establish spatial accuracy. Keep the
camera and string still, with every LED emitter directly visible. Check the
first, middle and last LEDs before a full scan. Reflections on a wall or desk
can be detected as valid points even when the actual emitter is obscured.
Use the lowest brightness and exposure that reliably detect every LED, then
repeat the scan to check coordinate stability. MariMapper pads the vertical
axis to a square and normalizes both coordinates by image width; these are
camera-space positions, not calibrated physical measurements.

The backend uses the controller's administrator account for test-data mode.
For a password-protected account, set the `PIXLITE_PASSWORD` environment
variable and pass the full HTTPS URL (PixLite uses port 4443). The controller
certificate must be trusted.
Requests can use a CA bundle specified by `REQUESTS_CA_BUNDLE`.

Start with the controller in live mode. Scanning temporarily replaces live
output with the controller's test pattern and lights one pixel at a time.
Use this on a dedicated controller during the scan. The backend returns the
controller to live mode on exit. If the connection drops during cleanup or
the process is forcibly stopped, restore live mode in Advatek Assistant.
