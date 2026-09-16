import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

from preview import render_preview_frame

import reel_recolor as rr


SCRIPT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SETTINGS_PATH = os.path.join(
    SCRIPT_DIR,
    "gui_settings.json"
)

SUPPORTED_VIDEO_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
)

PREVIEW_DISPLAY_SIZE = (
    338,
    600,
)

DEBOUNCE_MS = 300

LOGO_MODE_NONE = "None"
LOGO_MODE_FILE = "Logo File"
LOGO_MODE_GENERATED = "Generated"

DEFAULT_SETTINGS = {
    "input_folder": os.path.join(SCRIPT_DIR, "input_videos"),
    "output_folder": os.path.join(SCRIPT_DIR, "output_videos"),
    "encoder": "auto",
    "bg_color": "#FFFFFF",
    "text_color_auto": True,
    "text_color": "#000000",
    "logo_mode": LOGO_MODE_NONE,
    "logo_file": "",
    "avatar_file": "",
    "display_name": "",
    "username": "",
    "verified": True,
    "logo_gap": 40,
    "logo_scale": 0.75,
}


def rgb_to_hex(rgb):

    return "#{:02X}{:02X}{:02X}".format(
        *rgb
    )


class App(ctk.CTk):

    def __init__(self):

        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(
            "Reel Template Recolor"
        )

        self.geometry("1260x860")
        self.minsize(1080, 720)

        self.preview_generation = 0
        self.debounce_job = None
        self.folder_scan_job = None

        self.batch_process = None
        self.batch_thread = None

        self.preview_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.batch_status_queue = queue.Queue()

        self.settings = self._load_settings()

        self._build_layout()
        self._apply_loaded_settings()

        self.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
        )

        self.after(
            200,
            self._on_input_folder_changed,
        )

        self.after(
            80,
            self._poll_queues,
        )


    # ============================================================
    # SETTINGS PERSISTENCE
    # ============================================================

    def _load_settings(self):

        settings = dict(
            DEFAULT_SETTINGS
        )

        try:

            if os.path.isfile(
                SETTINGS_PATH
            ):

                with open(
                    SETTINGS_PATH,
                    "r",
                    encoding="utf-8",
                ) as handle:

                    saved = json.load(
                        handle
                    )

                settings.update(
                    saved
                )

        except Exception:

            pass

        return settings


    def _save_settings(self):

        current = {
            "input_folder": self.input_var.get(),
            "output_folder": self.output_var.get(),
            "encoder": self.encoder_var.get(),
            "bg_color": self.bg_color_hex,
            "text_color_auto": bool(
                self.text_color_auto_var.get()
            ),
            "text_color": self.text_color_hex,
            "logo_mode": self.logo_mode_var.get(),
            "logo_file": self.logo_file_var.get(),
            "avatar_file": self.avatar_file_var.get(),
            "display_name": self.display_name_var.get(),
            "username": self.username_var.get(),
            "verified": bool(
                self.verified_var.get()
            ),
            "logo_gap": int(
                self.logo_gap_var.get()
            ),
            "logo_scale": round(
                self.logo_scale_var.get(),
                3,
            ),
        }

        try:

            with open(
                SETTINGS_PATH,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    current,
                    handle,
                    indent=2,
                )

        except Exception:

            pass


    # ============================================================
    # LAYOUT
    # ============================================================

    def _build_layout(self):

        self.grid_columnconfigure(
            0,
            weight=0,
        )

        self.grid_columnconfigure(
            1,
            weight=1,
        )

        self.grid_rowconfigure(
            0,
            weight=1,
        )

        self.grid_rowconfigure(
            1,
            weight=0,
        )

        self._build_preview_panel()
        self._build_controls_panel()
        self._build_bottom_panel()


    def _build_preview_panel(self):

        frame = ctk.CTkFrame(
            self
        )

        frame.grid(
            row=0,
            column=0,
            padx=(16, 8),
            pady=(16, 8),
            sticky="nsew",
        )

        ctk.CTkLabel(
            frame,
            text="Preview",
            font=ctk.CTkFont(
                size=18,
                weight="bold",
            ),
        ).pack(
            pady=(14, 8)
        )

        image_container = ctk.CTkFrame(
            frame,
            width=PREVIEW_DISPLAY_SIZE[0] + 16,
            height=PREVIEW_DISPLAY_SIZE[1] + 16,
            fg_color=("gray85", "gray17"),
        )

        image_container.pack(
            padx=14,
            pady=4,
        )

        image_container.pack_propagate(
            False
        )

        # A plain tk.Label + ImageTk.PhotoImage instead of
        # CTkImage/CTkLabel: CTkImage's internal image handling
        # is not reliable across repeated swaps on every Python
        # version (observed "image ... does not exist" errors on
        # Python 3.14), whereas this combination is a
        # long-standing stable Tkinter pattern.
        self.preview_image_label = tk.Label(
            image_container,
            text="Pick an input folder\nto see a preview",
            font=("Segoe UI", 11),
            bg="#242424",
            fg="white",
            wraplength=PREVIEW_DISPLAY_SIZE[0],
            justify="center",
        )

        self.preview_image_label.pack(
            expand=True
        )

        self.current_photo_image = None

        self.preview_video_menu = ctk.CTkOptionMenu(
            frame,
            values=["(no videos found)"],
            command=lambda _choice: self._request_preview_update(),
        )

        self.preview_video_menu.pack(
            padx=14,
            pady=(10, 4),
            fill="x",
        )

        self.preview_status_label = ctk.CTkLabel(
            frame,
            text="",
            wraplength=310,
            justify="left",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )

        self.preview_status_label.pack(
            padx=14,
            pady=(4, 10),
            fill="x",
        )

        ctk.CTkButton(
            frame,
            text="Refresh Preview",
            command=self._request_preview_update,
        ).pack(
            padx=14,
            pady=(0, 16),
            fill="x",
        )


    def _build_controls_panel(self):

        outer = ctk.CTkFrame(
            self
        )

        outer.grid(
            row=0,
            column=1,
            padx=(8, 16),
            pady=(16, 8),
            sticky="nsew",
        )

        outer.grid_rowconfigure(
            0,
            weight=1,
        )

        outer.grid_columnconfigure(
            0,
            weight=1,
        )

        scroll = ctk.CTkScrollableFrame(
            outer,
            label_text="Settings",
        )

        scroll.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=4,
            pady=4,
        )

        scroll.grid_columnconfigure(
            0,
            weight=1,
        )

        self._build_folders_section(
            scroll
        )

        self._build_color_section(
            scroll
        )

        self._build_encoder_section(
            scroll
        )

        self._build_logo_section(
            scroll
        )


    def _section_label(self, parent, text):

        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(
                size=15,
                weight="bold",
            ),
        ).pack(
            anchor="w",
            padx=6,
            pady=(16, 4),
        )


    def _build_folders_section(self, parent):

        self._section_label(
            parent,
            "Folders",
        )

        self.input_var = tk.StringVar()

        self.input_var.trace_add(
            "write",
            lambda *_args: self._request_folder_scan(),
        )

        self._path_row(
            parent,
            "Input folder",
            self.input_var,
            self._browse_input,
        )

        self.output_var = tk.StringVar()

        self._path_row(
            parent,
            "Output folder",
            self.output_var,
            self._browse_output,
        )


    def _path_row(self, parent, label, var, browse_command):

        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        row = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        row.pack(
            fill="x",
            padx=6,
            pady=(2, 6),
        )

        row.grid_columnconfigure(
            0,
            weight=1,
        )

        entry = ctk.CTkEntry(
            row,
            textvariable=var,
        )

        entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        ctk.CTkButton(
            row,
            text="Browse",
            width=80,
            command=browse_command,
        ).grid(
            row=0,
            column=1,
        )

        return entry


    def _build_color_section(self, parent):

        self._section_label(
            parent,
            "Colors",
        )

        self.bg_color_hex = "#FFFFFF"
        self.text_color_hex = "#000000"

        ctk.CTkLabel(
            parent,
            text="Background",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        self.bg_color_var = tk.StringVar(
            value=self.bg_color_hex
        )

        self.bg_color_swatch = self._color_row(
            parent,
            self.bg_color_var,
            self._on_bg_hex_committed,
            self._pick_bg_color,
        )

        self.text_color_auto_var = tk.BooleanVar(
            value=True
        )

        ctk.CTkCheckBox(
            parent,
            text="Auto text color (opposite of background)",
            variable=self.text_color_auto_var,
            command=self._on_text_color_auto_toggle,
        ).pack(
            anchor="w",
            padx=6,
            pady=(10, 2),
        )

        ctk.CTkLabel(
            parent,
            text="Text",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        self.text_color_var = tk.StringVar(
            value=self.text_color_hex
        )

        self.text_color_entry, self.text_color_swatch = (
            self._color_row(
                parent,
                self.text_color_var,
                self._on_text_hex_committed,
                self._pick_text_color,
                return_entry=True,
            )
        )

        self.text_color_entry.configure(
            state="disabled"
        )

        self.text_color_swatch.configure(
            state="disabled"
        )


    def _color_row(
        self,
        parent,
        var,
        on_commit,
        on_pick_color,
        return_entry=False,
    ):

        row = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        row.pack(
            fill="x",
            padx=6,
            pady=(2, 6),
        )

        row.grid_columnconfigure(
            0,
            weight=1,
        )

        entry = ctk.CTkEntry(
            row,
            textvariable=var,
            placeholder_text="#RRGGBB",
        )

        entry.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        entry.bind(
            "<Return>",
            lambda _event: on_commit(),
        )

        entry.bind(
            "<FocusOut>",
            lambda _event: on_commit(),
        )

        swatch = ctk.CTkButton(
            row,
            text="",
            width=36,
            fg_color=var.get(),
            hover=False,
            command=on_pick_color,
        )

        swatch.grid(
            row=0,
            column=1,
        )

        if return_entry:

            return entry, swatch

        return swatch


    def _normalize_hex_color(self, value):

        value = value.strip()

        if not value.startswith("#"):

            value = "#" + value

        if len(value) != 7:

            return None

        try:

            int(
                value[1:],
                16,
            )

        except ValueError:

            return None

        return value.upper()


    def _on_bg_hex_committed(self):

        normalized = self._normalize_hex_color(
            self.bg_color_var.get()
        )

        if normalized is None:

            self.bg_color_var.set(
                self.bg_color_hex
            )

            return

        self.bg_color_hex = normalized

        self.bg_color_var.set(
            normalized
        )

        self.bg_color_swatch.configure(
            fg_color=normalized
        )

        self._request_preview_update()


    def _on_text_hex_committed(self):

        normalized = self._normalize_hex_color(
            self.text_color_var.get()
        )

        if normalized is None:

            self.text_color_var.set(
                self.text_color_hex
            )

            return

        self.text_color_hex = normalized

        self.text_color_var.set(
            normalized
        )

        self.text_color_swatch.configure(
            fg_color=normalized
        )

        self._request_preview_update()


    def _build_encoder_section(self, parent):

        self._section_label(
            parent,
            "Encoder",
        )

        self.encoder_var = tk.StringVar(
            value="auto"
        )

        ctk.CTkOptionMenu(
            parent,
            values=["auto", "nvenc", "cpu"],
            variable=self.encoder_var,
        ).pack(
            anchor="w",
            padx=6,
            pady=(2, 6),
        )


    def _build_logo_section(self, parent):

        self._section_label(
            parent,
            "Logo",
        )

        self.logo_mode_var = tk.StringVar(
            value=LOGO_MODE_NONE
        )

        ctk.CTkSegmentedButton(
            parent,
            values=[
                LOGO_MODE_NONE,
                LOGO_MODE_FILE,
                LOGO_MODE_GENERATED,
            ],
            variable=self.logo_mode_var,
            command=self._on_logo_mode_change,
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 10),
        )

        self.logo_file_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        self.logo_file_var = tk.StringVar()

        self._path_row(
            self.logo_file_frame,
            "Logo image",
            self.logo_file_var,
            self._browse_logo_file,
        )

        self.logo_generated_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        self.avatar_file_var = tk.StringVar()

        self._path_row(
            self.logo_generated_frame,
            "Avatar image",
            self.avatar_file_var,
            self._browse_avatar_file,
        )

        self.display_name_var = tk.StringVar()

        ctk.CTkLabel(
            self.logo_generated_frame,
            text="Display name",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        ctk.CTkEntry(
            self.logo_generated_frame,
            textvariable=self.display_name_var,
            placeholder_text="e.g. QasimRao",
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 6),
        )

        self.username_var = tk.StringVar()

        ctk.CTkLabel(
            self.logo_generated_frame,
            text="Username",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        ctk.CTkEntry(
            self.logo_generated_frame,
            textvariable=self.username_var,
            placeholder_text="e.g. Quziii",
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 6),
        )

        self.verified_var = tk.BooleanVar(
            value=True
        )

        ctk.CTkCheckBox(
            self.logo_generated_frame,
            text="Verified checkmark",
            variable=self.verified_var,
        ).pack(
            anchor="w",
            padx=6,
            pady=(2, 6),
        )

        self.logo_shared_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        self.logo_gap_var = tk.IntVar(
            value=40
        )

        self._slider_row(
            self.logo_shared_frame,
            "Logo gap (px)",
            self.logo_gap_var,
            0,
            150,
            150,
            is_int=True,
        )

        self.logo_scale_var = tk.DoubleVar(
            value=0.75
        )

        self._slider_row(
            self.logo_shared_frame,
            "Logo scale",
            self.logo_scale_var,
            0.1,
            1.5,
            140,
            is_int=False,
        )

        # Sub-frames are shown/hidden by _on_logo_mode_change.


    def _slider_row(
        self,
        parent,
        label,
        var,
        from_,
        to,
        steps,
        is_int,
    ):

        header = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        header.pack(
            fill="x",
            padx=6,
        )

        ctk.CTkLabel(
            header,
            text=label,
            font=ctk.CTkFont(size=12),
        ).pack(
            side="left",
        )

        value_label = ctk.CTkLabel(
            header,
            text=self._format_slider_value(
                var.get(),
                is_int,
            ),
            font=ctk.CTkFont(size=12),
        )

        value_label.pack(
            side="right",
        )

        def on_move(value):

            if is_int:

                var.set(
                    int(round(value))
                )

            else:

                var.set(
                    round(value, 3)
                )

            value_label.configure(
                text=self._format_slider_value(
                    var.get(),
                    is_int,
                )
            )

            self._request_preview_update()

        ctk.CTkSlider(
            parent,
            from_=from_,
            to=to,
            number_of_steps=steps,
            command=on_move,
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 10),
        )


    def _format_slider_value(self, value, is_int):

        if is_int:

            return str(
                int(value)
            )

        return f"{value:.2f}"


    def _build_bottom_panel(self):

        frame = ctk.CTkFrame(
            self
        )

        frame.grid(
            row=1,
            column=0,
            columnspan=2,
            padx=16,
            pady=(8, 16),
            sticky="nsew",
        )

        frame.grid_columnconfigure(
            0,
            weight=1,
        )

        button_row = ctk.CTkFrame(
            frame,
            fg_color="transparent",
        )

        button_row.pack(
            fill="x",
            padx=10,
            pady=(10, 4),
        )

        self.start_button = ctk.CTkButton(
            button_row,
            text="Start Batch Processing",
            command=self._start_batch,
        )

        self.start_button.pack(
            side="left",
        )

        self.stop_button = ctk.CTkButton(
            button_row,
            text="Stop",
            state="disabled",
            fg_color="#8B2E2E",
            hover_color="#6E2323",
            command=self._stop_batch,
        )

        self.stop_button.pack(
            side="left",
            padx=(8, 0),
        )

        self.progress_label = ctk.CTkLabel(
            button_row,
            text="Idle",
        )

        self.progress_label.pack(
            side="right",
        )

        self.log_textbox = ctk.CTkTextbox(
            frame,
            height=160,
            state="disabled",
        )

        self.log_textbox.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(4, 10),
        )


    # ============================================================
    # APPLY LOADED SETTINGS
    # ============================================================

    def _apply_loaded_settings(self):

        s = self.settings

        self.input_var.set(
            s.get("input_folder", "")
        )

        self.output_var.set(
            s.get("output_folder", "")
        )

        self.encoder_var.set(
            s.get("encoder", "auto")
        )

        self.bg_color_hex = s.get(
            "bg_color",
            "#FFFFFF",
        )

        self.bg_color_var.set(
            self.bg_color_hex
        )

        self.bg_color_swatch.configure(
            fg_color=self.bg_color_hex
        )

        self.text_color_hex = s.get(
            "text_color",
            "#000000",
        )

        self.text_color_var.set(
            self.text_color_hex
        )

        self.text_color_swatch.configure(
            fg_color=self.text_color_hex
        )

        self.text_color_auto_var.set(
            s.get("text_color_auto", True)
        )

        auto_state = (
            "disabled"
            if self.text_color_auto_var.get()
            else "normal"
        )

        self.text_color_swatch.configure(
            state=auto_state
        )

        self.text_color_entry.configure(
            state=auto_state
        )

        self.logo_file_var.set(
            s.get("logo_file", "")
        )

        self.avatar_file_var.set(
            s.get("avatar_file", "")
        )

        self.display_name_var.set(
            s.get("display_name", "")
        )

        self.username_var.set(
            s.get("username", "")
        )

        self.verified_var.set(
            s.get("verified", True)
        )

        self.logo_gap_var.set(
            s.get("logo_gap", 40)
        )

        self.logo_scale_var.set(
            s.get("logo_scale", 0.75)
        )

        self.logo_mode_var.set(
            s.get("logo_mode", LOGO_MODE_NONE)
        )

        self._on_logo_mode_change(
            self.logo_mode_var.get()
        )


    # ============================================================
    # BROWSE HANDLERS
    # ============================================================

    def _browse_input(self):

        chosen = filedialog.askdirectory(
            title="Choose input folder"
        )

        if chosen:

            # Setting the var fires the trace on input_var,
            # which schedules a folder scan on its own.
            self.input_var.set(
                chosen
            )


    def _browse_output(self):

        chosen = filedialog.askdirectory(
            title="Choose output folder"
        )

        if chosen:

            self.output_var.set(
                chosen
            )


    def _browse_logo_file(self):

        chosen = filedialog.askopenfilename(
            title="Choose logo image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )

        if chosen:

            self.logo_file_var.set(
                chosen
            )

            self._request_preview_update()


    def _browse_avatar_file(self):

        chosen = filedialog.askopenfilename(
            title="Choose avatar image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All files", "*.*"),
            ],
        )

        if chosen:

            self.avatar_file_var.set(
                chosen
            )

            self._request_preview_update()


    # ============================================================
    # COLOR PICKERS
    # ============================================================

    def _pick_bg_color(self):

        _, hex_value = colorchooser.askcolor(
            title="Background color",
            initialcolor=self.bg_color_hex,
        )

        if hex_value:

            self.bg_color_hex = hex_value.upper()

            self.bg_color_var.set(
                self.bg_color_hex
            )

            self.bg_color_swatch.configure(
                fg_color=self.bg_color_hex
            )

            self._request_preview_update()


    def _pick_text_color(self):

        _, hex_value = colorchooser.askcolor(
            title="Text color",
            initialcolor=self.text_color_hex,
        )

        if hex_value:

            self.text_color_hex = hex_value.upper()

            self.text_color_var.set(
                self.text_color_hex
            )

            self.text_color_swatch.configure(
                fg_color=self.text_color_hex
            )

            self._request_preview_update()


    def _on_text_color_auto_toggle(self):

        auto = self.text_color_auto_var.get()

        state = "disabled" if auto else "normal"

        self.text_color_swatch.configure(
            state=state
        )

        self.text_color_entry.configure(
            state=state
        )

        self._request_preview_update()


    # ============================================================
    # LOGO MODE
    # ============================================================

    def _on_logo_mode_change(self, choice):

        self.logo_file_frame.pack_forget()
        self.logo_generated_frame.pack_forget()
        self.logo_shared_frame.pack_forget()

        if choice == LOGO_MODE_FILE:

            self.logo_file_frame.pack(
                fill="x"
            )

            self.logo_shared_frame.pack(
                fill="x"
            )

        elif choice == LOGO_MODE_GENERATED:

            self.logo_generated_frame.pack(
                fill="x"
            )

            self.logo_shared_frame.pack(
                fill="x"
            )

        self._request_preview_update()


    # ============================================================
    # VIDEO LIST
    # ============================================================

    def _request_folder_scan(self):

        # Debounced so pasting/typing a path doesn't rescan the
        # folder (and hit ffprobe/ffmpeg for the preview) on every
        # single keystroke.

        if self.folder_scan_job is not None:

            self.after_cancel(
                self.folder_scan_job
            )

        self.folder_scan_job = self.after(
            DEBOUNCE_MS,
            self._on_input_folder_changed,
        )


    def _on_input_folder_changed(self):

        self.folder_scan_job = None

        folder = self.input_var.get()

        videos = []

        try:

            if os.path.isdir(
                folder
            ):

                for name in sorted(
                    os.listdir(
                        folder
                    )
                ):

                    if name.lower().endswith(
                        SUPPORTED_VIDEO_EXTENSIONS
                    ):

                        videos.append(
                            name
                        )

        except Exception:

            videos = []

        if videos:

            self.preview_video_menu.configure(
                values=videos
            )

            self.preview_video_menu.set(
                videos[0]
            )

        else:

            self.preview_video_menu.configure(
                values=["(no videos found)"]
            )

            self.preview_video_menu.set(
                "(no videos found)"
            )

        self._request_preview_update()


    # ============================================================
    # PREVIEW RENDERING
    # ============================================================

    def _request_preview_update(self):

        if self.debounce_job is not None:

            self.after_cancel(
                self.debounce_job
            )

        self.debounce_job = self.after(
            DEBOUNCE_MS,
            self._render_preview_async,
        )


    def _render_preview_async(self):

        self.debounce_job = None

        video_name = self.preview_video_menu.get()

        folder = self.input_var.get()

        if (
            not video_name

            or video_name == "(no videos found)"

            or not os.path.isdir(folder)
        ):

            self.preview_status_label.configure(
                text="No video available to preview."
            )

            return

        video_path = os.path.join(
            folder,
            video_name,
        )

        logo_mode_choice = self.logo_mode_var.get()

        logo_mode = {
            LOGO_MODE_NONE: "none",
            LOGO_MODE_FILE: "file",
            LOGO_MODE_GENERATED: "generated",
        }.get(
            logo_mode_choice,
            "none",
        )

        params = dict(
            video_path=video_path,
            target_color_hex=self.bg_color_hex,
            text_color_hex=(
                None
                if self.text_color_auto_var.get()
                else self.text_color_hex
            ),
            logo_mode=logo_mode,
            logo_path=(
                self.logo_file_var.get()
                if logo_mode == "file"
                else self.avatar_file_var.get()
            ),
            display_name=self.display_name_var.get() or None,
            username=self.username_var.get() or None,
            verified=self.verified_var.get(),
            logo_gap_px=int(
                self.logo_gap_var.get()
            ),
            logo_scale=(
                self.logo_scale_var.get()
                if logo_mode != "none"
                else None
            ),
        )

        self.preview_generation += 1

        generation = self.preview_generation

        self.preview_status_label.configure(
            text="Rendering preview..."
        )

        thread = threading.Thread(
            target=self._render_preview_worker,
            args=(
                params,
                generation,
            ),
            daemon=True,
        )

        thread.start()


    def _render_preview_worker(self, params, generation):

        try:

            result = render_preview_frame(
                **params
            )

            self.preview_queue.put(
                (
                    generation,
                    "ok",
                    result,
                )
            )

        except Exception as exc:

            self.preview_queue.put(
                (
                    generation,
                    "error",
                    str(exc),
                )
            )


    def _apply_preview_result(self, result):

        image = result["image"].copy()

        image.thumbnail(
            PREVIEW_DISPLAY_SIZE,
            Image.Resampling.LANCZOS,
        )

        photo_image = ImageTk.PhotoImage(
            image
        )

        # Keep a strong reference for as long as it's displayed -
        # Tkinter doesn't retain one on its own, and if this were
        # only a local variable it would get garbage collected
        # right after this call, leaving a blank/broken image.
        self.current_photo_image = photo_image

        self.preview_image_label.configure(
            image=photo_image,
            text="",
        )

        x, y, w, h = result["movie_rect"]

        status_lines = [
            f"Detected frame: x={x}, y={y}, "
            f"width={w}, height={h}",

            f"Detection method: "
            f"{result['detection_method']}",
        ]

        if result["logo_info"]:

            li = result["logo_info"]

            status_lines.append(
                f"Logo: x={li['x']}, y={li['y']}, "
                f"width={li['width']}, height={li['height']}"
            )

        self.preview_status_label.configure(
            text="\n".join(status_lines)
        )


    # ============================================================
    # QUEUE POLLING
    # ============================================================

    def _poll_queues(self):

        try:

            while True:

                generation, status, payload = self.preview_queue.get_nowait()

                if generation == self.preview_generation:

                    if status == "ok":

                        self._apply_preview_result(
                            payload
                        )

                    else:

                        self.current_photo_image = None

                        self.preview_image_label.configure(
                            image="",
                            text="Preview unavailable",
                        )

                        self.preview_status_label.configure(
                            text=f"Error: {payload}"
                        )

        except queue.Empty:

            pass

        try:

            while True:

                line = self.log_queue.get_nowait()

                self._append_log(
                    line
                )

        except queue.Empty:

            pass

        try:

            while True:

                self.batch_status_queue.get_nowait()

                self._on_batch_finished()

        except queue.Empty:

            pass

        self.after(
            80,
            self._poll_queues,
        )


    # ============================================================
    # BATCH PROCESSING
    # ============================================================

    def _build_cli_args(self):

        args = [
            sys.executable,
            os.path.join(
                SCRIPT_DIR,
                "reel_recolor.py",
            ),
            "--input",
            self.input_var.get(),
            "--output",
            self.output_var.get(),
            "--encoder",
            self.encoder_var.get(),
            "--color",
            self.bg_color_hex,
        ]

        if not self.text_color_auto_var.get():

            args += [
                "--text-color",
                self.text_color_hex,
            ]

        logo_mode = self.logo_mode_var.get()

        if logo_mode == LOGO_MODE_FILE:

            args += [
                "--logo",
                self.logo_file_var.get(),
                "--logo-gap",
                str(int(self.logo_gap_var.get())),
                "--logo-scale",
                f"{self.logo_scale_var.get():.3f}",
            ]

        elif logo_mode == LOGO_MODE_GENERATED:

            args += [
                "--avatar",
                self.avatar_file_var.get(),
                "--display-name",
                self.display_name_var.get(),
                "--logo-gap",
                str(int(self.logo_gap_var.get())),
                "--logo-scale",
                f"{self.logo_scale_var.get():.3f}",
            ]

            if self.username_var.get():

                args += [
                    "--username",
                    self.username_var.get(),
                ]

            args += [
                "--verified"
                if self.verified_var.get()
                else "--no-verified"
            ]

        return args


    def _start_batch(self):

        if self.batch_process is not None:

            return

        self._save_settings()

        args = self._build_cli_args()

        self.log_textbox.configure(
            state="normal"
        )

        self.log_textbox.delete(
            "1.0",
            "end",
        )

        self.log_textbox.configure(
            state="disabled"
        )

        self.start_button.configure(
            state="disabled"
        )

        self.stop_button.configure(
            state="normal"
        )

        self.progress_label.configure(
            text="Running..."
        )

        self.batch_thread = threading.Thread(
            target=self._run_batch_worker,
            args=(args,),
            daemon=True,
        )

        self.batch_thread.start()


    def _run_batch_worker(self, args):

        try:

            self.batch_process = subprocess.Popen(
                args,
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in self.batch_process.stdout:

                self.log_queue.put(
                    line.rstrip("\n")
                )

            self.batch_process.wait()

            exit_code = self.batch_process.returncode

            self.log_queue.put(
                f"--- finished (exit code {exit_code}) ---"
            )

        except Exception as exc:

            self.log_queue.put(
                f"--- failed to launch: {exc} ---"
            )

        finally:

            self.batch_process = None

            # Tkinter's .after() must only be called from the main
            # thread; scheduling it here (from this worker thread)
            # is what was freezing the GUI. Signal completion
            # through the same thread-safe queue mechanism as
            # everything else instead, and let _poll_queues (which
            # already runs on the main thread) act on it.
            self.batch_status_queue.put(
                "finished"
            )


    def _on_batch_finished(self):

        self.start_button.configure(
            state="normal"
        )

        self.stop_button.configure(
            state="disabled"
        )

        self.progress_label.configure(
            text="Idle"
        )


    def _stop_batch(self):

        if self.batch_process is not None:

            try:

                self.batch_process.terminate()

            except Exception:

                pass

            self.progress_label.configure(
                text="Stopping..."
            )


    def _append_log(self, line):

        self.log_textbox.configure(
            state="normal"
        )

        self.log_textbox.insert(
            "end",
            line + "\n",
        )

        self.log_textbox.see(
            "end"
        )

        self.log_textbox.configure(
            state="disabled"
        )

        if line.startswith("Processing:"):

            self.progress_label.configure(
                text=line
            )


    # ============================================================
    # CLOSE
    # ============================================================

    def _on_close(self):

        self._save_settings()

        self._stop_batch()

        self.destroy()


if __name__ == "__main__":

    app = App()

    app.mainloop()
