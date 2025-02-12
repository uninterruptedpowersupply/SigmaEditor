For a preview
https://www.youtube.com/watch?v=QkPHlyc0L2U

Overview
This Python script is a GUI application designed to process video files by adding custom text overlays and dynamic image overlays, often referred to as "disco" or "MLG" effects. It leverages FFmpeg for video encoding and OpenCV and Pillow (PIL) for image and text manipulation. The application supports hardware acceleration for faster video processing if compatible hardware (like NVIDIA CUDA or Intel Quick Sync Video) is detected.

Features
Text Overlay: Adds customizable text to the video frames.
Users can specify the text content, font file, text size, and text color (RGB).
Text is centered on the video frame.
Dynamic Image Overlays ("Disco Mode"): Overlays a sequence of images from a user-specified folder onto the video.
Images appear at random positions on the video frame at a set interval.
Users can control the interval between image appearances (Disco Frame Interval), the duration each image stays on screen (Image Duration), and the size of the overlay images.
Supports PNG, JPG, and JPEG image formats with alpha transparency for PNGs.
Hardware Acceleration: Detects and utilizes hardware acceleration (CUDA or Intel QSV) if available, significantly speeding up video encoding. If no hardware acceleration is detected, software encoding (libx264) is used.
Cache Settings: Remembers the last used settings for convenience, storing them in a cache.ini file in the application directory.
User-Friendly GUI: Built with Tkinter for a simple graphical interface.

Requirements / Version Requirements (Recommended)
Before running the script, ensure you have the following installed:

Python:  Python 3.x
FFmpeg: FFmpeg in your path

For optimal compatibility, it is recommended to use the following versions of Python libraries, or later compatible versions:

opencv-python: 4.7.0.68
Pillow (PIL): 10.2.0
tkinter: (Standard Python Library - typically comes with Python installations)
configparser: (Standard Python Library - typically comes with Python installations)


