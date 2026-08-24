# Reel Template Recolor

A Python/OpenCV/FFmpeg tool I built to automate recoloring vertical video templates.

The tool analyzes a reference frame, automatically detects the embedded movie/video region, recolors the surrounding static design, preserves colorful elements such as emojis, and then uses FFmpeg with NVIDIA NVENC to produce the final video.

## Why I built this

I created this for a video-processing workflow I personally use. Processing every frame in Python would be unnecessarily expensive because most of the template stays static.

Instead, the program analyzes one reference frame, creates a static recolored template, and lets FFmpeg overlay only the moving video region.

## Features

- Outputs 1080x1920 vertical video
- Preserves source aspect ratio
- Automatic movie/TV region detection
- Custom background colors
- Automatic contrasting text color
- Preserves colorful elements and emojis
- Batch video processing
- Resume/skip completed outputs
- NVIDIA NVENC GPU encoding
- FFmpeg-based video compositing

## Requirements

- Python
- NumPy
- OpenCV
- FFmpeg
- NVIDIA GPU
- FFmpeg build with h264_nvenc support

## Usage

Place videos inside:

input_videos/

Run:

python reel_recolor.py

Completed videos will be written to:

output_videos/

## Current limitations

The tool assumes that most of the design surrounding the embedded video is static. Detection is based on one reference frame, so videos with changing layouts or animated elements outside the detected movie region may not work correctly.

## Project status

This started as a personal automation tool and is still being improved.