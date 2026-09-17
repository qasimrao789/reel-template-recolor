import argparse
import cv2
import subprocess
import os
import glob
import json
import math
import shutil
from fractions import Fraction

import numpy as np

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
)

import logo_positions


# ============================================================
# SETTINGS
# ============================================================

# Default input/output folders resolve relative to this script's
# own location, not the current working directory. Otherwise,
# running the script from a different folder (a different
# terminal cwd, a shortcut, etc.) silently points at different
# "input_videos"/"output_videos" folders each time, which looks
# exactly like lost progress/resume not working, when nothing was
# actually lost. --input/--output override these defaults
# entirely and are used exactly as given, relative or absolute.
SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

INPUT_FOLDER = os.path.join(
    SCRIPT_DIR,
    "input_videos"
)

OUTPUT_FOLDER = os.path.join(
    SCRIPT_DIR,
    "output_videos"
)

# Any #RRGGBB color works.
TARGET_COLOR = "#FFFFFF"

# None = automatic opposite of TARGET_COLOR.
# Or set an exact text color such as "#000000" or "#FFFFFF".
TEXT_COLOR = None

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

# Optional branding/logo overlay.
# LOGO_PATH = None disables the feature entirely.
LOGO_PATH = None

# Vertical gap in pixels between the bottom of the detected
# movie/picture frame and the top of the logo.
LOGO_GAP_PX = 40

# Logo width as a fraction of the detected frame's width.
# Height is auto-scaled to preserve the logo's aspect ratio.
# None = pick a mode-appropriate default at runtime:
# RAW_LOGO_SCALE_DEFAULT for a supplied --logo image,
# GENERATED_LOGO_SCALE_DEFAULT for a generated branding block.
LOGO_SCALE = None

RAW_LOGO_SCALE_DEFAULT = 1.0
GENERATED_LOGO_SCALE_DEFAULT = 0.75

# How the logo is positioned:
# "auto"   = compute_logo_geometry(): centered under the detected
#            frame, scaled by LOGO_SCALE (default).
# "manual" = a point clicked in the GUI's logo position picker,
#            loaded from LOGO_POSITIONS_FILE, at the logo's own
#            native size (no scaling). Whether that file holds
#            one shared point for every video ("fixed") or one
#            per video filename ("per_reel") lives in the file
#            itself (see logo_positions.py) - in per_reel mode a
#            video with no saved point is skipped, not
#            auto-placed.
LOGO_POSITION_MODE = "auto"

# Resolved to <OUTPUT_FOLDER>/logo_positions.json by default; see
# main().
LOGO_POSITIONS_FILE = None

# Loaded once per run by main() when LOGO_POSITION_MODE isn't
# "auto"; see logo_positions.load_positions().
LOGO_POSITIONS_DATA = None

# ------------------------------------------------------------
# Generated branding block (avatar + name + checkmark + handle).
# Alternative to a ready-made LOGO_PATH image; set via
# --avatar / --display-name / --username / --verified.
# Rendered once at this internal resolution, then scaled down
# to the detected frame width like any other logo. Sized so
# that, combined with GENERATED_LOGO_SCALE_DEFAULT, the result
# lands close to a normal social-media byline instead of being
# blown up to fill the whole frame width.
# ------------------------------------------------------------

AVATAR_PATH = None
DISPLAY_NAME = None
USERNAME = None
VERIFIED_BADGE = True

AVATAR_DIAMETER = 160
LOGO_PADDING = 18
AVATAR_TEXT_GAP = 24

NAME_FONT_SIZE = 60
USERNAME_FONT_SIZE = 44
TEXT_LINE_GAP = 8

CHECKMARK_GAP = 12
CHECKMARK_DIAMETER_RATIO = 0.75

USERNAME_BLEND_TOWARD_BACKGROUND = 0.55

BOLD_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
)

REGULAR_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)

CHECKMARK_BLUE = (
    29,
    155,
    240,
)

# 0.0 = analyze the literal first frame only.
# If some videos begin with a black/fade frame, use 0.5 instead.
REFERENCE_TIME_SECONDS = 0.0

# ------------------------------------------------------------
# Movie/picture region detection is primarily motion-based: a
# second frame is sampled this many seconds after the reference
# frame, and wherever pixels actually change between the two is
# treated as the embedded video. This is far more reliable than
# guessing from color/saturation, since it doesn't care whether
# the moving content happens to be plain, pale, or dark. If the
# video is too short for a second distinct sample, or nothing
# moves enough between the two frames, detection falls back to
# the single-frame color/saturation heuristic below.
# ------------------------------------------------------------

MOTION_SAMPLE_OFFSET_SECONDS = 1.5

# Per-pixel RGB channel difference required to count as "moved".
# Kept low-ish so subtler real motion (talking, blinking, slight
# camera movement) still registers, while staying safely above
# ordinary video-compression noise in a static region.
MOTION_DIFF_THRESHOLD = 20

# Fraction of pixels in a row that must have moved for that row
# to count toward the detected region's vertical extent. (The
# horizontal extent is found separately, via dark-border
# trimming rather than motion; see trim_dark_horizontal_borders.)
MOTION_ROW_THRESHOLD = 0.04

COLOR_PRESERVE_THRESHOLD = 22
COLOR_MIN_BRIGHTNESS = 55

# How consistently dark a row/column must be (fraction of its
# pixels under the darkness threshold) before it's trimmed as a
# border. Deliberately close to 1.0: a genuine pillarbox/letterbox
# is essentially 100% dark, while a real video's content can brush
# right up against the edge (e.g. a face profile) without filling
# the whole row/column. A looser fraction lets that thin bright
# intrusion get outvoted by the rest of the mostly-dark row/column
# and wrongly trimmed away as if it were part of the border.
BORDER_DARK_FRACTION = 0.99

# Pixels darker/lighter than these (max/min channel) are snapped
# to pure black/white before recoloring, so a slightly-off-black
# template background (shadow, compression, color cast) inverts
# cleanly instead of producing a visibly tinted patch. Matches
# COLOR_MIN_BRIGHTNESS so there's no gap in between: a pixel is
# either dark enough to snap to black, or bright enough to be a
# color-preservation candidate, never neither (which otherwise
# produced a washed-out, partially-inverted "ghost" color).
BLACK_SNAP_THRESHOLD = COLOR_MIN_BRIGHTNESS
WHITE_SNAP_THRESHOLD = 215

# Color/emoji preservation is disabled within this many pixels
# directly above/below the detected movie rectangle (left/right
# use the full remaining width instead - see build_static_template).
# A watermark baked into the source video can bleed a few pixels
# past the detected top/bottom edge; a real caption/footer emoji is
# normally much further away than this margin.
EDGE_BLEED_MARGIN_PX = 30

EMOJI_MASK_DILATE_PASSES = 2
EMOJI_MASK_ERODE_PASSES = 3

NVENC_PRESET = "p1"
NVENC_CQ = "18"

# CPU fallback settings used when NVIDIA NVENC is unavailable.
CPU_PRESET = "medium"
CPU_CRF = "18"

# Encoder selection mode:
# "auto" = prefer NVIDIA NVENC, then fall back to libx264
# "nvenc" = require NVIDIA h264_nvenc
# "cpu" = require libx264
ENCODER_MODE = "auto"

# Resolved encoder used for the current run.
VIDEO_ENCODER = None

SKIP_EXISTING_OUTPUTS = True

# Output filenames match the input filename exactly (e.g.
# "1.mp4" -> "1.mp4"), just in a different folder. This is also
# what SKIP_EXISTING_OUTPUTS/resume keys off of - re-running with
# different settings (encoder, logo, color) reuses the same output
# filename rather than producing a differently-suffixed one, so
# clear the output folder (or use a different one) to force a
# redo with new settings.
OUTPUT_EXTENSION = ".mp4"

# Fast scaling before template/video processing.
SCALE_FLAGS = "bilinear"

TEMPLATE_FOLDER = os.path.join(
    OUTPUT_FOLDER,
    "_static_templates"
)


