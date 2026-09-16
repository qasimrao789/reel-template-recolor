from PIL import Image

import reel_recolor as rr


def render_preview_frame(
    video_path,
    target_color_hex,
    text_color_hex,
    logo_mode,
    logo_path=None,
    display_name=None,
    username=None,
    verified=True,
    logo_gap_px=40,
    logo_scale=None,
):

    # Reuses reel_recolor.py's own pipeline functions so the
    # preview is pixel-for-pixel what one frame of the real
    # ffmpeg output would look like, with no video encoding.

    source_width, source_height, fps, duration = rr.probe_video(
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

    reference_rgb = rr.extract_frame_at(
        video_path,
        preprocess_filter,
        rr.REFERENCE_TIME_SECONDS,
    )

    motion_sample_time = (
        rr.REFERENCE_TIME_SECONDS
        +
        rr.MOTION_SAMPLE_OFFSET_SECONDS
    )

    motion_frame_rgb = None

    if (
        duration <= 0

        or

        motion_sample_time < duration - 0.05
    ):

        try:

            motion_frame_rgb = rr.extract_frame_at(
                video_path,
                preprocess_filter,
                motion_sample_time,
            )

        except Exception:

            motion_frame_rgb = None

    (
        x,
        y,
        picture_width,
        picture_height,
        detection_method
    ) = rr.detect_picture_area(
        reference_rgb,
        motion_frame_rgb,
    )

    background_rgb = rr.hex_to_rgb(
        target_color_hex
    )

    rr.TEXT_COLOR = text_color_hex

    text_rgb = rr.get_text_rgb(
        background_rgb
    )

    template_rgb = rr.build_static_template(
        reference_rgb,
        background_rgb,
        text_rgb,
        x,
        y,
        picture_width,
        picture_height,
    )

    preview_image = Image.fromarray(
        template_rgb,
        mode="RGB",
    ).convert("RGBA")

    logo_info = None

    if logo_mode in ("file", "generated"):

        rr.LOGO_GAP_PX = logo_gap_px

        if logo_mode == "generated":

            effective_scale = (
                logo_scale
                if logo_scale is not None
                else rr.GENERATED_LOGO_SCALE_DEFAULT
            )

            logo_image = rr.build_generated_logo_image(
                display_name,
                username,
                verified,
                logo_path,
                text_rgb,
                background_rgb,
            )

        else:

            effective_scale = (
                logo_scale
                if logo_scale is not None
                else rr.RAW_LOGO_SCALE_DEFAULT
            )

            logo_image = Image.open(
                logo_path
            ).convert("RGBA")

        rr.LOGO_SCALE = effective_scale

        (
            logo_x,
            logo_y,
            logo_width
        ) = rr.compute_logo_geometry(
            x,
            y,
            picture_width,
            picture_height,
        )

        logo_aspect = (
            logo_image.height
            /
            logo_image.width
        )

        logo_height = max(
            2,
            round(
                logo_width * logo_aspect
            )
        )

        resized_logo = logo_image.resize(
            (
                logo_width,
                logo_height
            ),
            Image.Resampling.LANCZOS,
        )

        preview_image.paste(
            resized_logo,
            (
                logo_x,
                logo_y
            ),
            resized_logo,
        )

        logo_info = {
            "x": logo_x,
            "y": logo_y,
            "width": logo_width,
            "height": logo_height,
        }

    return {
        "image": preview_image.convert("RGB"),
        "detection_method": detection_method,
        "movie_rect": (
            x,
            y,
            picture_width,
            picture_height,
        ),
        "logo_info": logo_info,
        "source_size": (
            source_width,
            source_height,
        ),
        "fps": fps,
        "duration": duration,
    }
