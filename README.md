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
* Uses NVIDIA NVENC for H.264 encoding
* Preserves the original audio
* Saves completed videos into the selected output folder
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
Input Folder
    ↓
Find Supported Video Files
    ↓
Process Each Video
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
Output Folder
```

## Features

* Whole-folder batch processing
* Custom input folder with `--input`
* Custom output folder with `--output`
* 1080×1920 vertical output
* Aspect ratio preserved
* No stretching
* No padding / letterboxing
* Automatic center cropping
* Automatic embedded video region detection
* Custom background color
* Command-line `--color` option
* Command-line `--text-color` option
* Automatic contrasting text color when no custom text color is provided
* Color and emoji preservation
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

### 3. Prepare Your Videos

By default, the program looks for videos inside:

```text
input_videos/
```

You can create that folder manually, or use the `--input` option to point the program at any folder on your computer.

The default output folder is:

```text
output_videos/
```

You can also choose a different output folder with `--output`.

## Basic Usage

Place one or more videos inside:

```text
input_videos/
```

Then run:

```bash
python reel_recolor.py
```

The program will process every supported video directly inside that folder.

Completed videos will be saved inside:

```text
output_videos/
```

## Supported Video Formats

The tool currently scans for:

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
--color
--text-color
```

## Choose an Input Folder

Use `--input` to process videos from any folder.

Example:

```bash
python reel_recolor.py --input "D:\My Videos"
```

The tool will scan that folder and process all supported video files directly inside it.

You are not required to copy videos into the default `input_videos` folder when using this option.

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

This will:

```text
Read videos from:
D:\My Videos

Save completed videos to:
D:\Finished Videos
```

## Whole-Folder Batch Processing

The `--input` option points to a folder, not a single video file.

For example, if:

```text
D:\My Videos\
├── clip1.mp4
├── clip2.mp4
├── reel1.mov
└── movie.webm
```

you run:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished"
```

the program will process all supported videos inside `D:\My Videos`.

### Current Folder Limitation

The current version scans the selected folder itself but does not recursively search nested subfolders.

For example:

```text
My Videos/
├── clip1.mp4
├── clip2.mp4
│
└── Archive/
    └── clip3.mp4
```

`clip1.mp4` and `clip2.mp4` will be found.

`Archive/clip3.mp4` will not currently be processed automatically.

Recursive folder scanning is a possible future improvement.

## Change the Background Color

Use `--color` followed by a standard hexadecimal `#RRGGBB` color.

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

uses:

```text
Background: white
Text: black
```

Likewise:

```bash
python reel_recolor.py --color "#000000"
```

uses:

```text
Background: black
Text: white
```

## Combine All Options

All command-line options can be used together.

Example:

```bash
python reel_recolor.py --input "D:\My Videos" --output "D:\Finished Videos" --color "#FFFFFF" --text-color "#FF0000"
```

This means:

```text
Input folder:
D:\My Videos

Output folder:
D:\Finished Videos

Background:
White

Text:
Red
```

Every supported video directly inside the input folder will be processed using those settings.

## Default Configuration

The default settings are still available near the top of `reel_recolor.py`.

### Default Input Folder

```python
INPUT_FOLDER = "input_videos"
```

### Default Output Folder

```python
OUTPUT_FOLDER = "output_videos"
```

### Default Background Color

```python
TARGET_COLOR = "#FFFFFF"
```

### Default Text Color

```python
TEXT_COLOR = None
```

When `TEXT_COLOR` is `None`, the automatic opposite-color behavior is used.

Command-line options override these defaults for the current run.

## Output Resolution

The default output resolution is:

```python
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
```

The tool preserves the original aspect ratio and then center-crops the result to completely fill the 1080×1920 output.

It does not stretch the source video and does not add padding.

## Reference Frame

The default reference frame is taken from the beginning of the video:

```python
REFERENCE_TIME_SECONDS = 0.0
```

If your videos begin with a black frame or fade-in, try changing the source setting to:

```python
REFERENCE_TIME_SECONDS = 0.5
```

## Automatic Video Region Detection

The tool attempts to determine where the embedded movie/video area is located by analyzing one reference frame.

It uses OpenCV to examine properties such as:

* Brightness
* Saturation
* Horizontal content distribution
* Vertical content distribution
* Dark separator/border regions

The detected rectangle is treated as the dynamic portion of the template.

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

Instead of performing OpenCV operations on every frame, the program performs the expensive template analysis only once.

FFmpeg then performs the final video compositing:

```text
Static Recolored Template
            +
Moving Video Rectangle
            ↓
      Final Video
```

Video encoding is handled using NVIDIA's `h264_nvenc` encoder.

This keeps frame-by-frame video processing outside Python.

## Existing Output Detection

The tool can skip videos that have already been successfully processed.

It does not simply check whether an output filename exists.

Before skipping an output, it validates properties including:

* File existence
* Minimum file size
* Output resolution
* Output duration
* Whether the output appears truncated

This helps avoid treating broken or incomplete encodes as successfully completed videos.

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

The default runtime folders are:

```text
input_videos/
output_videos/
```

These are excluded from Git so personal videos and generated outputs are not uploaded to the repository.

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
* GitHub
* GitHub Actions

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

The movie-region detector uses image-processing heuristics rather than a machine-learning model.

Unusual layouts may therefore require adjustments to the detection thresholds.

### No Recursive Folder Scanning Yet

The selected input folder is batch-processed, but nested subfolders are not currently searched automatically.

## Future Improvements

Possible improvements include:

* Recursive subfolder processing with a `--recursive` option
* CPU encoding fallback using `libx264`
* Automatic GPU/CPU encoder selection
* Command-line reference-frame selection
* Configurable output resolution
* Multi-frame sampling for more reliable region detection
* Better handling of grayscale content
* Performance benchmarks
* More configurable detection thresholds
* Automated tests beyond syntax checking
* Packaging the tool for easier installation

## License

This project is available under the MIT License.

See the `LICENSE` file for details.

## Project Status

This project started as a personal automation tool for a workflow I use myself.

It is functional for that workflow and is being gradually cleaned up and improved as a reusable open-source project.