# ============================================================
# COLOR HELPERS
# ============================================================

def hex_to_rgb(hex_color):

    value = (
        hex_color
        .strip()
        .lstrip("#")
    )

    if len(value) != 6:

        raise ValueError(
            'Color must be in #RRGGBB format, e.g. "#FFD400"'
        )

    try:

        return tuple(
            int(
                value[i:i + 2],
                16
            )
            for i in (
                0,
                2,
                4
            )
        )

    except ValueError as exc:

        raise ValueError(
            f"Invalid hexadecimal color: {hex_color}"
        ) from exc


def get_opposite_rgb(rgb):

    return tuple(
        255 - c
        for c in rgb
    )


def get_text_rgb(background_rgb):

    if TEXT_COLOR is None:

        return get_opposite_rgb(
            background_rgb
        )

    return hex_to_rgb(
        TEXT_COLOR
    )


# ============================================================
# BASIC HELPERS
# ============================================================

def find_segments(mask):

    segments = []

    start = None

    for i, value in enumerate(mask):

        if value and start is None:

            start = i

        elif not value and start is not None:

            segments.append(
                (
                    start,
                    i - 1
                )
            )

            start = None

    if start is not None:

        segments.append(
            (
                start,
                len(mask) - 1
            )
        )

    return segments


def trim_dark_horizontal_borders(
    gray,
    top_y,
    bottom_y,
    width,
    gray_b=None
):

    # Assumes the embedded video spans the full width within its
    # row band, and only pulls inward where there is a genuine
    # solid dark pillarbox border on either side. Used by both
    # detectors so a plain/pale part of the actual video is never
    # excluded just for not being "content" or not showing motion
    # within a short sample window.
    #
    # When a second frame (gray_b) is available, a column only
    # counts as a border if it's dark in BOTH frames. A genuine
    # pillarbox stays black the whole video; real video content
    # that's merely dark at one sampled instant (a shadow, dark
    # hair/clothing momentarily at the edge) almost certainly
    # isn't dark at the other sampled instant too, so requiring
    # both avoids wrongly trimming it.

    def is_dark_column(gray_frame, xx):

        return (

            gray_frame[
                top_y:
                bottom_y + 1,
                xx
            ]
            <
            35

        ).mean() > BORDER_DARK_FRACTION


    def is_border_column(xx):

        if not is_dark_column(gray, xx):

            return False


        if gray_b is not None:

            return is_dark_column(
                gray_b,
                xx
            )


        return True


    left_x = 0

    while (

        left_x < width

        and

        is_border_column(
            left_x
        )
    ):

        left_x += 1


    right_x = width - 1

    while (

        right_x > left_x

        and

        is_border_column(
            right_x
        )
    ):

        right_x -= 1


    return (
        left_x,
        right_x
    )


def nvenc_is_usable():

    # h264_nvenc can be listed by "ffmpeg -encoders" while still
    # failing at runtime, e.g. when no working NVIDIA driver/CUDA
    # runtime is actually loadable (missing/broken nvcuda.dll).
    # A tiny real test encode is the only reliable way to know.

    test_cmd = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "error",

        "-f",
        "lavfi",

        "-i",
        "color=c=black:s=64x64:d=0.1",

        "-frames:v",
        "1",

        "-c:v",
        "h264_nvenc",

        "-f",
        "null",

        "-",
    ]


    try:

        result = subprocess.run(
            test_cmd,
            capture_output=True,
            text=True,
        )

    except Exception:

        return False


    return (
        result.returncode == 0
    )


def check_tools(
    encoder_mode="auto"
):

    for tool in (
        "ffmpeg",
        "ffprobe"
    ):

        if shutil.which(tool) is None:

            raise RuntimeError(
                f"{tool} was not found in PATH"
            )


    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-encoders"
        ],
        capture_output=True,
        text=True,
        check=True,
    )


    encoders = result.stdout

    has_nvenc = (
        "h264_nvenc" in encoders
    )

    has_libx264 = (
        "libx264" in encoders
    )


    if encoder_mode == "nvenc":

        if not has_nvenc:

            raise RuntimeError(
                "NVENC was requested, but h264_nvenc is not available "
                "in this FFmpeg build."
            )


        if not nvenc_is_usable():

            raise RuntimeError(
                "NVENC was requested, but a test encode with h264_nvenc "
                "failed. Your NVIDIA driver or CUDA runtime may be "
                "missing or broken. Try --encoder cpu instead."
            )


        return "h264_nvenc"


    if encoder_mode == "cpu":

        if has_libx264:

            return "libx264"


        raise RuntimeError(
            "CPU encoding was requested, but libx264 is not available "
            "in this FFmpeg build."
        )


    if encoder_mode != "auto":

        raise RuntimeError(
            f"Unsupported encoder mode: {encoder_mode}"
        )


    if has_nvenc and nvenc_is_usable():

        return "h264_nvenc"


    if has_libx264:

        return "libx264"


    raise RuntimeError(
        "No supported H.264 encoder found. "
        "Install an FFmpeg build containing h264_nvenc or libx264."
    )


def probe_video(video_path):

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate:format=duration",
        "-of",
        "json",
        video_path,
    ]


    data = json.loads(
        subprocess.check_output(
            cmd,
            text=True
        )
    )


    streams = data.get(
        "streams",
        []
    )


    if not streams:

        raise RuntimeError(
            f"No video stream found in {video_path}"
        )


    stream = streams[0]


    width = int(
        stream["width"]
    )


    height = int(
        stream["height"]
    )


    fps_text = stream.get(
        "avg_frame_rate",
        "0/0"
    )


    if fps_text in (
        "0/0",
        "N/A",
        ""
    ):

        fps_text = stream.get(
            "r_frame_rate",
            "0/0"
        )


    try:

        fps = float(
            Fraction(
                fps_text
            )
        )

    except Exception:

        fps = 0.0


    if fps <= 0:

        fps = 30.0


    try:

        duration = float(
            data
            .get(
                "format",
                {}
            )
            .get(
                "duration",
                0
            )
            or 0
        )

    except Exception:

        duration = 0.0


    return (
        width,
        height,
        fps,
        duration
    )


# ============================================================
# 1080x1920 ASPECT-PRESERVING SCALE + CENTER CROP
#
# NO PADDING.
# NO STRETCHING.
# ============================================================

def calculate_resize_crop(
    source_width,
    source_height
):

    scale = max(
        OUTPUT_WIDTH / source_width,
        OUTPUT_HEIGHT / source_height,
    )


    scaled_width = max(
        OUTPUT_WIDTH,
        int(
            math.ceil(
                source_width
                *
                scale
            )
        )
    )


    scaled_height = max(
        OUTPUT_HEIGHT,
        int(
            math.ceil(
                source_height
                *
                scale
            )
        )
    )


    # Keep intermediate dimensions even.
    if scaled_width % 2:

        scaled_width += 1


    if scaled_height % 2:

        scaled_height += 1


    crop_x = max(
        0,
        (
            scaled_width
            -
            OUTPUT_WIDTH
        )
        //
        2
    )


    crop_y = max(
        0,
        (
            scaled_height
            -
            OUTPUT_HEIGHT
        )
        //
        2
    )


    return (
        scaled_width,
        scaled_height,
        crop_x,
        crop_y
    )


def build_preprocess_filter(
    scaled_width,
    scaled_height,
    crop_x,
    crop_y
):

    return (

        f"scale="
        f"{scaled_width}:"
        f"{scaled_height}:"
        f"flags={SCALE_FLAGS},"

        f"crop="
        f"{OUTPUT_WIDTH}:"
        f"{OUTPUT_HEIGHT}:"
        f"{crop_x}:"
        f"{crop_y},"

        f"setsar=1"
    )


# ============================================================
# EXTRACT A SINGLE FRAME AT A GIVEN TIME
# ============================================================

