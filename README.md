# Reel Template Recolor

![Python Syntax Check](https://github.com/qasimrao789/reel-template-recolor/actions/workflows/python-check.yml/badge.svg)

A Python, OpenCV, and FFmpeg tool for automatically recoloring **vertical video templates** while preserving the embedded moving video and colorful elements such as emojis.

The tool supports both **NVIDIA NVENC GPU encoding** and **libx264 CPU encoding**, with automatic or manual encoder selection.

This project started as a personal automation tool for a video workflow I use regularly.

## Before & After

### Before

![Before](examples/before.jpg)

### After

![After](examples/after.jpg)

## What It Does

The tool batch-processes videos from an input folder and produces recolored **1080×1920 vertical videos** in an output folder.

Instead of processing every frame with Python, it analyzes only **one reference frame** to determine which parts of the layout are static and where the actual moving video is located.

It then:

* Scans an entire input folder for supported videos
* Resizes and center-crops each video to 1080×1920
* Automatically detects the embedded movie/video region
* Recolors the surrounding static template
* Preserves colorful elements such as emojis
* Restores the original movie region
* Uses FFmpeg to overlay the moving video onto the recolored template
* Supports NVIDIA NVENC GPU encoding
* Supports libx264 CPU encoding
* Automatically chooses an encoder by default
* Allows the encoder to be forced from the command line
* Preserves the original audio
* Saves completed videos into the selected output folder
* Skips outputs that were already successfully processed

## Why I Built It

I needed to repeatedly recolor the same style of vertical video template.

A straightforward solution would be to process every frame through Python and OpenCV.

However, most of the template does not change between frames.

Only the embedded movie/video area is moving.

So instead of repeatedly analyzing thousands of frames, this tool:

1. Analyzes one reference frame
2. Detects the moving video region
3. Builds the recolored static template once
4. Lets FFmpeg handle the moving video for the rest of the encode

This keeps expensive frame-by-frame image processing outside Python.

## How It Works

```text
Input Folder
    ↓
Find Supported Videos
    ↓
Read Metadata with ffprobe
    ↓
Aspect-Ratio-Preserving Resize
    ↓
Center Crop to 1080×1920
    ↓
Extract One Reference Frame
    ↓
Analyze Frame with OpenCV
    ↓
Detect Embedded Video Region
    ↓
Build Recolored Static Template
    ↓
Preserve Colorful Elements
    ↓
FFmpeg Overlays Moving Video Region
    ↓
Select Encoder
    ↓
h264_nvenc GPU or libx264 CPU
    ↓
Final MP4
```

## Features

* Whole-folder batch processing
* Custom input folder with `--input`
* Custom output folder with `--output`
* Manual encoder selection with `--encoder`
* Automatic GPU/CPU encoder selection
* NVIDIA `h264_nvenc` support
* CPU `libx264` fallback
* 1080×1920 vertical output
* Aspect ratio preserved
* No stretching
* No padding / letterboxing
* Automatic center cropping
* Automatic embedded video region detection
* Custom background color
* Custom text color
* Automatic contrasting text color
* Color and emoji preservation
* Existing-output validation
* Resume / skip completed videos
* Original audio preserved
* FFmpeg-based video compositing
* No Python per-frame processing loop
* Automatic Python syntax checking with GitHub Actions

## Requirements

### Python

Python 3 is required.

### Python Packages

Install the required packages with:

```bash
pip install -r requirements.txt
```

The project currently uses:

* NumPy
* OpenCV

### FFmpeg

FFmpeg and ffprobe must be installed and available in your system `PATH`.

Check FFmpeg with:

```bash
ffmpeg -version
```

Check ffprobe with:

```bash
ffprobe -version
```

### Video Encoder

The tool supports:

```text
h264_nvenc
libx264
```

At least one of these should be available in your FFmpeg build.

On Windows:

```bash
ffmpeg -encoders | findstr /i "nvenc libx264"
```

On Linux or macOS:

```bash
ffmpeg -encoders | grep -E "nvenc|libx264"
```

An NVIDIA GPU is optional.

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/qasimrao789/reel-template-recolor.git
```

Move into the project folder:

```bash
cd reel-template-recolor
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Check FFmpeg

Run:

```bash
ffmpeg -version
```

Then check your available H.264 encoders.

Windows:

```bash
ffmpeg -encoders | findstr /i "nvenc libx264"
```

Linux/macOS:

```bash
ffmpeg -encoders | grep -E "nvenc|libx264"
```

## Basic Usage

By default, the tool looks for videos inside:

```text
input_videos/
```

Run:

```bash
python reel_recolor.py
```

Completed videos are saved inside:

```text
output_videos/
```

## Supported Video Formats

The program currently scans for:

```text
.mp4
.mov
.mkv
.avi
.webm
```

For example:

```text
input_videos/
├── video1.mp4
├── video2.mov
├── video3.mkv
└── video4.webm
```

Running:

```bash
python reel_recolor.py
```

will process all four videos.

## Command-Line Options

To see all available options:

```bash
python reel_recolor.py --help
```

The current options are:

```text
--input
--output
--encoder
--color
--text-color
```

## Choose an Input Folder

Use `--input` to process videos from any folder.

Example:

```bash
python reel_recolor.py --input "D:\My Videos"
```

Every supported video directly inside the selected folder will be processed.

## Choose an Output Folder

Use `--output` to choose where completed videos are saved.

Example:

```bash
python reel_recolor.py --output "D:\Finished Videos"
```

You can combine custom input and output folders:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished Videos"
```

## Whole-Folder Batch Processing

The `--input` option accepts a folder rather than a single file.

For example:

```text
D:\My Videos\
├── clip1.mp4
├── clip2.mp4
├── reel1.mov
└── movie.webm
```

Run:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished"
```

All supported videos directly inside `D:\My Videos` will be processed.

### Current Folder Limitation

Nested subfolders are not currently searched recursively.

For example:

```text
My Videos/
├── clip1.mp4
├── clip2.mp4
│
└── Archive/
    └── clip3.mp4
```

`clip1.mp4` and `clip2.mp4` are processed.

`Archive/clip3.mp4` is currently ignored.

## Encoder Selection

The tool supports three encoder modes:

```text
auto
nvenc
cpu
```

Use the `--encoder` option to choose one.

### Automatic Mode

This is the default:

```bash
python reel_recolor.py --encoder auto
```

Behavior:

```text
h264_nvenc available
        ↓
Use NVIDIA GPU encoding

h264_nvenc unavailable
        ↓
Use libx264 CPU encoding
```

You can also simply run:

```bash
python reel_recolor.py
```

because `auto` is the default mode.

### Force NVIDIA NVENC

Use:

```bash
python reel_recolor.py --encoder nvenc
```

This requires FFmpeg to provide:

```text
h264_nvenc
```

If NVENC is not available, the program stops with an error instead of silently switching to CPU encoding.

### Force CPU Encoding

Use:

```bash
python reel_recolor.py --encoder cpu
```

This forces:

```text
libx264
```

even if NVIDIA NVENC is available.

This is useful for:

* Testing CPU encoding
* Running on systems without NVIDIA GPUs
* Comparing GPU and CPU encoding
* Troubleshooting NVENC issues

The CPU path has been tested successfully during development.

## Encoder Output

At startup, the program displays the selected mode and resolved encoder.

For automatic GPU encoding:

```text
Encoder mode: auto
Video encoder: h264_nvenc
```

For forced CPU encoding:

```text
Encoder mode: cpu
Video encoder: libx264
CPU encoding forced by --encoder cpu.
```

For automatic CPU fallback:

```text
Encoder mode: auto
Video encoder: libx264
NVIDIA NVENC not available; using CPU encoding.
```

## GPU vs CPU Output Names

GPU-encoded files use a suffix containing:

```text
_recolored_cuda_
```

CPU-encoded files use:

```text
_recolored_cpu_
```

This makes it easy to identify which encoder produced an output.

## Change the Background Color

Use `--color` with a standard hexadecimal `#RRGGBB` color.

Example:

```bash
python reel_recolor.py --color "#FFD400"
```

Other examples:

```bash
python reel_recolor.py --color "#FFFFFF"
```

```bash
python reel_recolor.py --color "#000000"
```

```bash
python reel_recolor.py --color "#FF0000"
```

## Change the Text Color

Use `--text-color`:

```bash
python reel_recolor.py --text-color "#FF0000"
```

You can combine background and text colors:

```bash
python reel_recolor.py --color "#FFFFFF" --text-color "#FF0000"
```

Another example:

```bash
python reel_recolor.py --color "#0000FF" --text-color "#FFFF00"
```

## Automatic Text Color

If `--text-color` is not provided, the program automatically uses the opposite RGB color of the selected background.

For example:

```bash
python reel_recolor.py --color "#FFFFFF"
```

results in:

```text
Background: white
Text: black
```

And:

```bash
python reel_recolor.py --color "#000000"
```

results in:

```text
Background: black
Text: white
```

## Combine All Options

All command-line options can be combined.

Example:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished Videos" --encoder cpu --color "#FFFFFF" --text-color "#FF0000"
```

This means:

```text
Input folder:
D:\My Videos

Output folder:
D:\Finished Videos

Encoder:
libx264 CPU

Background:
White

Text:
Red
```

Another example using automatic encoder selection:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished Videos" --encoder auto --color "#FFD400"
```

## Default Configuration

Command-line arguments override the defaults for the current run.

### Default Input Folder

```python
INPUT_FOLDER = "input_videos"
```

### Default Output Folder

```python
OUTPUT_FOLDER = "output_videos"
```

### Default Encoder Mode

```python
ENCODER_MODE = "auto"
```

### Default Background Color

```python
TARGET_COLOR = "#FFFFFF"
```

### Default Text Color

```python
TEXT_COLOR = None
```

When `TEXT_COLOR` is `None`, automatic opposite-color behavior is used.

## Encoding Settings

### NVIDIA NVENC

The current NVIDIA encoding defaults include:

```python
NVENC_PRESET = "p1"
NVENC_CQ = "18"
```

### CPU / libx264

The CPU encoder uses:

```python
CPU_PRESET = "medium"
CPU_CRF = "18"
```

## Output Resolution

The default output resolution is:

```python
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
```

The source aspect ratio is preserved.

The image is scaled until it completely fills the 1080×1920 output and is then center-cropped.

The program does not stretch the video and does not add padding.

## Reference Frame

The default reference frame is taken from the beginning of each video:

```python
REFERENCE_TIME_SECONDS = 0.0
```

If videos begin with a black frame or fade-in, you can change this to:

```python
REFERENCE_TIME_SECONDS = 0.5
```

## Automatic Video Region Detection

The tool attempts to detect the embedded movie/video area by analyzing one reference frame.

OpenCV examines properties including:

* Brightness
* Saturation
* Horizontal content distribution
* Vertical content distribution
* Dark separator/border regions

The detected rectangle is treated as the dynamic part of the template.

Everything outside that region is used to construct the static recolored template.

## Color Preservation

Recoloring every pixel could destroy colorful elements such as:

* Emojis
* Icons
* Logos
* Colored graphics

The program creates a mask based on differences between RGB channels.

Pixels that appear sufficiently colorful are preserved from the original reference frame.

OpenCV dilation and erosion are used to clean the preservation mask.

## Performance Approach

The main optimization is avoiding a Python per-frame processing loop.

A video may contain thousands of frames.

Instead of performing OpenCV operations on every frame, the program performs template analysis only once.

FFmpeg then handles the frame-by-frame compositing:

```text
Static Recolored Template
            +
Moving Video Rectangle
            ↓
      Final Video
```

Encoding is handled by either:

```text
h264_nvenc
```

or:

```text
libx264
```

depending on the selected encoder mode.

## Existing Output Detection

The tool can skip videos that have already been successfully processed.

It does more than simply check whether an output filename exists.

Before skipping an output, the program validates:

* File existence
* Minimum file size
* Output resolution
* Output duration
* Whether the output appears truncated

This helps prevent incomplete or corrupted outputs from being treated as finished.

## Project Structure

```text
reel-template-recolor/
│
├── .github/
│   └── workflows/
│       └── python-check.yml
│
├── examples/
│   ├── before.jpg
│   └── after.jpg
│
├── reel_recolor.py
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

Default runtime folders:

```text
input_videos/
output_videos/
```

These are excluded from Git so personal source videos and generated outputs are not uploaded to the repository.

## Automated Checks

The repository uses GitHub Actions to automatically run a Python syntax check whenever changes are pushed to `main` or included in a pull request.

This helps catch syntax errors before changes are merged.

## Tech Used

* Python
* OpenCV
* NumPy
* FFmpeg
* ffprobe
* NVIDIA NVENC
* libx264
* H.264
* AAC
* Git
* GitHub
* GitHub Actions

## Current Limitations

### Static Template Assumption

The tool assumes most content outside the embedded movie/video region remains static.

Animated elements outside the detected movie rectangle may not behave correctly.

Examples include:

* Animated captions
* Progress bars
* Moving stickers
* Changing interface elements
* Animated backgrounds

### Single Reference Frame

Detection currently uses one reference frame per video.

If that frame contains:

* A fade
* A black screen
* A transition
* An unusual scene

automatic region detection may be less accurate.

Changing `REFERENCE_TIME_SECONDS` can help.

### CPU Encoding Performance

CPU encoding with `libx264` may be significantly slower than NVENC GPU encoding depending on the system.

### Heuristic Detection

The movie-region detector uses image-processing heuristics rather than a machine-learning model.

Unusual layouts may require adjustments to the detection thresholds.

### No Recursive Folder Scanning

The selected input folder is batch-processed, but nested subfolders are not currently searched automatically.

## Future Improvements

Possible future improvements include:

* Command-line reference-frame selection
* Configurable output resolution
* Multi-frame sampling for more reliable region detection
* Better handling of grayscale content
* Performance benchmarks comparing NVENC and libx264
* More configurable detection thresholds
* Automated tests beyond syntax checking
* Easier installation and packaging
* Optional recursive folder processing if needed

## License

This project is available under the MIT License.

See the `LICENSE` file for details.

## Project Status

This project started as a personal automation tool for a workflow I use myself.

It is functional for that workflow and is being gradually cleaned up and improved as a reusable open-source project.
