import json
import os


MODE_FIXED = "fixed"
MODE_PER_REEL = "per_reel"


def new_positions(mode):

    return {
        "mode": mode,
        "fixed_position": None,
        "positions": {},
    }


def load_positions(path):

    if not os.path.isfile(
        path
    ):

        return new_positions(
            MODE_PER_REEL
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as handle:

        data = json.load(
            handle
        )

    data.setdefault(
        "mode",
        MODE_PER_REEL,
    )

    data.setdefault(
        "fixed_position",
        None,
    )

    data.setdefault(
        "positions",
        {},
    )

    return data


def save_positions(path, data):

    folder = os.path.dirname(
        path
    )

    if folder:

        os.makedirs(
            folder,
            exist_ok=True,
        )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            data,
            handle,
            indent=2,
        )


def set_fixed_position(path, x, y):

    data = load_positions(
        path
    )

    data["mode"] = MODE_FIXED

    data["fixed_position"] = {
        "x": x,
        "y": y,
    }

    save_positions(
        path,
        data,
    )

    return data


def set_reel_position(path, filename, x, y):

    data = load_positions(
        path
    )

    data["mode"] = MODE_PER_REEL

    data["positions"][
        filename
    ] = {
        "x": x,
        "y": y,
    }

    save_positions(
        path,
        data,
    )

    return data


def set_no_logo(path, filename):

    # Marks a video as deliberately having no logo, distinct from
    # "not yet annotated" (missing entirely from "positions").
    # process_video() still processes/recolors the video, it just
    # skips the logo overlay for this one.

    data = load_positions(
        path
    )

    data["mode"] = MODE_PER_REEL

    data["positions"][
        filename
    ] = {
        "skip": True,
    }

    save_positions(
        path,
        data,
    )

    return data


def is_marked_no_logo(data, filename):

    entry = data.get(
        "positions",
        {},
    ).get(
        filename
    )

    return bool(
        entry
    ) and entry.get(
        "skip",
        False,
    )


def is_annotated(data, filename):

    # True once a video has been "decided" one way or another
    # (a position, or marked no-logo) - used to tell a genuinely
    # pending video apart from one that's done.

    mode = data.get(
        "mode",
        MODE_PER_REEL,
    )

    if mode == MODE_FIXED:

        return data.get(
            "fixed_position"
        ) is not None

    return filename in data.get(
        "positions",
        {},
    )


def get_position_for(data, filename):

    mode = data.get(
        "mode",
        MODE_PER_REEL,
    )

    if mode == MODE_FIXED:

        fixed = data.get(
            "fixed_position"
        )

        if fixed is None:

            return None

        return (
            fixed["x"],
            fixed["y"],
        )

    entry = data.get(
        "positions",
        {},
    ).get(
        filename
    )

    if entry is None or entry.get(
        "skip",
        False,
    ):

        return None

    return (
        entry["x"],
        entry["y"],
    )