def extract_frame_at(
    video_path,
    preprocess_filter,
    time_seconds
):

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error"
    ]


    if time_seconds > 0:

        cmd += [
            "-ss",
            str(
                time_seconds
            )
        ]


    cmd += [

        "-i",
        video_path,

        "-map",
        "0:v:0",

        "-frames:v",
        "1",

        "-vf",
        preprocess_filter,

        "-f",
        "rawvideo",

        "-pix_fmt",
        "rgb24",

        "pipe:1",
    ]


    raw = subprocess.check_output(
        cmd
    )


    expected_size = (
        OUTPUT_WIDTH
        *
        OUTPUT_HEIGHT
        *
        3
    )


    if len(raw) != expected_size:

        raise RuntimeError(
            f"Could not extract a 1080x1920 frame at "
            f"{time_seconds:.2f}s"
        )


    return np.frombuffer(
        raw,
        dtype=np.uint8
    ).reshape(
        OUTPUT_HEIGHT,
        OUTPUT_WIDTH,
        3,
    ).copy()


# ============================================================
# DETECT MOVIE / PICTURE AREA FROM MOTION BETWEEN TWO FRAMES
#
# PRIMARY detection method. Directly measures where pixels
# change between two sampled frames, instead of guessing from
# color/saturation in a single frame.
# ============================================================

def detect_picture_area_from_motion(
    frame_a_rgb,
    frame_b_rgb
):

    diff = np.abs(

        frame_a_rgb.astype(
            np.int16
        )

        -

        frame_b_rgb.astype(
            np.int16
        )
    )


    motion_mask = (
        diff.max(axis=2)
        >
        MOTION_DIFF_THRESHOLD
    )


    height, width = (
        motion_mask.shape
    )


    # ========================================================
    # VERTICAL
    # ========================================================

    row_score = motion_mask.mean(
        axis=1
    )


    smooth_row_score = np.convolve(

        row_score,

        np.ones(15)
        /
        15,

        mode="same"
    )


    row_segments = find_segments(
        smooth_row_score > MOTION_ROW_THRESHOLD
    )


    meaningful_rows = [

        seg

        for seg in row_segments

        if (
            seg[1]
            -
            seg[0]
        )
        >
        height * 0.08
    ]


    if not meaningful_rows:

        raise RuntimeError(
            "No vertical motion found between sampled frames"
        )


    top_y, bottom_y = max(

        meaningful_rows,

        key=lambda seg:
        seg[1] - seg[0],
    )


    picture_height = (
        bottom_y
        -
        top_y
        +
        1
    )


    # ========================================================
    # HORIZONTAL
    #
    # Deliberately NOT based on motion: a real static part of
    # the live video (e.g. a plain background behind a talking
    # subject, or just a subject that hasn't moved yet within
    # the short sampled window) would otherwise get wrongly
    # trimmed away even though it's genuinely part of the movie.
    # Use the same "assume full width, trim only a genuine dark
    # pillarbox border" logic as the color-based fallback,
    # within the vertical band that motion already located.
    # ========================================================

    gray_a = cv2.cvtColor(
        frame_a_rgb,
        cv2.COLOR_RGB2GRAY
    )

    gray_b = cv2.cvtColor(
        frame_b_rgb,
        cv2.COLOR_RGB2GRAY
    )

    left_x, right_x = trim_dark_horizontal_borders(
        gray_a,
        top_y,
        bottom_y,
        width,
        gray_b=gray_b,
    )


    picture_width = (
        right_x
        -
        left_x
        +
        1
    )


    # ========================================================
    # SAFETY
    # ========================================================

    if picture_height < height * 0.20:

        raise RuntimeError(
            "Detected motion region height is too small"
        )


    if picture_width < width * 0.20:

        raise RuntimeError(
            "Detected motion region width is too small"
        )


    return (
        left_x,
        top_y,
        picture_width,
        picture_height
    )


# ============================================================
# DETECT MOVIE / PICTURE AREA FROM ONE FRAME
#
# FALLBACK detection method, used only when motion-based
# detection isn't possible (video too short for a second
# distinct sample) or finds no significant motion.
# ============================================================

def detect_picture_area_from_frame(
    frame_rgb
):

    gray = cv2.cvtColor(
        frame_rgb,
        cv2.COLOR_RGB2GRAY
    )


    hsv = cv2.cvtColor(
        frame_rgb,
        cv2.COLOR_RGB2HSV
    )


    saturation = hsv[
        :,
        :,
        1
    ]


    content_pixels = (

        (
            (saturation > 18)
            &
            (gray > 25)
            &
            (gray < 245)
        )

        |

        (
            (saturation > 5)
            &
            (gray > 40)
            &
            (gray < 230)
        )
    )


    height, width = (
        content_pixels.shape
    )


    # ========================================================
    # VERTICAL
    # ========================================================

    row_score = content_pixels.mean(
        axis=1
    )


    smooth_row_score = np.convolve(

        row_score,

        np.ones(15)
        /
        15,

        mode="same"
    )


    row_segments = find_segments(
        smooth_row_score > 0.12
    )


    meaningful_rows = [

        seg

        for seg in row_segments

        if (
            seg[1]
            -
            seg[0]
        )
        >
        height * 0.15
    ]


    if not meaningful_rows:

        meaningful_rows = (
            row_segments
        )


    if not meaningful_rows:

        raise RuntimeError(
            "No vertical movie/picture area found"
        )


    core_top, core_bottom = max(

        meaningful_rows,

        key=lambda seg:
        seg[1] - seg[0],
    )


    top_y = core_top


    for yy in range(
        core_top,
        0,
        -1
    ):

        if (
            gray[
                yy,
                :
            ]
            <
            35
        ).mean() > BORDER_DARK_FRACTION:

            top_y = (
                yy + 1
            )

            break


    bottom_y = core_bottom


    for yy in range(
        core_bottom,
        height - 1
    ):

        if (
            gray[
                yy,
                :
            ]
            <
            35
        ).mean() > BORDER_DARK_FRACTION:

            bottom_y = (
                yy - 1
            )

            break


    picture_height = (
        bottom_y
        -
        top_y
        +
        1
    )


    # ========================================================
    # HORIZONTAL
    #
    # Unlike the vertical position (which varies a lot between
    # templates and has to be found by looking for content),
    # the embedded video almost always spans the full frame
    # width within its row band. Requiring "colorful content"
    # to justify each column wrongly excludes plain/pale parts
    # of the actual video (e.g. a light background) near the
    # edges, leaving them frozen and mis-colored. So default to
    # the full width and only pull inward where there really is
    # a solid dark pillarbox border, the same way the vertical
    # bounds are trimmed above.
    # ========================================================

    left_x, right_x = trim_dark_horizontal_borders(
        gray,
        top_y,
        bottom_y,
        width,
    )


    picture_width = (
        right_x
        -
        left_x
        +
        1
    )


    # ========================================================
    # SAFETY
    # ========================================================

    if picture_height < height * 0.20:

        raise RuntimeError(
            "Detected picture height is too small"
        )


    if picture_width < width * 0.20:

        raise RuntimeError(
            "Detected picture width is too small"
        )


    return (
        left_x,
        top_y,
        picture_width,
        picture_height
    )


# ============================================================
# DETECT MOVIE / PICTURE AREA
#
# Tries motion-based detection first (accurate regardless of
# color); falls back to the single-frame color/saturation
# heuristic if a second frame isn't available or no significant
# motion is found.
# ============================================================

def detect_picture_area(
    reference_rgb,
    motion_frame_rgb
):

    if motion_frame_rgb is None:

        fallback_reason = (
            "motion-based detection skipped "
            "(video too short for a second sample)"
        )

    else:

        try:

            (
                x,
                y,
                picture_width,
                picture_height
            ) = detect_picture_area_from_motion(
                reference_rgb,
                motion_frame_rgb,
            )

            return (
                x,
                y,
                picture_width,
                picture_height,
                "motion (2-frame diff)",
            )

        except RuntimeError as exc:

            fallback_reason = (
                f"motion-based detection unavailable "
                f"({exc})"
            )


    (
        x,
        y,
        picture_width,
        picture_height
    ) = detect_picture_area_from_frame(
        reference_rgb
    )

    return (
        x,
        y,
        picture_width,
        picture_height,
        f"color/saturation heuristic ({fallback_reason})",
    )


