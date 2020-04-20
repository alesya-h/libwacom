/*
 * Copyright © 2012 Red Hat, Inc.
 *
 * Permission to use, copy, modify, distribute, and sell this software
 * and its documentation for any purpose is hereby granted without
 * fee, provided that the above copyright notice appear in all copies
 * and that both that copyright notice and this permission notice
 * appear in supporting documentation, and that the name of Red Hat
 * not be used in advertising or publicity pertaining to distribution
 * of the software without specific, written prior permission.  Red
 * Hat makes no representations about the suitability of this software
 * for any purpose.  It is provided "as is" without express or implied
 * warranty.
 *
 * THE AUTHORS DISCLAIM ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
 * INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN
 * NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY SPECIAL, INDIRECT OR
 * CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
 * OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
 * NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
 * CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 * Authors:
 *        Olivier Fourdan (ofourdan@redhat.com)
 */

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libwacom.h"
#include <glib/gi18n.h>
#include <glib.h>

#include <linux/input.h>

static void print_hwdb_header (void)
{
	printf("# hwdb entries for libwacom supported devices\n"
	       "# This file is generated by libwacom, do not edit\n"
	       "#\n"
	       "# The lookup key is a contract between the udev rules and the hwdb entries.\n"
	       "# It is not considered public API and may change.\n"
	       "\n");
}

static void print_wireless_kit_quirk (void)
{
	/* Bamboo and Intuos devices connected to the system via Wacom's
	 * Wireless Accessory Kit appear to udev as having the PID of the
	 * dongle rather than the actual tablet. Make sure we properly tag
	 * such devices.
	 */
	const char *matchstr = "b0003v056Ap0084";

	printf("# Wacom Wireless Accessory Kit\n"
	       "libwacom:name:*:input:%s*\n"
	       " ID_INPUT=1\n"
	       " ID_INPUT_TABLET=1\n"
	       " ID_INPUT_JOYSTICK=0\n"
	       "\n"
	       "libwacom:name:* Finger:input:%s*:\n"
	       " ID_INPUT_TOUCHPAD=1\n"
	       "\n"
	       "libwacom:name:* Pad:input:%s*:\n"
	       " ID_INPUT_TABLET_PAD=1\n"
	       "\n", matchstr, matchstr, matchstr);
}

static void print_hwdb_entry (WacomDevice *device, const WacomMatch *match)
{
	WacomBusType type = libwacom_match_get_bustype (match);
	int vendor = libwacom_match_get_vendor_id (match);
	int product = libwacom_match_get_product_id (match);
	char matchstr[64];
	int bus;

	switch (type) {
		case WBUSTYPE_BLUETOOTH:
			bus = BUS_BLUETOOTH;
			break;
		case WBUSTYPE_USB:
			bus = BUS_USB;
			break;
		default:
			/* serial devices have a special rule */
			return;
	}

	g_snprintf (matchstr, sizeof(matchstr),
		    "b%04Xv%04Xp%04X", bus, vendor, product);

	/* We print three hwdb entries per device:
	   - a generic one to set tablet and unset joystick
	   - one for the Finger device to set touchscreen or touchpad
	   - one for the Pad device to sed tablet-pad
	 */
	printf("# %s\n", libwacom_get_name (device));
	printf("libwacom:name:*:input:%s*\n"
	       " ID_INPUT=1\n"
	       " ID_INPUT_TABLET=1\n"
	       " ID_INPUT_JOYSTICK=0\n"
	       "\n", matchstr);

	if (libwacom_has_touch (device)) {
		const char *touchtype = "ID_INPUT_TOUCHPAD";

		if (libwacom_get_integration_flags (device) != WACOM_DEVICE_INTEGRATED_NONE)
			touchtype = "ID_INPUT_TOUCHSCREEN";

		printf("libwacom:name:* Finger:input:%s*\n"
		       " %s=1\n"
		       "\n", matchstr, touchtype);
	}

	if (libwacom_get_num_buttons (device) > 0) {
		printf("libwacom:name:* Pad:input:%s*\n"
		       " ID_INPUT_TABLET_PAD=1\n"
		       "\n", matchstr);
	}
}

int main(int argc, char **argv)
{
	WacomDeviceDatabase *db;
	WacomDevice **list, **p;

	db = libwacom_database_new_for_path(TOPSRCDIR"/data");

	list = libwacom_list_devices_from_database(db, NULL);
	if (!list) {
		fprintf(stderr, "Failed to load device database.\n");
		return 1;
	}

	print_hwdb_header ();
	print_wireless_kit_quirk ();
	for (p = list; *p; p++) {
		const WacomMatch **matches, **match;

		matches = libwacom_get_matches(*p);
		for (match = matches; *match; match++)
			print_hwdb_entry(*p, *match);
	}

	g_free(list);
	libwacom_database_destroy (db);

	return 0;
}

/* vim: set noexpandtab tabstop=8 shiftwidth=8: */