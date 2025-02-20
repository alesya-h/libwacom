#!/usr/bin/env python3
#
# Copyright © 2012 Red Hat, Inc.
#
# Permission to use, copy, modify, distribute, and sell this software
# and its documentation for any purpose is hereby granted without
# fee, provided that the above copyright notice appear in all copies
# and that both that copyright notice and this permission notice
# appear in supporting documentation, and that the name of Red Hat
# not be used in advertising or publicity pertaining to distribution
# of the software without specific, written prior permission.  Red
# Hat makes no representations about the suitability of this software
# for any purpose.  It is provided "as is" without express or implied
# warranty.
#
# THE AUTHORS DISCLAIM ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
# NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY SPECIAL, INDIRECT OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import argparse
import configparser
import sys
import subprocess
from pathlib import Path


class Tablet(object):
    def __init__(self, name, bus, vid, pid):
        self.name = name
        self.bus = bus
        self.vid = vid  # Note: this is a string
        self.pid = pid  # Note: this is a string
        self.has_touch = False
        self.has_pad = False
        self.is_touchscreen = False

        # We have everything in strings so let's use that for sorting later
        # This will sort bluetooth before usb but meh
        self.cmpstr = ":".join((bus, vid, pid, name))

    def __lt__(self, other):
        return self.cmpstr < other.cmpstr

    def __str__(self):
        return f"{self.bus}:{self.vid}:{self.pid}:{self.name}"


class HWDBFile:
    def __init__(self):
        self.tablets = []

    def _tablet_entry(self, tablet):
        vid = tablet.vid.upper()
        pid = tablet.pid.upper()
        bustypes = {
            "usb": "0003",
            "bluetooth": "0005",
        }
        # serial devices have their own rules, so we skip anything that
        # doesn't have straight conversion
        try:
            bus = bustypes[tablet.bus]
        except KeyError:
            return

        match = f"b{bus}v{vid}p{pid}"
        entries = {"*": ["ID_INPUT=1", "ID_INPUT_TABLET=1", "ID_INPUT_JOYSTICK=0"]}
        if tablet.has_touch:
            if tablet.is_touchscreen:
                entries["* Finger"] = ["ID_INPUT_TOUCHSCREEN=1"]
            else:
                entries["* Finger"] = ["ID_INPUT_TOUCHPAD=1"]

        if tablet.has_pad:
            entries["* Pad"] = ["ID_INPUT_TABLET_PAD=1"]

        # Non-Wacom devices often have a Keyboard node instead of a Pad
        # device. If they share the USB ID with the tablet, we likely just
        # assigned ID_INPUT_TABLET to a keyboard device - and libinput refuses
        # to accept those.
        # Let's add a generic exclusion rule for anything we know of with a
        # Keyboard device name.
        if int(vid, 16) != 0x56A:
            entries["* Keyboard"] = ["ID_INPUT_TABLET=0"]

        lines = [f"# {tablet.name}"]
        for name, props in entries.items():
            lines.append(f"libwacom:name:{name}:input:{match}*")
            lines.extend([f" {p}" for p in props])
            lines.append("")

        return "\n".join(lines)

    def print(self, file=sys.stdout):
        header = (
            "# hwdb entries for libwacom supported devices",
            "# This file is generated by libwacom, do not edit",
            "#",
            "# The lookup key is a contract between the udev rules and the hwdb entries.",
            "# It is not considered public API and may change.",
            "",
        )
        print("\n".join(header), file=file)

        for t in self.tablets:
            entry = self._tablet_entry(t)
            if entry:
                print(entry, file=file)


