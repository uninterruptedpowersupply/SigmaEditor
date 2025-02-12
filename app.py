import tkinter as tk
from tkinter import filedialog, messagebox
import configparser
import os
import sys
import subprocess
import threading
import random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ================================
# Cache Handling
# ================================

def get_cache_file():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "cache.ini")

CACHE_FILE = get_cache_file()

def load_cache():
    cache = configparser.ConfigParser()
    if os.path.exists(CACHE_FILE):
        cache.read(CACHE_FILE)
        if 'CACHE' in cache:
            return dict(cache['CACHE'])
    return {}

def save_cache(cache_dict):
    cache = configparser.ConfigParser()
    cache['CACHE'] = cache_dict
    with open(CACHE_FILE, 'w') as configfile:
        cache.write(configfile)

# ================================
# Locate FFmpeg Executable
# ================================
def get_ffmpeg_executable():
    """
    Checks for an ffmpeg binary in the same folder as the script/EXE.
    If found, returns its absolute path; otherwise returns 'ffmpeg' (assuming it's in PATH).
    """
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    # On Windows, look for ffmpeg.exe; otherwise, look for ffmpeg
    ffmpeg_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    candidate = os.path.join(base_path, ffmpeg_name)
    if os.path.exists(candidate):
        return candidate
    else:
        return "ffmpeg"  # Fallback to system PATH

# ================================
# FFmpeg Hardware Detection
# ================================
def detect_hwaccels(ffmpeg_exec):
    try:
        output = subprocess.check_output([ffmpeg_exec, "-hide_banner", "-hwaccels"], stderr=subprocess.STDOUT)
        lines = output.decode("utf-8").splitlines()
        hwaccels = [line.strip() for line in lines[1:] if line.strip()]
        return hwaccels
    except Exception as e:
        print("Error detecting hwaccels:", e)
        return []