# ============================================================
# LOGO GEOMETRY
#
# Anchored to the detected frame so it adapts automatically
# to whatever position/size that frame has in each video.
# ============================================================

def compute_logo_geometry(
    x,
    y,
    picture_width,
    picture_height,
):

    logo_y = (
        y
        +
        picture_height
        +
        LOGO_GAP_PX
    )

    logo_width = round(
        picture_width
        *
        LOGO_SCALE
    )

    if logo_width % 2:

        logo_width += 1

    logo_width = max(
        2,
        logo_width
    )

    # Centered within the detected frame's width, not the full
    # canvas, so it stays aligned with the frame in every video.
    logo_x = (
        x
        +
        (
            picture_width
            -
            logo_width
        )
        //
        2
    )

    return (
        logo_x,
        logo_y,
        logo_width
    )


def compute_manual_logo_geometry(
    center_x,
    center_y,
    logo_width,
    logo_height,
):

    # Native size, no scaling: the logo is centered exactly on a
    # user-picked point (LOGO_POSITION_MODE = "fixed" or
    # "per_reel"), not positioned relative to the detected frame.

    logo_x = (
        center_x
        -
        logo_width // 2
    )

    logo_y = (
        center_y
        -
        logo_height // 2
    )

    return (
        logo_x,
        logo_y
    )


# ============================================================
# GENERATED BRANDING BLOCK
#
# Builds the same kind of image LOGO_PATH would normally point
# to, from simple editable parts (avatar / name / handle /
# checkmark) instead of requiring a pre-made file.
# ============================================================

def resolve_font(
    candidates,
    size
):

    for path in candidates:

        if os.path.isfile(path):

            try:

                return ImageFont.truetype(
                    path,
                    size
                )

            except Exception:

                continue


    print(
        "WARNING: no TrueType font found for the generated logo "
        "text; falling back to a low-quality built-in font."
    )

    return ImageFont.load_default()