class TabletDatabase:
    def __init__(self, path):
        self.path = path
        self.tablets = sorted(self._load(path))

    def _load(self, path):
        for file in Path(path).glob("*.tablet"):
            config = configparser.ConfigParser()
            config.read(file)
            for match in config["Device"]["DeviceMatch"].split(";"):
                # ignore trailing semicolons
                if not match or match == "generic":
                    continue

                # For hwdb entries we don't care about name matches,
                # it'll just result in duplicate ID_INPUT_TABLET assignments
                # for tablets with re-used usbids and that doesn't matter
                try:
                    bus, vid, pid, *_ = match.split(":")
                except ValueError as e:
                    print(f"Failed to process match {match}")
                    raise e

                name = config["Device"]["Name"]
                t = Tablet(name, bus, vid, pid)

                try:
                    t.has_touch = config["Features"]["Touch"].lower() == "true"
                    if t.has_touch:
                        integration = config["Device"]["IntegratedIn"]
                        t.is_touchscreen = (
                            "Display" in integration or "System" in integration
                        )
                except KeyError:
                    pass
                t.has_pad = any(config.has_section(s) for s in ["Buttons", "Keys"])
                yield t


# Guess the udev directory based on path. For the case of /usr/share, the
# udev directory is probably in /usr/lib so let's fallback to that.
def find_udev_base_dir(path):
    for parent in path.parents:
        d = Path(parent / "udev" / "rules.d")
        if d.exists():
            return d.parent

    # /usr/share but also any custom prefixes
    for parent in path.parents:
        d = Path(parent / "lib" / "udev" / "rules.d")
        if d.exists():
            return d.parent

    raise FileNotFoundError(path)


# udev's behaviour is that where a file X exists in two locations,
# only the highest-precedence one is read. Our files are supposed to be
# complimentary to the system-installed ones (which default to
# 65-libwacom.hwdb) so we bump the filename number.
def guess_hwdb_filename(basedir):
    hwdbdir = Path(basedir) / "hwdb.d"
    if not hwdbdir.exists():
        raise FileNotFoundError(hwdbdir)

    fname = hwdbdir / f"66-libwacom.hwdb"
    return fname


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update the system according to the current set of tablet data files"
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default="/etc/libwacom",
        help="Directory to load .tablet files from",
    )
    # buildsystem-mode is what we use from meson, it changes the
    # the behavior to just generate the file and print it
    parser.add_argument(
        "--buildsystem-mode",
        action="store_true",
        default=False,
        help="be used by the build system only",
    )
    parser.add_argument(
        "--skip-systemd-hwdb-update",
        action="store_true",
        default=False,
        help="Do not run systemd-hwdb --update (Note: updates to tablet files will not be reflected in udev)",
    )
    parser.add_argument(
        "--udev-base-dir",
        type=Path,
        default=None,
        help="The udev base directory (default: guessed based on the path)",
    )
    ns = parser.parse_args()

    db = TabletDatabase(ns.path)

    hwdb = HWDBFile()
    # Bamboo and Intuos devices connected to the system via Wacom's
    # Wireless Accessory Kit appear to udev as having the PID of the
    # dongle rather than the actual tablet. Make sure we properly tag
    # such devices.
    #
    # We only really care about this in the official hwdb files
    if ns.buildsystem_mode:
        wwak = Tablet("Wacom Wireless Accessory Kit", "usb", "056A", "0084")
        wwak.has_pad = True
        wwak.has_touch = True
        hwdb.tablets.append(wwak)

    hwdb.tablets.extend(db.tablets)
    if ns.buildsystem_mode:
        hwdb.print()
    else:
        try:
            udevdir = ns.udev_base_dir or find_udev_base_dir(ns.path)
            hwdbfile = guess_hwdb_filename(udevdir)
            with open(hwdbfile, "w") as fd:
                hwdb.print(fd)
            print(f"New hwdb file: {hwdbfile}")

            if not ns.skip_systemd_hwdb_update:
                subprocess.run(
                    ["systemd-hwdb", "update"],
                    capture_output=True,
                    check=True,
                    text=True,
                )
            print("Finished, please unplug and replug your device")
        except PermissionError as e:
            print(f"{e}, please run me as root")
        except FileNotFoundError as e:
            print(f"Unable to find udev base directory: {e}")
        except subprocess.CalledProcessError as e:
            print(f"hwdb update failed: {e.stderr}")
