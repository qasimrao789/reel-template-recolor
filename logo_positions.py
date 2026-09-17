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

    if entry is None:

        return None

    return (
        entry["x"],
        entry["y"],
    )
