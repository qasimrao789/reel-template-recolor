import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from preview import render_preview_frame

import reel_recolor as rr
import logo_positions


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

# Tweet (avatar/name/handle block) and Logo (a supplied image
# file) are two entirely independent, separately-toggleable
# features - not modes of one shared selector. Both can be
# enabled on the same video at once.

POSITION_MODE_AUTO = "Auto"
POSITION_MODE_FIXED = "Same spot for all"
POSITION_MODE_PER_REEL = "Per-reel"

# Max size of the click-to-place window's canvas; the 1080x1920
# reference frame is scaled down to fit within this.
CLICK_WINDOW_MAX_SIZE = (
    480,
    854,
)

DEFAULT_SETTINGS = {
    "input_folder": os.path.join(SCRIPT_DIR, "input_videos"),
    "output_folder": os.path.join(SCRIPT_DIR, "output_videos"),
    "encoder": "auto",
    "bg_color": "#FFFFFF",
    "text_color_auto": True,
    "text_color": "#000000",

    "tweet_enabled": False,
    "avatar_file": "",
    "display_name": "",
    "username": "",
    "verified": True,
    "tweet_gap": 40,
    "tweet_scale": 0.75,

    "logo_enabled": False,
    "logo_file": "",
    "logo_gap": 40,
    "logo_scale": 1.0,
    "logo_position_mode": POSITION_MODE_AUTO,
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

            "tweet_enabled": bool(
                self.tweet_enabled_var.get()
            ),
            "avatar_file": self.avatar_file_var.get(),
            "display_name": self.display_name_var.get(),
            "username": self.username_var.get(),
            "verified": bool(
                self.verified_var.get()
            ),
            "tweet_gap": int(
                self.tweet_gap_var.get()
            ),
            "tweet_scale": round(
                self.tweet_scale_var.get(),
                3,
            ),

            "logo_enabled": bool(
                self.logo_enabled_var.get()
            ),
            "logo_file": self.logo_file_var.get(),
            "logo_gap": int(
                self.logo_gap_var.get()
            ),
            "logo_scale": round(
                self.logo_scale_var.get(),
                3,
            ),
            "logo_position_mode": self.logo_position_mode_var.get(),
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
        self.preview_manual_position_note = ""

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

        self._build_tweet_section(
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


    def _build_tweet_section(self, parent):

        # Independent feature: the avatar/name/handle block. Not a
        # mode of Logo - both can be enabled at once.

        self._section_label(
            parent,
            "Tweet",
        )

        self.tweet_enabled_var = tk.BooleanVar(
            value=False
        )

        ctk.CTkCheckBox(
            parent,
            text="Enable Tweet block",
            variable=self.tweet_enabled_var,
            command=self._on_tweet_enabled_change,
        ).pack(
            anchor="w",
            padx=6,
            pady=(2, 8),
        )

        self.tweet_fields_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        self.avatar_file_var = tk.StringVar()

        self._path_row(
            self.tweet_fields_frame,
            "Avatar image",
            self.avatar_file_var,
            self._browse_avatar_file,
        )

        self.display_name_var = tk.StringVar()

        ctk.CTkLabel(
            self.tweet_fields_frame,
            text="Display name",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        ctk.CTkEntry(
            self.tweet_fields_frame,
            textvariable=self.display_name_var,
            placeholder_text="e.g. QasimRao",
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 6),
        )

        self.username_var = tk.StringVar()

        ctk.CTkLabel(
            self.tweet_fields_frame,
            text="Username",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
        )

        ctk.CTkEntry(
            self.tweet_fields_frame,
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
            self.tweet_fields_frame,
            text="Verified checkmark",
            variable=self.verified_var,
        ).pack(
            anchor="w",
            padx=6,
            pady=(2, 6),
        )

        self.tweet_gap_var = tk.IntVar(
            value=40
        )

        self._slider_row(
            self.tweet_fields_frame,
            "Tweet gap (px)",
            self.tweet_gap_var,
            0,
            150,
            150,
            is_int=True,
        )

        self.tweet_scale_var = tk.DoubleVar(
            value=0.75
        )

        self._slider_row(
            self.tweet_fields_frame,
            "Tweet scale",
            self.tweet_scale_var,
            0.1,
            1.5,
            140,
            is_int=False,
        )

        # tweet_fields_frame is shown/hidden by
        # _on_tweet_enabled_change.


    def _build_logo_section(self, parent):

        # Independent feature: a supplied logo image file, with
        # its own auto or manually-clicked placement. Not a mode
        # of Tweet - both can be enabled at once.

        self._section_label(
            parent,
            "Logo",
        )

        self.logo_enabled_var = tk.BooleanVar(
            value=False
        )

        ctk.CTkCheckBox(
            parent,
            text="Enable Logo overlay",
            variable=self.logo_enabled_var,
            command=self._on_logo_enabled_change,
        ).pack(
            anchor="w",
            padx=6,
            pady=(2, 8),
        )

        self.logo_fields_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )

        self.logo_file_var = tk.StringVar()

        self._path_row(
            self.logo_fields_frame,
            "Logo image",
            self.logo_file_var,
            self._browse_logo_file,
        )

        # ------------------------------------------------------
        # Logo position: auto (gap/scale-based placement below the
        # frame) vs. manually clicked, at the logo's native size.
        # ------------------------------------------------------

        ctk.CTkLabel(
            self.logo_fields_frame,
            text="Logo position",
            font=ctk.CTkFont(size=12),
        ).pack(
            anchor="w",
            padx=6,
            pady=(6, 0),
        )

        self.logo_position_mode_var = tk.StringVar(
            value=POSITION_MODE_AUTO
        )

        ctk.CTkSegmentedButton(
            self.logo_fields_frame,
            values=[
                POSITION_MODE_AUTO,
                POSITION_MODE_FIXED,
                POSITION_MODE_PER_REEL,
            ],
            variable=self.logo_position_mode_var,
            command=self._on_logo_position_mode_change,
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 8),
        )

        self.logo_shared_frame = ctk.CTkFrame(
            self.logo_fields_frame,
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
            value=1.0
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

        self.logo_fixed_frame = ctk.CTkFrame(
            self.logo_fields_frame,
            fg_color="transparent",
        )

        ctk.CTkButton(
            self.logo_fixed_frame,
            text="Pick position...",
            command=self._open_fixed_position_picker,
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 4),
        )

        self.logo_fixed_status_label = ctk.CTkLabel(
            self.logo_fixed_frame,
            text="Not set yet",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )

        self.logo_fixed_status_label.pack(
            anchor="w",
            padx=6,
            pady=(0, 8),
        )

        self.logo_per_reel_frame = ctk.CTkFrame(
            self.logo_fields_frame,
            fg_color="transparent",
        )

        ctk.CTkButton(
            self.logo_per_reel_frame,
            text="Annotate positions...",
            command=self._open_per_reel_annotator,
        ).pack(
            fill="x",
            padx=6,
            pady=(2, 4),
        )

        self.logo_per_reel_status_label = ctk.CTkLabel(
            self.logo_per_reel_frame,
            text="0 annotated",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )

        self.logo_per_reel_status_label.pack(
            anchor="w",
            padx=6,
            pady=(0, 8),
        )

        # logo_fields_frame is shown/hidden by
        # _on_logo_enabled_change; its sub-panels (gap/scale vs.
        # fixed vs. per-reel) by _on_logo_position_mode_change.


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

        self.tweet_gap_var.set(
            s.get("tweet_gap", 40)
        )

        self.tweet_scale_var.set(
            s.get("tweet_scale", 0.75)
        )

        self.tweet_enabled_var.set(
            s.get("tweet_enabled", False)
        )

        self._on_tweet_enabled_change()

        self.logo_file_var.set(
            s.get("logo_file", "")
        )

        self.logo_gap_var.set(
            s.get("logo_gap", 40)
        )

        self.logo_scale_var.set(
            s.get("logo_scale", 1.0)
        )

        self.logo_position_mode_var.set(
            s.get("logo_position_mode", POSITION_MODE_AUTO)
        )

        self.logo_enabled_var.set(
            s.get("logo_enabled", False)
        )

        self._on_logo_enabled_change()


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

    def _on_tweet_enabled_change(self):

        self.tweet_fields_frame.pack_forget()

        if self.tweet_enabled_var.get():

            self.tweet_fields_frame.pack(
                fill="x"
            )

        self._request_preview_update()


    def _on_logo_enabled_change(self):

        self.logo_fields_frame.pack_forget()

        if self.logo_enabled_var.get():

            self.logo_fields_frame.pack(
                fill="x"
            )

            self._on_logo_position_mode_change(
                self.logo_position_mode_var.get()
            )

        self._request_preview_update()


    def _on_logo_position_mode_change(self, choice):

        self.logo_shared_frame.pack_forget()
        self.logo_fixed_frame.pack_forget()
        self.logo_per_reel_frame.pack_forget()

        if not self.logo_enabled_var.get():

            return

        if choice == POSITION_MODE_FIXED:

            self.logo_fixed_frame.pack(
                fill="x"
            )

            self._refresh_logo_position_status()

        elif choice == POSITION_MODE_PER_REEL:

            self.logo_per_reel_frame.pack(
                fill="x"
            )

            self._refresh_logo_position_status()

        else:

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


    def _list_input_videos(self):

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

        return videos


    def _on_input_folder_changed(self):

        self.folder_scan_job = None

        videos = self._list_input_videos()

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
    # MANUAL LOGO POSITIONING
    # ============================================================

    def _positions_file_path(self):

        output_folder = (
            self.output_var.get()

            or

            DEFAULT_SETTINGS["output_folder"]
        )

        return os.path.join(
            output_folder,
            "logo_positions.json",
        )


    def _refresh_logo_position_status(self):

        try:

            data = logo_positions.load_positions(
                self._positions_file_path()
            )

        except Exception:

            data = logo_positions.new_positions(
                "per_reel"
            )

        fixed = data.get(
            "fixed_position"
        )

        if data.get("mode") == "fixed" and fixed:

            self.logo_fixed_status_label.configure(
                text=f"Set: ({fixed['x']}, {fixed['y']})"
            )

        else:

            self.logo_fixed_status_label.configure(
                text="Not set yet"
            )

        total = len(
            self._list_input_videos()
        )

        annotated = len(
            data.get(
                "positions",
                {},
            )
        )

        self.logo_per_reel_status_label.configure(
            text=f"{annotated} / {total} annotated"
        )


    def _extract_raw_frame(self, video_path):

        # Deliberately the raw reference frame, not the recolored
        # template - fast (one ffmpeg call, no motion detection),
        # which matters when clicking through a large library, and
        # the click position is about layout, not final colors.

        (
            source_width,
            source_height,
            fps,
            duration
        ) = rr.probe_video(
            video_path
        )

        (
            scaled_width,
            scaled_height,
            crop_x,
            crop_y
        ) = rr.calculate_resize_crop(
            source_width,
            source_height,
        )

        preprocess_filter = rr.build_preprocess_filter(
            scaled_width,
            scaled_height,
            crop_x,
            crop_y,
        )

        frame_rgb = rr.extract_frame_at(
            video_path,
            preprocess_filter,
            rr.REFERENCE_TIME_SECONDS,
        )

        return Image.fromarray(
            frame_rgb,
            mode="RGB",
        )


    def _get_current_logo_native_size(self):

        # Logo-only: the click-to-place windows are a Logo File
        # feature, unrelated to whether Tweet is also enabled.

        try:

            path = self.logo_file_var.get()

            if path and os.path.isfile(path):

                return Image.open(path).size

        except Exception:

            pass

        return None


    def _build_click_window(self, title, frame_image):

        win = tk.Toplevel(self)

        win.title(title)

        max_w, max_h = CLICK_WINDOW_MAX_SIZE

        scale = min(
            max_w / frame_image.width,
            max_h / frame_image.height,
            1.0,
        )

        display_w = max(
            1,
            int(frame_image.width * scale),
        )

        display_h = max(
            1,
            int(frame_image.height * scale),
        )

        display_image = frame_image.resize(
            (
                display_w,
                display_h
            ),
            Image.Resampling.LANCZOS,
        )

        photo = ImageTk.PhotoImage(
            display_image
        )

        canvas = tk.Canvas(
            win,
            width=display_w,
            height=display_h,
            highlightthickness=0,
            bg="black",
        )

        canvas.pack(
            padx=10,
            pady=10,
        )

        canvas.create_image(
            0,
            0,
            anchor="nw",
            image=photo,
        )

        # Keep a strong reference on the canvas itself, or it gets
        # garbage collected and the image disappears/errors.
        canvas.image = photo

        win.content_canvas = canvas

        return (
            win,
            canvas,
            scale,
        )


    def _draw_click_marker(
        self,
        canvas,
        display_x,
        display_y,
        logo_native_size,
        scale,
    ):

        canvas.delete("marker")

        r = 7

        canvas.create_line(
            display_x - r, display_y,
            display_x + r, display_y,
            fill="#FF3B30", width=2, tags="marker",
        )

        canvas.create_line(
            display_x, display_y - r,
            display_x, display_y + r,
            fill="#FF3B30", width=2, tags="marker",
        )

        if logo_native_size:

            box_w = logo_native_size[0] * scale
            box_h = logo_native_size[1] * scale

            canvas.create_rectangle(
                display_x - box_w / 2,
                display_y - box_h / 2,
                display_x + box_w / 2,
                display_y + box_h / 2,
                outline="#34C759",
                width=2,
                dash=(5, 3),
                tags="marker",
            )


    def _open_fixed_position_picker(self):

        videos = self._list_input_videos()

        if not videos:

            messagebox.showerror(
                "No videos",
                "No videos found in the input folder.",
            )

            return

        video_path = os.path.join(
            self.input_var.get(),
            videos[0],
        )

        try:

            frame_image = self._extract_raw_frame(
                video_path
            )

        except Exception as exc:

            messagebox.showerror(
                "Error",
                f"Could not read a frame from {videos[0]}:\n{exc}",
            )

            return

        logo_native_size = self._get_current_logo_native_size()

        win, canvas, scale = self._build_click_window(
            f"Pick logo position - reference: {videos[0]}",
            frame_image,
        )

        def on_click(event):

            real_x = int(
                event.x / scale
            )

            real_y = int(
                event.y / scale
            )

            logo_positions.set_fixed_position(
                self._positions_file_path(),
                real_x,
                real_y,
            )

            self._refresh_logo_position_status()

            win.destroy()

        canvas.bind(
            "<Button-1>",
            on_click,
        )

        ctk.CTkLabel(
            win,
            text=(
                "Click anywhere on the frame to set the logo's "
                "center for every video."
            ),
            wraplength=CLICK_WINDOW_MAX_SIZE[0],
        ).pack(
            pady=(0, 10)
        )


    def _open_per_reel_annotator(self):

        videos = self._list_input_videos()

        if not videos:

            messagebox.showerror(
                "No videos",
                "No videos found in the input folder.",
            )

            return

        positions_path = self._positions_file_path()

        data = logo_positions.load_positions(
            positions_path
        )

        logo_native_size = self._get_current_logo_native_size()

        folder = self.input_var.get()

        start_index = 0

        for i, name in enumerate(videos):

            if name not in data["positions"]:

                start_index = i

                break

        state = {
            "index": start_index
        }

        win = tk.Toplevel(self)

        win.title(
            "Annotate logo positions"
        )

        info_label = ctk.CTkLabel(
            win,
            text="",
            font=ctk.CTkFont(size=13),
            wraplength=CLICK_WINDOW_MAX_SIZE[0],
        )

        info_label.pack(
            pady=(10, 4)
        )

        canvas_container = ctk.CTkFrame(
            win,
            fg_color="transparent",
        )

        canvas_container.pack(
            padx=10,
            pady=4,
        )

        canvas_state = {
            "canvas": None
        }

        def load_current():

            filename = videos[
                state["index"]
            ]

            video_path = os.path.join(
                folder,
                filename,
            )

            try:

                frame_image = self._extract_raw_frame(
                    video_path
                )

            except Exception as exc:

                messagebox.showerror(
                    "Error",
                    f"Could not read a frame from "
                    f"{filename}:\n{exc}",
                )

                return

            max_w, max_h = CLICK_WINDOW_MAX_SIZE

            scale = min(
                max_w / frame_image.width,
                max_h / frame_image.height,
                1.0,
            )

            display_w = max(
                1,
                int(frame_image.width * scale),
            )

            display_h = max(
                1,
                int(frame_image.height * scale),
            )

            display_image = frame_image.resize(
                (
                    display_w,
                    display_h
                ),
                Image.Resampling.LANCZOS,
            )

            photo = ImageTk.PhotoImage(
                display_image
            )

            if canvas_state["canvas"] is not None:

                canvas_state["canvas"].destroy()

            canvas = tk.Canvas(
                canvas_container,
                width=display_w,
                height=display_h,
                highlightthickness=0,
                bg="black",
            )

            canvas.pack()

            canvas.create_image(
                0,
                0,
                anchor="nw",
                image=photo,
            )

            canvas.image = photo

            canvas_state["canvas"] = canvas
            canvas_state["scale"] = scale

            # Unambiguous handle for the current content canvas -
            # customtkinter widgets can use internal tk.Canvas
            # instances of their own, so a tree search for "any
            # Canvas" isn't reliable.
            win.content_canvas = canvas

            existing = data["positions"].get(
                filename
            )

            marked_no_logo = bool(
                existing
            ) and existing.get(
                "skip",
                False,
            )

            if existing and not marked_no_logo:

                self._draw_click_marker(
                    canvas,
                    existing["x"] * scale,
                    existing["y"] * scale,
                    logo_native_size,
                    scale,
                )

            annotated_count = len(
                data["positions"]
            )

            if marked_no_logo:

                status_suffix = "  (marked: no logo)"

            elif existing:

                status_suffix = (
                    "  (already set - click to overwrite)"
                )

            else:

                status_suffix = ""

            info_label.configure(
                text=(
                    f"{annotated_count} / {len(videos)} annotated "
                    f"total  |  viewing {state['index'] + 1} / "
                    f"{len(videos)}: {filename}{status_suffix}"
                )
            )

            def on_click(event):

                real_x = int(
                    event.x / scale
                )

                real_y = int(
                    event.y / scale
                )

                logo_positions.set_reel_position(
                    positions_path,
                    filename,
                    real_x,
                    real_y,
                )

                data["positions"][filename] = {
                    "x": real_x,
                    "y": real_y,
                }

                self._refresh_logo_position_status()

                go_next()

            canvas.bind(
                "<Button-1>",
                on_click,
            )


        def go_next():

            if state["index"] + 1 < len(videos):

                state["index"] += 1

                load_current()

            else:

                messagebox.showinfo(
                    "Done",
                    "That's the last video in the folder.",
                )


        def go_back():

            if state["index"] > 0:

                state["index"] -= 1

                load_current()


        def mark_no_logo():

            filename = videos[
                state["index"]
            ]

            logo_positions.set_no_logo(
                positions_path,
                filename,
            )

            data["positions"][filename] = {
                "skip": True,
            }

            self._refresh_logo_position_status()

            go_next()


        nav_row = ctk.CTkFrame(
            win,
            fg_color="transparent",
        )

        nav_row.pack(
            pady=(4, 10)
        )

        ctk.CTkButton(
            nav_row,
            text="< Back",
            width=80,
            command=go_back,
        ).pack(
            side="left",
            padx=3,
        )

        ctk.CTkButton(
            nav_row,
            text="No logo >",
            width=100,
            fg_color="#8B6F2E",
            hover_color="#6E5824",
            command=mark_no_logo,
        ).pack(
            side="left",
            padx=3,
        )

        ctk.CTkButton(
            nav_row,
            text="Skip for now >",
            width=120,
            command=go_next,
        ).pack(
            side="left",
            padx=3,
        )

        ctk.CTkButton(
            nav_row,
            text="Close",
            width=80,
            command=win.destroy,
        ).pack(
            side="left",
            padx=3,
        )

        ctk.CTkLabel(
            win,
            text=(
                "Click on the frame to place the logo's center and "
                "save. \"No logo\" marks this video to be processed "
                "without one. \"Skip for now\" leaves it undecided "
                "for later. Closing at any point keeps everything "
                "decided so far; reopening resumes from the next "
                "undecided video."
            ),
            wraplength=CLICK_WINDOW_MAX_SIZE[0],
        ).pack(
            pady=(0, 10)
        )

        def on_window_close():

            self._refresh_logo_position_status()

            win.destroy()

        win.protocol(
            "WM_DELETE_WINDOW",
            on_window_close,
        )

        load_current()


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

        logo_position_mode = self.logo_position_mode_var.get()

        logo_manual_center = None

        self.preview_manual_position_note = ""

        if (

            self.logo_enabled_var.get()

            and

            logo_position_mode != POSITION_MODE_AUTO
        ):

            # Look up this exact video's saved point (if any) so
            # the live preview shows real manual placement, the
            # same way the click-to-place windows do - instead of
            # a misleading auto-computed position.
            try:

                data = logo_positions.load_positions(
                    self._positions_file_path()
                )

                logo_manual_center = logo_positions.get_position_for(
                    data,
                    video_name,
                )

            except Exception:

                logo_manual_center = None

            if logo_manual_center is None:

                self.preview_manual_position_note = (
                    "\n(No saved logo position for this video "
                    "yet - use the position picker.)"
                )

        params = dict(
            video_path=video_path,
            target_color_hex=self.bg_color_hex,
            text_color_hex=(
                None
                if self.text_color_auto_var.get()
                else self.text_color_hex
            ),
            tweet_enabled=self.tweet_enabled_var.get(),
            avatar_path=self.avatar_file_var.get() or None,
            display_name=self.display_name_var.get() or None,
            username=self.username_var.get() or None,
            verified=self.verified_var.get(),
            tweet_gap_px=int(
                self.tweet_gap_var.get()
            ),
            tweet_scale=self.tweet_scale_var.get(),
            logo_enabled=self.logo_enabled_var.get(),
            logo_path=self.logo_file_var.get() or None,
            logo_position_mode=(
                "manual"
                if logo_position_mode != POSITION_MODE_AUTO
                else "auto"
            ),
            logo_manual_center=logo_manual_center,
            logo_gap_px=int(
                self.logo_gap_var.get()
            ),
            logo_scale=self.logo_scale_var.get(),
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

        if result["tweet_info"]:

            ti = result["tweet_info"]

            status_lines.append(
                f"Tweet: x={ti['x']}, y={ti['y']}, "
                f"width={ti['width']}, height={ti['height']}"
            )

        if result["logo_info"]:

            li = result["logo_info"]

            status_lines.append(
                f"Logo: x={li['x']}, y={li['y']}, "
                f"width={li['width']}, height={li['height']}"
            )

        self.preview_status_label.configure(
            text=(
                "\n".join(status_lines)
                +
                getattr(
                    self,
                    "preview_manual_position_note",
                    "",
                )
            )
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

        # Tweet and Logo are independent - each contributes its own
        # flags based on its own enable checkbox, so both, either,
        # or neither can end up in the command.

        if self.tweet_enabled_var.get():

            args += [
                "--avatar",
                self.avatar_file_var.get(),
                "--display-name",
                self.display_name_var.get(),
            ]

            if self.username_var.get():

                args += [
                    "--username",
                    self.username_var.get(),
                ]

            args += [
                "--verified"
                if self.verified_var.get()
                else "--no-verified",
                "--tweet-gap",
                str(int(self.tweet_gap_var.get())),
                "--tweet-scale",
                f"{self.tweet_scale_var.get():.3f}",
            ]

        if self.logo_enabled_var.get():

            manual_position = (
                self.logo_position_mode_var.get()
                !=
                POSITION_MODE_AUTO
            )

            args += [
                "--logo",
                self.logo_file_var.get(),
            ]

            if manual_position:

                args += [
                    "--logo-position-mode",
                    "manual",
                    "--logo-positions-file",
                    self._positions_file_path(),
                ]

            else:

                args += [
                    "--logo-gap",
                    str(int(self.logo_gap_var.get())),
                    "--logo-scale",
                    f"{self.logo_scale_var.get():.3f}",
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
