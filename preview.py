from PIL import Image

import reel_recolor as rr


def render_preview_frame(
    video_path,
    target_color_hex,
    text_color_hex,
    tweet_enabled=False,
    avatar_path=None,
    display_name=None,
    username=None,
    verified=True,
    tweet_gap_px=40,
    tweet_scale=None,
    logo_enabled=False,
    logo_path=None,
    logo_position_mode="auto",
    logo_manual_center=None,
    logo_gap_px=40,
    logo_scale=None,
):

    # Reuses reel_recolor.py's own pipeline functions so the
    # preview is pixel-for-pixel what one frame of the real
    # ffmpeg output would look like, with no video encoding.
    # Tweet and Logo are independent - either, both, or neither
    # can be composited onto the same preview image, matching how
    # they're independent overlays in the real render.

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

    tweet_info = None

    logo_info = None


    if tweet_enabled and avatar_path:

        effective_tweet_scale = (
            tweet_scale
            if tweet_scale is not None
            else rr.TWEET_SCALE_DEFAULT
        )

        tweet_image = rr.build_tweet_image(
            display_name,
            username,
            verified,
            avatar_path,
            text_rgb,
            background_rgb,
        )

        (
            tweet_x,
            tweet_y,
            tweet_width
        ) = rr.compute_logo_geometry(
            x,
            y,
            picture_width,
            picture_height,
            tweet_gap_px,
            effective_tweet_scale,
        )

        tweet_aspect = (
            tweet_image.height
            /
            tweet_image.width
        )

        tweet_height = max(
            2,
            round(
                tweet_width * tweet_aspect
            )
        )

        resized_tweet = tweet_image.resize(
            (
                tweet_width,
                tweet_height
            ),
            Image.Resampling.LANCZOS,
        )

        preview_image.paste(
            resized_tweet,
            (
                tweet_x,
                tweet_y
            ),
            resized_tweet,
        )

        tweet_info = {
            "x": tweet_x,
            "y": tweet_y,
            "width": tweet_width,
            "height": tweet_height,
        }


    if logo_enabled and logo_path:

        logo_image = Image.open(
            logo_path
        ).convert("RGBA")

        if (

            logo_position_mode == "manual"

            and

            logo_manual_center is not None
        ):

            logo_native_width, logo_native_height = (
                logo_image.size
            )

            (
                logo_x,
                logo_y
            ) = rr.compute_manual_logo_geometry(
                logo_manual_center[0],
                logo_manual_center[1],
                logo_native_width,
                logo_native_height,
            )

            resized_logo = logo_image

            logo_width = logo_native_width

            logo_height = logo_native_height

        elif logo_position_mode != "manual":

            effective_logo_scale = (
                logo_scale
                if logo_scale is not None
                else rr.RAW_LOGO_SCALE_DEFAULT
            )

            (
                logo_x,
                logo_y,
                logo_width
            ) = rr.compute_logo_geometry(
                x,
                y,
                picture_width,
                picture_height,
                logo_gap_px,
                effective_logo_scale,
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

        else:

            # Manual mode but no saved position for the currently
            # previewed video (or none provided) - nothing to draw.
            resized_logo = None

        if resized_logo is not None:

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
        "tweet_info": tweet_info,
        "logo_info": logo_info,
        "source_size": (
            source_width,
            source_height,
        ),
        "fps": fps,
        "duration": duration,
    }