# ================================
# Video Processing Function
# ================================
def process_video(input_video, save_video, images_folder, font_path, custom_text, text_size,
                  text_color, disco_interval, image_duration, image_size):
    try:
        cap = cv2.VideoCapture(input_video)
        if not cap.isOpened():
            messagebox.showerror("Error", "Cannot open input video.")
            return

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Get the ffmpeg executable from our root directory (or fallback to system PATH)
        ffmpeg_exec = get_ffmpeg_executable()
        # Detect hardware acceleration options using the found ffmpeg
        hwaccels = detect_hwaccels(ffmpeg_exec)
        print("Detected hwaccels:", hwaccels)
        if any('cuda' in accel.lower() for accel in hwaccels):
            hwaccel_opts = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
            encoder_opts = ["-c:v", "h264_nvenc"]
            print("Using CUDA acceleration")
        elif any('qsv' in accel.lower() for accel in hwaccels):
            hwaccel_opts = ["-hwaccel", "qsv"]
            encoder_opts = ["-c:v", "h264_qsv"]
            print("Using Intel Quick Sync acceleration")
        else:
            hwaccel_opts = []
            encoder_opts = ["-c:v", "libx264"]
            print("No hardware acceleration detected; using software encoding")

        # Build the ffmpeg command to pipe raw frames from stdin
        ffmpeg_cmd = [
            ffmpeg_exec,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps)
        ] + hwaccel_opts + [
            "-i", "-"  # input from stdin
        ]
        ffmpeg_cmd += ["-threads", "4"] + encoder_opts + [
            "-pix_fmt", "yuv420p", save_video
        ]
        print("Running ffmpeg command:")
        print(" ".join(ffmpeg_cmd))
        process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

        # Load overlay images from images_folder and resize to (image_size x image_size)
        mlg_images = []
        for img_file in os.listdir(images_folder):
            if img_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                img_path = os.path.join(images_folder, img_file)
                img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    if img.shape[2] == 3:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                    img = cv2.resize(img, (image_size, image_size))
                    mlg_images.append(img)

        # Prepare sharpen kernel and load font
        sharpen_kernel = np.array([[-1, -1, -1],
                                   [-1,  9, -1],
                                   [-1, -1, -1]])
        try:
            font = ImageFont.truetype(font_path, text_size)
        except Exception as e:
            font = ImageFont.load_default()
            print("Could not load font, using default:", e)
        
        # Parse text_color (format "R,G,B")
        try:
            r, g, b = map(int, text_color.split(","))
            text_color_tuple = (r, g, b)
        except Exception as e:
            text_color_tuple = (255, 255, 255)
            print("Invalid text_color; defaulting to white:", e)

        frame_number = 0
        active_overlays = []
        current_image_index = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame_number += 1
            processed_frame = frame.copy()

            # Process active overlays
            for overlay in active_overlays.copy():
                if frame_number <= overlay['end_frame']:
                    x, y = overlay['position']
                    img_overlay = overlay['image']
                    alpha = img_overlay[:, :, 3] / 255.0
                    overlay_bgr = img_overlay[:, :, :3]
                    for c in range(3):
                        processed_frame[y:y+img_overlay.shape[0], x:x+img_overlay.shape[1], c] = \
                            (1 - alpha) * processed_frame[y:y+img_overlay.shape[0], x:x+img_overlay.shape[1], c] + \
                            alpha * overlay_bgr[:, :, c]
                else:
                    active_overlays.remove(overlay)

            # Add new overlay at every 'disco_interval' frames
            if frame_number % disco_interval == 0 and mlg_images:
                pos_x = random.randint(0, width - image_size)
                pos_y = random.randint(0, height - image_size)
                active_overlays.append({
                    'image': mlg_images[current_image_index % len(mlg_images)],
                    'position': (pos_x, pos_y),
                    'end_frame': frame_number + image_duration
                })
                current_image_index += 1

            # Add custom text overlay using PIL
            pil_img = Image.fromarray(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            text_bbox = draw.textbbox((0, 0), custom_text, font=font)
            text_w = text_bbox[2] - text_bbox[0]
            text_h = text_bbox[3] - text_bbox[1]
            text_position = ((width - text_w) // 2, (height - text_h) // 2)
            draw.text(text_position, custom_text, font=font, fill=text_color_tuple)
            processed_frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            # Apply sharpen filter
            processed_frame = cv2.filter2D(processed_frame, -1, sharpen_kernel)

            # Write frame data to ffmpeg stdin
            process.stdin.write(processed_frame.tobytes())

        cap.release()
        process.stdin.close()
        process.wait()
        messagebox.showinfo("Complete", f"Video processing complete!\nSaved to: {save_video}")
    except Exception as e:
        messagebox.showerror("Processing Error", f"An error occurred during processing:\n{e}")
        print("Processing error:", e)

# ================================
# GUI Setup
# ================================
def browse_font():
    file = filedialog.askopenfilename(
        title="Select Font File", 
        filetypes=[("Font Files", "*.ttf *.otf"), ("All Files", "*.*")]
    )
    if file:
        font_entry.delete(0, tk.END)
        font_entry.insert(0, os.path.abspath(file))

def browse_input_video():
    file = filedialog.askopenfilename(
        title="Select Input Video", 
        filetypes=[("Video Files", "*.mp4 *.avi *.mov *.mkv"), ("All Files", "*.*")]
    )
    if file:
        input_video_entry.delete(0, tk.END)
        input_video_entry.insert(0, os.path.abspath(file))

def browse_images_folder():
    folder = filedialog.askdirectory(title="Select Images Folder")
    if folder:
        images_folder_entry.delete(0, tk.END)
        images_folder_entry.insert(0, os.path.abspath(folder))

def browse_save_video():
    file = filedialog.asksaveasfilename(
        title="Select Save Video Path", 
        defaultextension=".mp4",
        filetypes=[("MP4 Files", "*.mp4"), ("All Files", "*.*")]
    )
    if file:
        if not file.lower().endswith(".mp4"):
            file += ".mp4"
        save_video_entry.delete(0, tk.END)
        save_video_entry.insert(0, os.path.abspath(file))

def start_processing_thread():
    # Retrieve GUI values
    font_path = font_entry.get().strip()
    custom_text = custom_text_entry.get().strip()
    text_size = text_size_entry.get().strip()
    text_color = text_color_entry.get().strip()
    input_video = input_video_entry.get().strip()
    images_folder = images_folder_entry.get().strip()
    save_video = save_video_entry.get().strip()
    disco_interval = disco_interval_entry.get().strip()
    image_duration = image_duration_entry.get().strip()
    image_size = image_size_entry.get().strip()

    if not all([font_path, custom_text, text_size, text_color, input_video, images_folder, save_video, disco_interval, image_duration, image_size]):
        messagebox.showerror("Missing Information", "Please fill in all fields.")
        return

    try:
        text_size_int = int(text_size)
        disco_interval_int = int(disco_interval)
        image_duration_int = int(image_duration)
        image_size_int = int(image_size)
    except ValueError:
        messagebox.showerror("Invalid Input", "Text size, disco frame interval, image duration, and image size must be integers.")
        return

    if not os.path.isfile(font_path):
        messagebox.showerror("File Error", f"Font file not found:\n{font_path}")
        return
    if not os.path.isfile(input_video):
        messagebox.showerror("File Error", f"Input video not found:\n{input_video}")
        return
    if not os.path.isdir(images_folder):
        messagebox.showerror("Folder Error", f"Images folder not found:\n{images_folder}")
        return
    output_dir = os.path.dirname(save_video)
    if output_dir and not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as e:
            messagebox.showerror("Output Path Error", f"Failed to create output directory:\n{output_dir}\n{e}")
            return

    cache_data = {
        "font_path": font_path,
        "custom_text": custom_text,
        "text_size": text_size,
        "text_color": text_color,
        "input_video": input_video,
        "images_folder": images_folder,
        "save_video": save_video,
        "disco_interval": disco_interval,
        "image_duration": image_duration,
        "image_size": image_size
    }
    save_cache(cache_data)

    start_btn.config(state=tk.DISABLED)
    status_label.config(text="Processing video, please wait...")

    def run():
        process_video(input_video, save_video, images_folder, font_path, custom_text,
                      text_size_int, text_color, disco_interval_int, image_duration_int, image_size_int)
        start_btn.config(state=tk.NORMAL)
        status_label.config(text="Processing complete!")
    threading.Thread(target=run).start()

# Build main window
root = tk.Tk()
root.title("Video Processing App")

cached = load_cache()

# Row 0: Font File
tk.Label(root, text="Font File:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
font_entry = tk.Entry(root, width=60)
font_entry.grid(row=0, column=1, padx=5, pady=5)
if "font_path" in cached:
    font_entry.insert(0, cached["font_path"])
tk.Button(root, text="Browse", command=browse_font).grid(row=0, column=2, padx=5, pady=5)

# Row 1: Custom Text
tk.Label(root, text="Custom Text:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
custom_text_entry = tk.Entry(root, width=60)
custom_text_entry.grid(row=1, column=1, padx=5, pady=5)
if "custom_text" in cached:
    custom_text_entry.insert(0, cached["custom_text"])
else:
    custom_text_entry.insert(0, "SAMPLE TEXT")

# Row 2: Text Size
tk.Label(root, text="Text Size:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
text_size_entry = tk.Entry(root, width=10)
text_size_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
if "text_size" in cached:
    text_size_entry.insert(0, cached["text_size"])
else:
    text_size_entry.insert(0, "100")

# Row 3: Text Color (R,G,B)
tk.Label(root, text="Text Color (R,G,B):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
text_color_entry = tk.Entry(root, width=20)
text_color_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
if "text_color" in cached:
    text_color_entry.insert(0, cached["text_color"])
else:
    text_color_entry.insert(0, "255,255,255")

# Row 4: Input Video
tk.Label(root, text="Input Video:").grid(row=4, column=0, padx=5, pady=5, sticky="e")
input_video_entry = tk.Entry(root, width=60)
input_video_entry.grid(row=4, column=1, padx=5, pady=5)
if "input_video" in cached:
    input_video_entry.insert(0, cached["input_video"])
tk.Button(root, text="Browse", command=browse_input_video).grid(row=4, column=2, padx=5, pady=5)

# Row 5: Images Folder
tk.Label(root, text="Images Folder:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
images_folder_entry = tk.Entry(root, width=60)
images_folder_entry.grid(row=5, column=1, padx=5, pady=5)
if "images_folder" in cached:
    images_folder_entry.insert(0, cached["images_folder"])
tk.Button(root, text="Browse", command=browse_images_folder).grid(row=5, column=2, padx=5, pady=5)

# Row 6: Save Video Path
tk.Label(root, text="Save Video Path:").grid(row=6, column=0, padx=5, pady=5, sticky="e")
save_video_entry = tk.Entry(root, width=60)
save_video_entry.grid(row=6, column=1, padx=5, pady=5)
if "save_video" in cached:
    save_video_entry.insert(0, cached["save_video"])
tk.Button(root, text="Browse", command=browse_save_video).grid(row=6, column=2, padx=5, pady=5)

# Row 7: Disco Frame Interval
tk.Label(root, text="Disco Frame Interval:").grid(row=7, column=0, padx=5, pady=5, sticky="e")
disco_interval_entry = tk.Entry(root, width=10)
disco_interval_entry.grid(row=7, column=1, padx=5, pady=5, sticky="w")
if "disco_interval" in cached:
    disco_interval_entry.insert(0, cached["disco_interval"])
else:
    disco_interval_entry.insert(0, "5")

# Row 8: Image Duration Frames
tk.Label(root, text="Image Duration (frames):").grid(row=8, column=0, padx=5, pady=5, sticky="e")
image_duration_entry = tk.Entry(root, width=10)
image_duration_entry.grid(row=8, column=1, padx=5, pady=5, sticky="w")
if "image_duration" in cached:
    image_duration_entry.insert(0, cached["image_duration"])
else:
    image_duration_entry.insert(0, "10")

# Row 9: Image Size (px)
tk.Label(root, text="Image Size (px):").grid(row=9, column=0, padx=5, pady=5, sticky="e")
image_size_entry = tk.Entry(root, width=10)
image_size_entry.grid(row=9, column=1, padx=5, pady=5, sticky="w")
if "image_size" in cached:
    image_size_entry.insert(0, cached["image_size"])
else:
    image_size_entry.insert(0, "100")

start_btn = tk.Button(root, text="Start Processing", command=start_processing_thread, width=20)
start_btn.grid(row=10, column=1, padx=5, pady=10)
status_label = tk.Label(root, text="")
status_label.grid(row=11, column=1, padx=5, pady=5)

root.mainloop()
