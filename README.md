# Reel Template Recolor

![Python Syntax Check](https://github.com/qasimrao789/reel-template-recolor/actions/workflows/python-check.yml/badge.svg)

A Python, OpenCV, and FFmpeg tool for automatically recoloring **vertical video templates** while preserving the embedded moving video and colorful elements such as emojis.

This started as a personal automation tool for a video workflow I use regularly.

## Before & After

### Before

![Before](examples/before.jpg)

### After

![After](examples/after.jpg)

## What It Does

The tool takes videos from an `input_videos` folder and produces recolored **1080×1920 vertical videos** in an `output_videos` folder.

Instead of processing every frame with Python, it analyzes only **one reference frame** to determine which parts of the layout are static and where the actual moving video is located.

It then:

* Resizes and center-crops the video to 1080×1920
* Automatically detects the embedded movie/video region
* Recolors the surrounding static template
* Preserves colorful elements such as emojis
* Restores the original movie region
* Uses FFmpeg to overlay the moving video onto the recolored template
* Uses NVIDIA NVENC for H.264 encoding
* Preserves the original audio
* Skips outputs that were already successfully processed

## Why I Built It

I needed to repeatedly recolor the same style of vertical video template.

A straightforward solution would be to process every single frame through Python and OpenCV.

However, most of the template does not change between frames.

Only the embedded movie/video area is moving.

So instead of repeatedly analyzing thousands of frames, this tool:

1. Analyzes one reference frame
2. Detects the moving video region
3. Builds the recolored static template once
4. Lets FFmpeg handle the moving video for the rest of the encode

This reduces the amount of per-frame work performed in Python.

## How It Works

```text
Input Video
    ↓
Read Video Metadata with ffprobe
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
Create Recolored Static Template
    ↓
Preserve Colorful Elements
    ↓
FFmpeg Overlays Moving Video Region
    ↓
NVIDIA NVENC H.264 Encoding
    ↓
Final MP4
```

## Features

* 1080×1920 vertical output
* Aspect ratio preserved
* No stretching
* No padding / letterboxing
* Automatic center cropping
* Automatic embedded video region detection
* Custom background color
* Command-line `--color` option
* Automatic contrasting text color
* Optional custom text color in source settings
* Color and emoji preservation
* Batch processing
* Existing-output validation
* Resume / skip completed videos
* Original audio preserved
* FFmpeg-based video compositing
* NVIDIA NVENC H.264 encoding
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

You can verify this by running:

```bash
ffmpeg -version
```

and:

```bash
ffprobe -version
```

### NVIDIA GPU

The current version requires an NVIDIA GPU and an FFmpeg build containing the `h264_nvenc` encoder.

On Windows, you can check for NVENC support with:

```bash
ffmpeg -encoders | findstr nvenc
```

On Linux or macOS:

```bash
ffmpeg -encoders | grep nvenc
```

You should see `h264_nvenc` in the output.

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

### 3. Create the Input Folder

Create a folder named:

```text
input_videos
```

Your project should look roughly like:

```text
reel-template-recolor/
│
├── examples/
│   ├── before.jpg
│   └── after.jpg
│
├── input_videos/
├── README.md
├── LICENSE
├── reel_recolor.py
├── requirements.txt
└── .gitignore
```

The `output_videos` folder will be created automatically when the program runs.

## Usage

Place your videos inside:

```text
input_videos/
```

Supported formats include:

```text
.mp4
.mov
.mkv
.avi
.webm
```

Then run:

```bash
python reel_recolor.py
```

The processed videos will be saved inside:

```text
output_videos/
```

## Command-Line Color Option

The background color can be changed without editing the Python source code.

For example:

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

Colors must use the standard `#RRGGBB` hexadecimal format.

To view the available command-line options:

```bash
python reel_recolor.py --help
```

If no `--color` option is provided, the program uses the default color configured in the source code.

## Configuration

The main settings are near the top of `reel_recolor.py`.

### Default Background Color

```python
TARGET_COLOR = "#FFFFFF"
```

Any standard `#RRGGBB` hexadecimal color can be used.

The default can still be changed directly in the source code, but the `--color` command-line option makes this unnecessary for normal use.

### Text Color

By default:

```python
TEXT_COLOR = None
```

When set to `None`, the program automatically uses the opposite RGB color of the selected background.

You can also specify a color manually:

```python
TEXT_COLOR = "#000000"
```

### Output Resolution

The default output is:

```python
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
```

### Reference Frame

The default reference frame is taken from the very beginning of the video:

```python
REFERENCE_TIME_SECONDS = 0.0
```

If your videos begin with a black frame or fade-in, try:

```python
REFERENCE_TIME_SECONDS = 0.5
```

## Automatic Video Region Detection

The tool attempts to determine where the embedded movie/video area is located by analyzing the reference frame.

It uses OpenCV to examine properties such as:

* Brightness
* Saturation
* Horizontal content distribution
* Vertical content distribution
* Dark separator/border regions

The detected rectangle is then treated as the dynamic portion of the video.

Everything outside that rectangle is used to create the static recolored template.

## Color Preservation

Simply recoloring the entire template could destroy colorful elements such as:

* Emojis
* Icons
* Logos
* Colored graphics

The program creates a mask based on differences between the RGB channels.

Pixels that appear sufficiently colorful are preserved from the original reference frame.

OpenCV dilation and erosion are also used to clean the preservation mask.

## Performance Approach

The main optimization in this project is avoiding a Python frame-processing loop.

A typical video may contain thousands of frames.

Instead of performing OpenCV operations on every frame, this program performs the expensive template analysis only once.

FFmpeg then performs the final video compositing:

```text
Static Recolored Template
            +
Moving Video Rectangle
            ↓
      Final Video
```

Video encoding is handled using NVIDIA's `h264_nvenc` encoder.

## Existing Output Detection

The tool can skip videos that have already been processed.

It does not simply check whether the output filename exists.

Before skipping an output, it validates properties including:

* File existence
* Minimum file size
* Output resolution
* Output duration
* Whether the output appears truncated

This helps avoid treating broken or incomplete encodes as successfully completed files.

## Current Limitations

### Static Template Assumption

The tool assumes that most of the content outside the embedded video region remains static.

Animated elements outside the detected movie rectangle may therefore not behave correctly.

Examples include:

* Animated captions
* Progress bars
* Moving stickers
* Changing interface elements
* Animated backgrounds

### Single Reference Frame

Detection currently uses one reference frame.

If that frame contains:

* A fade
* A black screen
* A transition
* An unusual scene

the automatic region detection may be less accurate.

Changing `REFERENCE_TIME_SECONDS` can help.

### NVIDIA Requirement

The current version requires FFmpeg with NVIDIA NVENC support.

A CPU encoding fallback is not currently implemented.

### Heuristic Detection

The movie-region detector is based on image-processing heuristics rather than a machine-learning model.

Unusual layouts may therefore require adjustments to the detection thresholds.

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

Runtime folders such as `input_videos` and `output_videos` are excluded from Git so personal and generated videos are not uploaded to the repository.

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
* H.264
* AAC
* Git
* GitHub Actions

## Future Improvements

Possible improvements include:

* More command-line options
* Command-line input and output folder selection
* Command-line text color selection
* CPU encoding fallback using `libx264`
* Automatic encoder selection
* Multi-frame sampling for more reliable region detection
* Better handling of grayscale content
* Performance benchmarks
* More configurable detection settings
* Additional output resolution options

## License

This project is available under the MIT License.

See the `LICENSE` file for details.

## Project Status

This project started as a personal automation tool for a workflow I use myself.

It is functional for that workflow and is being gradually cleaned up and improved as a reusable open-source project.