def crop_avatar_to_circle(
    avatar_path,
    diameter
):

    source = Image.open(
        avatar_path
    ).convert(
        "RGBA"
    )

    width, height = source.size

    side = min(
        width,
        height
    )

    left = (
        width - side
    ) // 2

    top = (
        height - side
    ) // 2

    source = source.crop(
        (
            left,
            top,
            left + side,
            top + side,
        )
    )

    source = source.resize(
        (
            diameter,
            diameter
        ),
        Image.Resampling.LANCZOS,
    )

    mask = Image.new(
        "L",
        (
            diameter,
            diameter
        ),
        0,
    )

    ImageDraw.Draw(
        mask
    ).ellipse(
        (
            0,
            0,
            diameter - 1,
            diameter - 1,
        ),
        fill=255,
    )

    circular = Image.new(
        "RGBA",
        (
            diameter,
            diameter
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )

    circular.paste(
        source,
        (0, 0),
        mask,
    )

    return circular


def draw_checkmark_badge(
    draw,
    center,
    diameter
):

    cx, cy = center

    radius = diameter / 2

    draw.ellipse(
        (
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
        ),
        fill=CHECKMARK_BLUE,
    )

    stroke_width = max(
        2,
        round(
            diameter * 0.12
        )
    )

    p1 = (
        cx - radius * 0.5,
        cy
    )

    p2 = (
        cx - radius * 0.12,
        cy + radius * 0.4
    )

    p3 = (
        cx + radius * 0.55,
        cy - radius * 0.4
    )

    draw.line(
        [p1, p2],
        fill=(255, 255, 255),
        width=stroke_width,
        joint="curve",
    )

    draw.line(
        [p2, p3],
        fill=(255, 255, 255),
        width=stroke_width,
        joint="curve",
    )


def build_generated_logo_image(
    display_name,
    username,
    verified,
    avatar_path,
    text_rgb,
    background_rgb,
):

    has_avatar = (
        avatar_path is not None
    )

    has_name = bool(
        display_name
    )

    has_username = bool(
        username
    )

    if not (
        has_avatar
        or
        has_name
        or
        has_username
    ):

        raise RuntimeError(
            "Nothing to render for the generated logo: provide at "
            "least --avatar, --display-name, or --username."
        )


    bold_font = resolve_font(
        BOLD_FONT_CANDIDATES,
        NAME_FONT_SIZE,
    )

    regular_font = resolve_font(
        REGULAR_FONT_CANDIDATES,
        USERNAME_FONT_SIZE,
    )

    measure_draw = ImageDraw.Draw(
        Image.new(
            "RGBA",
            (1, 1)
        )
    )


    checkmark_diameter = round(
        NAME_FONT_SIZE
        *
        CHECKMARK_DIAMETER_RATIO
    )


    name_bbox = None
    name_width = 0
    name_height = 0

    if has_name:

        name_bbox = measure_draw.textbbox(
            (0, 0),
            display_name,
            font=bold_font,
        )

        name_width = (
            name_bbox[2]
            -
            name_bbox[0]
        )

        name_height = (
            name_bbox[3]
            -
            name_bbox[1]
        )

        if verified:

            name_width += (
                CHECKMARK_GAP
                +
                checkmark_diameter
            )


    username_text = None
    username_bbox = None
    username_width = 0
    username_height = 0

    if has_username:

        username_text = (
            username
            if username.startswith("@")
            else f"@{username}"
        )

        username_bbox = measure_draw.textbbox(
            (0, 0),
            username_text,
            font=regular_font,
        )

        username_width = (
            username_bbox[2]
            -
            username_bbox[0]
        )

        username_height = (
            username_bbox[3]
            -
            username_bbox[1]
        )


    text_block_width = max(
        name_width,
        username_width,
    )

    text_block_height = 0

    if has_name:

        text_block_height += name_height

    if has_name and has_username:

        text_block_height += TEXT_LINE_GAP

    if has_username:

        text_block_height += username_height


    avatar_block_width = (
        AVATAR_DIAMETER
        if has_avatar
        else 0
    )

    gap = (
        AVATAR_TEXT_GAP
        if has_avatar and (has_name or has_username)
        else 0
    )

    content_width = (
        avatar_block_width
        +
        gap
        +
        text_block_width
    )

    content_height = max(
        avatar_block_width,
        text_block_height,
    )

    canvas_width = (
        content_width
        +
        LOGO_PADDING * 2
    )

    canvas_height = (
        content_height
        +
        LOGO_PADDING * 2
    )

    canvas = Image.new(
        "RGBA",
        (
            canvas_width,
            canvas_height
        ),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        canvas
    )

    cursor_x = LOGO_PADDING


    if has_avatar:

        circular_avatar = crop_avatar_to_circle(
            avatar_path,
            AVATAR_DIAMETER,
        )

        avatar_y = (
            LOGO_PADDING
            +
            (
                content_height
                -
                AVATAR_DIAMETER
            )
            //
            2
        )

        canvas.paste(
            circular_avatar,
            (
                cursor_x,
                avatar_y
            ),
            circular_avatar,
        )

        cursor_x += (
            AVATAR_DIAMETER
            +
            gap
        )


    text_y = (
        LOGO_PADDING
        +
        (
            content_height
            -
            text_block_height
        )
        //
        2
    )


    if has_name:

        draw.text(
            (
                cursor_x - name_bbox[0],
                text_y - name_bbox[1],
            ),
            display_name,
            font=bold_font,
            fill=text_rgb,
        )

        if verified:

            badge_center_x = (
                cursor_x
                +
                (
                    name_bbox[2]
                    -
                    name_bbox[0]
                )
                +
                CHECKMARK_GAP
                +
                checkmark_diameter / 2
            )

            badge_center_y = (
                text_y
                +
                name_height / 2
            )

            draw_checkmark_badge(
                draw,
                (
                    badge_center_x,
                    badge_center_y,
                ),
                checkmark_diameter,
            )

        text_y += (
            name_height
            +
            TEXT_LINE_GAP
        )


    if has_username:

        username_color = tuple(

            round(

                text_rgb[i]
                +
                (
                    background_rgb[i]
                    -
                    text_rgb[i]
                )
                *
                USERNAME_BLEND_TOWARD_BACKGROUND
            )

            for i in range(3)
        )

        draw.text(
            (
                cursor_x - username_bbox[0],
                text_y - username_bbox[1],
            ),
            username_text,
            font=regular_font,
            fill=username_color,
        )


    return canvas


# ============================================================
# BUILD STATIC RECOLORED TEMPLATE
#
# IMPORTANT:
# THIS RUNS ONLY ONCE PER REEL.
# ============================================================

def build_static_template(
    reference_rgb,
    background_rgb,
    text_rgb,
    x,
    y,
    picture_width,
    picture_height,
):


    # ========================================================
    # SNAP NEAR-BLACK / NEAR-WHITE BEFORE RECOLORING
    #
    # A template's "black" background is rarely pure (0,0,0) —
    # compression, shadows, or a slight color cast can leave it
    # a few shades off (e.g. dark reddish-brown instead of
    # black). Inverting that exact off-black shade produces a
    # visibly tinted patch (e.g. pale blue) instead of matching
    # the rest of the recolored background, which inverts from
    # true black to true white. Snapping anything already close
    # to black/white to the exact value first avoids that seam.
    # The ORIGINAL reference_rgb (not this snapped copy) is
    # still used below for color/emoji preservation and for
    # restoring the movie rectangle.
    # ========================================================

    recolor_source = reference_rgb.copy()

    near_black = (
        recolor_source.max(axis=2)
        <
        BLACK_SNAP_THRESHOLD
    )

    recolor_source[near_black] = (
        0,
        0,
        0,
    )

    near_white = (
        recolor_source.min(axis=2)
        >
        WHITE_SNAP_THRESHOLD
    )

    recolor_source[near_white] = (
        255,
        255,
        255,
    )


    # ========================================================
    # RECOLOR
    # ========================================================

    if (
        background_rgb
        ==
        (
            255,
            255,
            255
        )

        and

        text_rgb
        ==
        (
            0,
            0,
            0
        )
    ):

        changed = (
            255 - recolor_source
        )


    elif (
        background_rgb
        ==
        (
            0,
            0,
            0
        )

        and

        text_rgb
        ==
        (
            255,
            255,
            255
        )
    ):

        changed = (
            recolor_source.copy()
        )


    else:

        bg = np.array(

            background_rgb,

            dtype=np.float32

        ).reshape(
            1,
            1,
            3
        )


        text = np.array(

            text_rgb,

            dtype=np.float32

        ).reshape(
            1,
            1,
            3
        )


        values = (

            recolor_source.astype(
                np.float32
            )

            /

            255.0
        )


        changed = (

            bg

            +

            (
                text
                -
                bg
            )

            *

            values
        )


        changed = np.clip(

            np.rint(
                changed
            ),

            0,

            255

        ).astype(
            np.uint8
        )


    # ========================================================
    # COLOR / EMOJI MASK
    #
    # CALCULATED ONCE ONLY.
    # ========================================================

    max_rgb = reference_rgb.max(
        axis=2
    ).astype(
        np.int16
    )


    min_rgb = reference_rgb.min(
        axis=2
    ).astype(
        np.int16
    )


    difference = (
        max_rgb
        -
        min_rgb
    )


    mask = (

        (
            difference
            >
            COLOR_PRESERVE_THRESHOLD
        )

        &

        (
            max_rgb
            >
            COLOR_MIN_BRIGHTNESS
        )

    ).astype(
        np.uint8
    ) * 255


    # ========================================================
    # MORPHOLOGY
    #
    # ALSO ONLY ONCE.
    # ========================================================

    kernel = np.ones(
        (
            3,
            3
        ),
        dtype=np.uint8
    )


    if EMOJI_MASK_DILATE_PASSES > 0:

        mask = cv2.dilate(

            mask,

            kernel,

            iterations=
            EMOJI_MASK_DILATE_PASSES,
        )


    if EMOJI_MASK_ERODE_PASSES > 0:

        mask = cv2.erode(

            mask,

            kernel,

            iterations=
            EMOJI_MASK_ERODE_PASSES,
        )


    # ========================================================
    # PRESERVE ORIGINAL COLORFUL ELEMENTS
    # ========================================================

    template = (
        changed.copy()
    )


    preserve = (
        mask > 0
    )


    # ========================================================
    # SUPPRESS PRESERVATION LEFT/RIGHT OF THE MOVIE RECTANGLE
    #
    # Anything colorful sharing the movie's own rows, but outside
    # its detected width, is essentially always bleed-through from
    # the live video (a person/object partially outside the
    # detected crop) rather than a genuine static emoji/logo
    # elsewhere in the template. Suppress the whole remaining
    # width on each side, not just a fixed margin, since the
    # bleed can extend arbitrarily far depending on the shot.
    # Preservation above/below the movie band is left untouched,
    # since that's where a real caption/footer emoji would be.
    # ========================================================

    preserve[
        y:
        y + picture_height,

        0:
        x
    ] = False

    preserve[
        y:
        y + picture_height,

        x + picture_width:
        OUTPUT_WIDTH
    ] = False


    # A thin margin directly above/below the rectangle is
    # suppressed too (not the full remaining height, unlike
    # left/right) - a caption/footer emoji is normally well clear
    # of the video, but a watermark baked into the video itself
    # can bleed a few pixels past the detected top/bottom edge.

    top_margin_y1 = max(
        0,
        y - EDGE_BLEED_MARGIN_PX
    )

    bottom_margin_y2 = min(
        OUTPUT_HEIGHT,
        y + picture_height + EDGE_BLEED_MARGIN_PX
    )

    preserve[
        top_margin_y1:
        y,

        x:
        x + picture_width
    ] = False

    preserve[
        y + picture_height:
        bottom_margin_y2,

        x:
        x + picture_width
    ] = False


    template[
        preserve
    ] = reference_rgb[
        preserve
    ]


    # ========================================================
    # RESTORE TV / MOVIE RECTANGLE
    # ========================================================

    x2 = min(
        OUTPUT_WIDTH,
        x + picture_width
    )


    y2 = min(
        OUTPUT_HEIGHT,
        y + picture_height
    )


    template[
        y:y2,
        x:x2
    ] = reference_rgb[
        y:y2,
        x:x2
    ]


    return template


def save_template_png(
    template_rgb,
    template_path
):

    template_bgr = cv2.cvtColor(

        template_rgb,

        cv2.COLOR_RGB2BGR
    )


    if not cv2.imwrite(
        template_path,
        template_bgr
    ):

        raise RuntimeError(
            f"Could not save temporary template: "
            f"{template_path}"
        )


# ============================================================
# RESUME / VALIDATE EXISTING OUTPUT
# ============================================================

def is_valid_completed_output(
    output_path,
    source_duration
):

    if not os.path.isfile(
        output_path
    ):

        return False


    if os.path.getsize(
        output_path
    ) < 1024:

        return False


    cmd = [

        "ffprobe",

        "-v",
        "error",

        "-select_streams",
        "v:0",

        "-show_entries",
        "stream=width,height:format=duration",

        "-of",
        "json",

        output_path,
    ]


    try:

        data = json.loads(

            subprocess.check_output(

                cmd,

                text=True,

                stderr=subprocess.STDOUT,
            )
        )


        stream = (
            data["streams"][0]
        )


        width = int(
            stream["width"]
        )


        height = int(
            stream["height"]
        )


        output_duration = float(

            data
            .get(
                "format",
                {}
            )
            .get(
                "duration",
                0
            )

            or

            0
        )


    except Exception:

        return False


    if (
        width != OUTPUT_WIDTH
        or
        height != OUTPUT_HEIGHT
    ):

        return False


    if output_duration <= 0.05:

        return False


    # Don't skip a broken/truncated output.
    if source_duration > 0:

        tolerance = max(

            2.0,

            source_duration
            *
            0.03
        )


        if output_duration < (
            source_duration
            -
            tolerance
        ):

            return False


    return True


# ============================================================
# ENCODE USING STATIC TEMPLATE
#
# NO PYTHON FRAME LOOP.
# NO PYTORCH FRAME LOOP.
#
# FFmpeg:
#
#   source
#      ↓
#   resize/crop 1080x1920
#      ↓
#   crop moving TV rectangle
#      ↓
#   overlay it onto static recolored template
#      ↓
#   NVENC
# ============================================================

def encode_with_static_template(
    video_path,
    template_path,
    output_path,
    preprocess_filter,
    fps,
    x,
    y,
    picture_width,
    picture_height,
    manual_logo_center=None,
):


    logo_enabled = (
        LOGO_PATH is not None
    )


    filter_complex = (

        f"[0:v]"
        f"{preprocess_filter}"
        f"[full];"

        f"[full]"
        f"crop="
        f"{picture_width}:"
        f"{picture_height}:"
        f"{x}:"
        f"{y}"
        f"[movie];"

        f"[1:v]"
        f"scale="
        f"{OUTPUT_WIDTH}:"
        f"{OUTPUT_HEIGHT},"
        f"setsar=1"
        f"[base];"
    )


    if logo_enabled and manual_logo_center is not None:

        logo_native_width, logo_native_height = Image.open(
            LOGO_PATH
        ).size

        (
            logo_x,
            logo_y
        ) = compute_manual_logo_geometry(
            manual_logo_center[0],
            manual_logo_center[1],
            logo_native_width,
            logo_native_height,
        )

        filter_complex += (

            f"[base]"
            f"[movie]"
            f"overlay="
            f"{x}:"
            f"{y}:"
            f"shortest=1"
            f"[composited];"

            f"[2:v]"
            f"format=rgba"
            f"[logo];"

            f"[composited]"
            f"[logo]"
            f"overlay="
            f"{logo_x}:"
            f"{logo_y}:"
            f"shortest=1,"
            f"format=yuv420p"
            f"[v]"
        )


    elif logo_enabled:

        (
            logo_x,
            logo_y,
            logo_width
        ) = compute_logo_geometry(
            x,
            y,
            picture_width,
            picture_height,
        )

        filter_complex += (

            f"[base]"
            f"[movie]"
            f"overlay="
            f"{x}:"
            f"{y}:"
            f"shortest=1"
            f"[composited];"

            f"[2:v]"
            f"format=rgba,"
            f"scale="
            f"{logo_width}:"
            f"-2"
            f"[logo];"

            f"[composited]"
            f"[logo]"
            f"overlay="
            f"{logo_x}:"
            f"{logo_y}:"
            f"shortest=1,"
            f"format=yuv420p"
            f"[v]"
        )


    else:

        filter_complex += (

            f"[base]"
            f"[movie]"
            f"overlay="
            f"{x}:"
            f"{y}:"
            f"shortest=1,"
            f"format=yuv420p"
            f"[v]"
        )


    cmd = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-y",


        # Original moving video
        "-i",
        video_path,


        # Static recolored template
        "-loop",
        "1",

        "-framerate",
        f"{fps:.8f}",

        "-i",
        template_path,
    ]


    if logo_enabled:

        cmd += [

            # Logo / branding overlay
            "-loop",
            "1",

            "-framerate",
            f"{fps:.8f}",

            "-i",
            LOGO_PATH,
        ]


    cmd += [

        "-filter_complex",
        filter_complex,


        "-map",
        "[v]",

        "-map",
        "0:a?",
    ]


    if VIDEO_ENCODER == "h264_nvenc":

        cmd += [

            "-c:v",
            "h264_nvenc",

            "-preset",
            NVENC_PRESET,

            "-rc",
            "vbr",

            "-cq",
            NVENC_CQ,

            "-b:v",
            "0",
        ]


    elif VIDEO_ENCODER == "libx264":

        cmd += [

            "-c:v",
            "libx264",

            "-preset",
            CPU_PRESET,

            "-crf",
            CPU_CRF,
        ]


    else:

        raise RuntimeError(
            f"Unsupported video encoder: {VIDEO_ENCODER}"
        )


    cmd += [

        "-pix_fmt",
        "yuv420p",


        # Audio
        "-c:a",
        "aac",

        "-b:a",
        "192k",


        # MP4
        "-movflags",
        "+faststart",

        "-shortest",

        output_path,
    ]


    subprocess.run(
        cmd,
        check=True
    )


# ============================================================
# PROCESS ONE VIDEO
# ============================================================

def process_video(
    video_path
):

    filename = os.path.basename(
        video_path
    )


    name, _ = os.path.splitext(
        filename
    )


    output_path = os.path.join(

        OUTPUT_FOLDER,

        f"{name}{OUTPUT_EXTENSION}",
    )


    template_path = os.path.join(

        TEMPLATE_FOLDER,

        f"{name}_static_template.png",
    )


    # ========================================================
    # SOURCE INFO
    # ========================================================

    (
        source_width,
        source_height,
        fps,
        source_duration
    ) = probe_video(
        video_path
    )


    # ========================================================
    # RESUME FROM PREVIOUS RUN
    # ========================================================

    if (
        SKIP_EXISTING_OUTPUTS

        and

        is_valid_completed_output(
            output_path,
            source_duration,
        )
    ):

        print(
            f"SKIP completed: "
            f"{filename}"
        )

        return "skipped"


    # ========================================================
    # RESOLVE MANUAL LOGO POSITION
    #
    # "fixed"/"per_reel": a video with no saved click position is
    # left alone entirely (not auto-placed, not processed without
    # a logo) until it's annotated, so a large library can be
    # annotated and processed incrementally over many sessions.
    # ========================================================

    manual_logo_center = None

    if LOGO_POSITION_MODE == "manual":

        manual_logo_center = logo_positions.get_position_for(
            LOGO_POSITIONS_DATA,
            filename,
        )

        if manual_logo_center is None:

            print(
                f"SKIP unannotated: "
                f"{filename}"
            )

            return "unannotated"


    # ========================================================
    # PRE-SCALE
    # ========================================================

    (
        scaled_width,
        scaled_height,
        crop_x,
        crop_y
    ) = calculate_resize_crop(

        source_width,

        source_height,
    )


    preprocess_filter = build_preprocess_filter(

        scaled_width,

        scaled_height,

        crop_x,

        crop_y,
    )


    # ========================================================
    # COLORS
    # ========================================================

    background_rgb = hex_to_rgb(
        TARGET_COLOR
    )


    text_rgb = get_text_rgb(
        background_rgb
    )


    # ========================================================
    # SAMPLE FRAME(S)
    #
    # Always extract the reference frame. Also try to extract a
    # second frame a bit later, so the movie region can be found
    # from actual motion instead of guessed from color.
    # ========================================================

    reference_rgb = extract_frame_at(

        video_path,

        preprocess_filter,

        REFERENCE_TIME_SECONDS,
    )


    motion_sample_time = (
        REFERENCE_TIME_SECONDS
        +
        MOTION_SAMPLE_OFFSET_SECONDS
    )


    motion_frame_rgb = None

    if (

        source_duration <= 0

        or

        motion_sample_time
        <
        source_duration - 0.05
    ):

        try:

            motion_frame_rgb = extract_frame_at(

                video_path,

                preprocess_filter,

                motion_sample_time,
            )

        except Exception:

            motion_frame_rgb = None


    # ========================================================
    # DETECT TV RECTANGLE
    # ========================================================

    (
        x,
        y,
        picture_width,
        picture_height,
        detection_method
    ) = detect_picture_area(
        reference_rgb,
        motion_frame_rgb,
    )


    # ========================================================
    # BUILD STATIC TEMPLATE ONCE
    # ========================================================

    template_rgb = build_static_template(

        reference_rgb,

        background_rgb,

        text_rgb,

        x,

        y,

        picture_width,

        picture_height,
    )


    save_template_png(

        template_rgb,

        template_path
    )


    # ========================================================
    # INFO
    # ========================================================

    print()

    print(
        "=" * 72
    )


    print(
        f"Processing: "
        f"{filename}"
    )


    print(

        f"Source: "
        f"{source_width}x{source_height} "
        f"@ "
        f"{fps:.3f} fps"
    )


    print(

        f"Pre-scale: "

        f"{source_width}x{source_height} "

        f"-> "

        f"{scaled_width}x{scaled_height} "

        f"-> center crop "

        f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}"
    )


    print(

        f"Reference frame: "
        f"{REFERENCE_TIME_SECONDS:.2f}s"

        +

        (
            f", motion sample at "
            f"{motion_sample_time:.2f}s"
            if motion_frame_rgb is not None
            else ""
        )
    )


    print(
        f"Detection method: "
        f"{detection_method}"
    )


    print(

        "Detected movie area: "

        f"x={x}, "

        f"y={y}, "

        f"width={picture_width}, "

        f"height={picture_height}"
    )


    if LOGO_PATH is not None and manual_logo_center is not None:

        logo_native_width, logo_native_height = Image.open(
            LOGO_PATH
        ).size

        (
            logo_x,
            logo_y
        ) = compute_manual_logo_geometry(
            manual_logo_center[0],
            manual_logo_center[1],
            logo_native_width,
            logo_native_height,
        )

        print(
            "Logo overlay (manual position): "

            f"{LOGO_PATH} "

            f"(center={manual_logo_center}, "

            f"x={logo_x}, "

            f"y={logo_y}, "

            f"width={logo_native_width}, "

            f"height={logo_native_height})"
        )

    elif LOGO_PATH is not None:

        (
            logo_x,
            logo_y,
            logo_width
        ) = compute_logo_geometry(
            x,
            y,
            picture_width,
            picture_height,
        )

        print(
            "Logo overlay: "

            f"{LOGO_PATH} "

            f"(x={logo_x}, "

            f"y={logo_y}, "

            f"width={logo_width}, "

            f"gap={LOGO_GAP_PX}px)"
        )

        if logo_y >= OUTPUT_HEIGHT:

            print(
                "WARNING: logo position is below the output "
                "canvas and will not be visible."
            )


    print(
        f"Background RGB: "
        f"{background_rgb}"
    )


    print(
        f"Text RGB: "
        f"{text_rgb}"
    )


    print(
        "Per-frame color/emoji analysis: OFF"
    )


    print(
        "Per-frame Python/PyTorch processing: OFF"
    )


    print(
        "Only the TV/movie rectangle changes each frame."
    )


    print(
        "=" * 72
    )


    # ========================================================
    # ENCODE
    # ========================================================

    try:

        encode_with_static_template(

            video_path,

            template_path,

            output_path,

            preprocess_filter,

            fps,

            x,

            y,

            picture_width,

            picture_height,

            manual_logo_center,
        )


    finally:

        try:

            if os.path.isfile(
                template_path
            ):

                os.remove(
                    template_path
                )

        except Exception:

            pass


    print(
        f"Saved: "
        f"{output_path}"
    )


    return "processed"


# ============================================================
# MAIN
# ============================================================

def main():

    global INPUT_FOLDER, OUTPUT_FOLDER, TEMPLATE_FOLDER, TARGET_COLOR, TEXT_COLOR, ENCODER_MODE, VIDEO_ENCODER, LOGO_PATH, LOGO_GAP_PX, LOGO_SCALE, AVATAR_PATH, DISPLAY_NAME, USERNAME, VERIFIED_BADGE, LOGO_POSITION_MODE, LOGO_POSITIONS_FILE, LOGO_POSITIONS_DATA

    parser = argparse.ArgumentParser(
        description="Recolor vertical video templates."
    )

    parser.add_argument(
        "--input",
        default=INPUT_FOLDER,
        help='Folder containing input videos. Default: "input_videos"',
    )

    parser.add_argument(
        "--output",
        default=OUTPUT_FOLDER,
        help='Folder where processed videos will be saved. Default: "output_videos"',
    )

    parser.add_argument(
        "--encoder",
        choices=(
            "auto",
            "nvenc",
            "cpu",
        ),
        default=ENCODER_MODE,
        help=(
            'Video encoder mode: "auto" prefers NVIDIA NVENC and falls back '
            'to CPU; "nvenc" forces h264_nvenc; "cpu" forces libx264.'
        ),
    )

    parser.add_argument(
        "--color",
        default=TARGET_COLOR,
        help='Background color in #RRGGBB format, e.g. "#FFD400"',
    )

    parser.add_argument(
        "--text-color",
        default=TEXT_COLOR,
        help='Text color in #RRGGBB format. If omitted, the opposite of --color is used.',
    )

    parser.add_argument(
        "--logo",
        default=LOGO_PATH,
        help=(
            "Path to a logo/branding image to overlay below the detected "
            "movie frame. If omitted, no logo is added."
        ),
    )

    parser.add_argument(
        "--logo-gap",
        type=int,
        default=LOGO_GAP_PX,
        help=(
            "Vertical gap in pixels between the bottom of the detected "
            "movie frame and the top of the logo. Default: 40"
        ),
    )

    parser.add_argument(
        "--logo-scale",
        type=float,
        default=LOGO_SCALE,
        help=(
            "Logo width as a fraction of the detected frame's width. "
            "Height is scaled to preserve aspect ratio. Default: "
            f"{RAW_LOGO_SCALE_DEFAULT} for a supplied --logo image, "
            f"{GENERATED_LOGO_SCALE_DEFAULT} for a generated branding "
            "block."
        ),
    )

    parser.add_argument(
        "--avatar",
        default=AVATAR_PATH,
        help=(
            "Path to a profile picture to generate a branding block "
            "from (center-cropped to a circle). Alternative to --logo; "
            "cannot be combined with it."
        ),
    )

    parser.add_argument(
        "--display-name",
        default=DISPLAY_NAME,
        help="Bold display name for the generated branding block.",
    )

    parser.add_argument(
        "--username",
        default=USERNAME,
        help=(
            'Handle for the generated branding block, e.g. "myhandle" '
            'or "@myhandle".'
        ),
    )

    parser.add_argument(
        "--verified",
        action=argparse.BooleanOptionalAction,
        default=VERIFIED_BADGE,
        help=(
            "Show a blue verified checkmark next to the display name "
            "in the generated branding block. Default: on. Use "
            "--no-verified to turn it off."
        ),
    )

    parser.add_argument(
        "--logo-position-mode",
        choices=(
            "auto",
            "manual",
        ),
        default=LOGO_POSITION_MODE,
        help=(
            '"auto" (default) positions the logo below the detected '
            'frame as usual. "manual" uses points clicked in the '
            "GUI's logo position picker, saved to "
            "--logo-positions-file, at the logo's native size instead "
            "of auto-scaling. Whether that file holds one shared "
            'point ("fixed") or one per video ("per_reel") is set by '
            "the picker itself, not this flag. In per_reel mode, a "
            "video with no saved point is skipped rather than "
            "auto-placed."
        ),
    )

    parser.add_argument(
        "--logo-positions-file",
        default=LOGO_POSITIONS_FILE,
        help=(
            "Path to the JSON file of manually-clicked logo "
            "positions. Default: <output folder>/logo_positions.json"
        ),
    )

    args = parser.parse_args()

    INPUT_FOLDER = args.input
    OUTPUT_FOLDER = args.output
    ENCODER_MODE = args.encoder
    TARGET_COLOR = args.color
    TEXT_COLOR = args.text_color
    LOGO_PATH = args.logo
    LOGO_GAP_PX = args.logo_gap
    LOGO_SCALE = args.logo_scale
    AVATAR_PATH = args.avatar
    DISPLAY_NAME = args.display_name
    USERNAME = args.username
    VERIFIED_BADGE = args.verified
    LOGO_POSITION_MODE = args.logo_position_mode
    LOGO_POSITIONS_FILE = args.logo_positions_file

    generated_logo_requested = (
        AVATAR_PATH is not None
        or
        DISPLAY_NAME is not None
        or
        USERNAME is not None
    )

    if LOGO_SCALE is None:

        LOGO_SCALE = (
            GENERATED_LOGO_SCALE_DEFAULT
            if generated_logo_requested
            else RAW_LOGO_SCALE_DEFAULT
        )

    if (
        LOGO_PATH is not None

        and

        not os.path.isfile(
            LOGO_PATH
        )
    ):

        raise RuntimeError(
            f"Logo file not found: {LOGO_PATH}"
        )

    if (
        LOGO_PATH is not None

        and

        generated_logo_requested
    ):

        raise RuntimeError(
            "--logo cannot be combined with --avatar/--display-name/"
            "--username. Use --logo for a ready-made image, or the "
            "--avatar/--display-name/--username/--verified options to "
            "generate one."
        )

    if (
        AVATAR_PATH is not None

        and

        not os.path.isfile(
            AVATAR_PATH
        )
    ):

        raise RuntimeError(
            f"Avatar file not found: {AVATAR_PATH}"
        )

    if (
        LOGO_POSITION_MODE != "auto"

        and

        LOGO_PATH is None

        and

        not generated_logo_requested
    ):

        raise RuntimeError(
            f"--logo-position-mode {LOGO_POSITION_MODE} requires a "
            "logo to position: pass --logo or "
            "--avatar/--display-name."
        )

    TEMPLATE_FOLDER = os.path.join(
        OUTPUT_FOLDER,
        "_static_templates"
    )

    os.makedirs(
        OUTPUT_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        TEMPLATE_FOLDER,
        exist_ok=True
    )

    if LOGO_POSITIONS_FILE is None:

        LOGO_POSITIONS_FILE = os.path.join(
            OUTPUT_FOLDER,
            "logo_positions.json"
        )

    if LOGO_POSITION_MODE == "manual":

        LOGO_POSITIONS_DATA = logo_positions.load_positions(
            LOGO_POSITIONS_FILE
        )

        if (

            LOGO_POSITIONS_DATA["mode"] == "fixed"

            and

            LOGO_POSITIONS_DATA["fixed_position"] is None
        ):

            raise RuntimeError(
                f"--logo-position-mode manual, but "
                f"{LOGO_POSITIONS_FILE} has no fixed_position set "
                "yet. Pick a position first (GUI: \"Same spot for "
                "all\")."
            )

    VIDEO_ENCODER = check_tools(
        ENCODER_MODE
    )


    background_rgb = hex_to_rgb(
        TARGET_COLOR
    )


    text_rgb = get_text_rgb(
        background_rgb
    )


    if generated_logo_requested:

        generated_logo_image = build_generated_logo_image(
            DISPLAY_NAME,
            USERNAME,
            VERIFIED_BADGE,
            AVATAR_PATH,
            text_rgb,
            background_rgb,
        )

        LOGO_PATH = os.path.join(
            TEMPLATE_FOLDER,
            "_generated_logo.png",
        )

        generated_logo_image.save(
            LOGO_PATH
        )


    print()

    print(
        "=" * 72
    )


    print(
        "STATIC TEMPLATE RECOLOR"
    )


    print(
        f"Output: "
        f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}"
    )


    print(
        "Aspect ratio: preserved"
    )


    print(
        "Padding: none"
    )


    print(
        "Final framing: center crop"
    )


    print(

        f"Target/background: "
        f"{TARGET_COLOR} "
        f"-> "
        f"{background_rgb}"
    )


    print(

        f"Text color: "

        f"{TEXT_COLOR if TEXT_COLOR is not None else 'AUTO OPPOSITE'} "

        f"-> "

        f"{text_rgb}"
    )


    print(

        f"Reference frame time: "
        f"{REFERENCE_TIME_SECONDS:.2f}s"
    )


    print(

        f"Skip completed outputs: "
        f"{SKIP_EXISTING_OUTPUTS}"
    )


    if generated_logo_requested:

        print(
            "Logo: generated "
            f"(avatar={AVATAR_PATH}, "
            f"name={DISPLAY_NAME!r}, "
            f"username={USERNAME!r}, "
            f"verified={VERIFIED_BADGE})"
        )

        print(
            f"Logo gap: "
            f"{LOGO_GAP_PX}px"
        )

        print(
            f"Logo scale: "
            f"{LOGO_SCALE}"
        )

    elif LOGO_PATH is not None:

        print(
            f"Logo: "
            f"{LOGO_PATH}"
        )

        print(
            f"Logo gap: "
            f"{LOGO_GAP_PX}px"
        )

        print(
            f"Logo scale: "
            f"{LOGO_SCALE}"
        )

    else:

        print(
            "Logo: disabled"
        )


    if LOGO_POSITION_MODE == "manual":

        if LOGO_POSITIONS_DATA["mode"] == "fixed":

            print(
                "Logo position mode: manual (fixed point "
                f"{LOGO_POSITIONS_DATA['fixed_position']} for every "
                "video)"
            )

        else:

            annotated_count = len(
                LOGO_POSITIONS_DATA["positions"]
            )

            print(
                "Logo position mode: manual (per-reel, "
                f"{annotated_count} video(s) currently annotated in "
                f"{LOGO_POSITIONS_FILE})"
            )


    print(

        f"Encoder mode: "
        f"{ENCODER_MODE}"
    )


    print(

        f"Video encoder: "
        f"{VIDEO_ENCODER}"
    )


    if VIDEO_ENCODER == "libx264":

        if ENCODER_MODE == "cpu":

            print(
                "CPU encoding forced by --encoder cpu."
            )

        else:

            print(
                "NVIDIA NVENC not available or not working "
                "(missing/broken driver); using CPU encoding."
            )


    print(
        "=" * 72
    )


    supported_extensions = (

        ".mp4",

        ".mov",

        ".mkv",

        ".avi",

        ".webm",
    )


    video_files = sorted(

        path

        for path in glob.glob(

            os.path.join(
                INPUT_FOLDER,
                "*.*"
            )
        )

        if path.lower().endswith(
            supported_extensions
        )
    )


    if not video_files:

        print(
            f"No videos found in: "
            f"{INPUT_FOLDER}"
        )

        return


    print(
        f"Found "
        f"{len(video_files)} "
        f"video(s)."
    )


    processed_count = 0

    skipped_count = 0

    unannotated_count = 0

    error_count = 0


    for video_path in video_files:

        try:

            result = process_video(
                video_path
            )


            if result == "skipped":

                skipped_count += 1


            elif result == "unannotated":

                unannotated_count += 1


            else:

                processed_count += 1


        except Exception as exc:

            error_count += 1


            print()

            print(

                f"ERROR processing: "
                f"{video_path}"
            )


            print(
                exc
            )


            print(
                "-" * 72
            )


    if generated_logo_requested:

        try:

            if os.path.isfile(
                LOGO_PATH
            ):

                os.remove(
                    LOGO_PATH
                )

        except Exception:

            pass


    try:

        if (

            os.path.isdir(
                TEMPLATE_FOLDER
            )

            and

            not os.listdir(
                TEMPLATE_FOLDER
            )
        ):

            os.rmdir(
                TEMPLATE_FOLDER
            )

    except Exception:

        pass


    print()

    print(
        "=" * 72
    )


    print(
        "BATCH FINISHED"
    )


    print(

        f"Processed now: "
        f"{processed_count}"
    )


    print(

        f"Skipped already completed: "
        f"{skipped_count}"
    )


    if LOGO_POSITION_MODE == "manual":

        print(

            f"Skipped (no saved logo position yet): "
            f"{unannotated_count}"
        )


    print(

        f"Errors: "
        f"{error_count}"
    )


    print(
        "=" * 72
    )


if __name__ == "__main__":

    main()