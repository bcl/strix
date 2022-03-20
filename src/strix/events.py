# events.py
#
# Copyright (C) 2017 Brian C. Lane
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from datetime import datetime, timedelta
from glob import glob
import json
import multiprocessing as mp
import os
import re
import shutil
import tempfile
import threading

import structlog

class EventCacheClass:
    def __init__(self):
        self._log = None
        self._base_dir = "/invalid/path/for/expire"
        self._last_check = datetime(1985, 10, 26, 1, 22, 0)
        self._force_expire = False
        self._check_cache = 60
        self._keep_days = 9999
        self._lock = threading.Lock()
        self._cache = {}

    def get(self, key):
        with self._lock:
            return self._cache[key]

    def set(self, key, value):
        with self._lock:
            # Convert start/end to datetime object
            if "start" in value and type(value["start"]) == type(""):
                value["start"] = datetime.fromisoformat(value["start"])
            if "end" in value and type(value["end"]) == type(""):
                value["end"] = datetime.fromisoformat(value["end"])

            self._cache[key] = value

            # This can potentially remove the key just added if it is an old event
            self._expire_events()

            # Return True if it was added to the cache
            return key in self._cache

    def base_dir(self, base_dir):
        with self._lock:
            self._base_dir = base_dir

    def logger(self, logger):
        with self._lock:
            self._log = logger

    def keep(self, days):
        with self._lock:
            self._keep_days = days

    def check_cache(self, minutes):
        with self._lock:
            self._check_cache = minutes

    def reset_check(self):
        with self._lock:
            self._last_check = datetime(1985, 10, 26, 1, 22, 0)

    def force_expire(self, force=False):
        with self._lock:
            self._force_expire = force

    def log_info(self, *args):
        if self._log:
            self._log.info(*args)

    def log_error(self, *args):
        if self._log:
            self._log.error(*args)

    def _expire_events(self):
        start = datetime.now()

        if not self._force_expire:
            if start - self._last_check < timedelta(minutes=self._check_cache):
                return
        self._last_check = datetime.now()

        if not self._force_expire:
            self.log_info("Checking cache...")

        remove = {}
        for e in self._cache:
            if self._cache[e]["start"] < datetime.now() - timedelta(days=self._keep_days):
                if "event_path" in self._cache[e] \
                   and self._cache[e]["event_path"].startswith(self._base_dir):
                    daypath = os.path.dirname(self._cache[e]["event_path"].rstrip("/"))
                    if daypath in remove:
                        remove[daypath].append(e)
                    else:
                        remove[daypath] = [e]

        if not self._force_expire:
            self.log_info(f"Done checking cache in {datetime.now()-start}")

        remove = {}
        if len(remove) == 0:
            return

        self.log_info(f"Removing {len(remove)} days")

        # Create the temporary delete_queue directory
        tdir = tempfile.TemporaryDirectory(dir=os.path.join(self._base_dir, "delete_queue"))
        delete_queue = tdir.name

        # Move each day's directory to the temporary delete_queue directory
        for daypath in remove:
            # All paths should have a Camera* component
            cm = re.search("(Camera\d+)", daypath)
            if not cm:
                self.log_error(f"Camera* missing from path {daypath}")

            if cm and os.path.exists(daypath):
                self.log_info("REMOVE: %s", daypath)

                if not os.path.exists(os.path.join(delete_queue, cm.group())):
                    os.makedirs(os.path.join(delete_queue, cm.group()))

                # Move the daily directory tree into the delete_queue/Camera* directory
                shutil.move(daypath, os.path.join(delete_queue, cm.group()))

            # Remove the events from the cache
            self.log_info(f"Removing {len(remove[daypath])} events")
            for e in remove[daypath]:
                del self._cache[e]

        self.log_info(f"Expire of {len(remove)} days took: {datetime.now()-start}")

        def dth_fn(delete_queue):
            shutil.rmtree(delete_queue, ignore_errors=True)

        # Start a thread to do the actual delete in the background
        dth = mp.Process(name="delete-thread",
                            target=dth_fn,
                            args=(delete_queue,))
        dth.start()


# Singleton
EventCache = EventCacheClass()


def preload_cache(log, base_dir):
    log.info("Pre-loading event cache...")
    start = datetime(1985, 10, 26, 1, 22, 0)
    total = timedelta()
    EventCache.force_expire(True)
    for camera in sorted(c for c in os.listdir(base_dir) if c.startswith("Camera")):
        end   = datetime.now()
        _ = camera_events(log, base_dir, camera, start, end, 0, 0)
        log.info(f"{camera} event cache loaded in {datetime.now()-end} seconds")
        total += datetime.now()-end
    log.info(f"Event cache loaded in {total} seconds")
    EventCache.force_expire(False)


def path_to_dt(path):
    # Use the last 2 elements of the path to construct a Datatime
    (date, time) = path.split("/")[-2:]
    time = time.replace("-", ":")
    dt_str = "{0} {1}".format(date, time)
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

def image_to_dt(event_date, image):
    """ Convert an event date (YYYY-MM-DD) and image HH-MM-SS-FF

    returns a datetime object
    """
    # Trim off .jpg and the frame count
    image_time = image.rsplit('-', 1)[0]
    return datetime.strptime(event_date+"/"+image_time, "%Y-%m-%d/%H-%M-%S")


def event_details(log, event_path):
    # Check the cache for the details
    try:
        return EventCache.get(event_path)
    except KeyError:
        pass

    # Try the file cache next
    try:
        if os.path.exists(event_path+"/.details.json"):
            with open(event_path+"/.details.json") as f:
                details = json.load(f)

            # Adding to the cache can potentially expire old events
            ok = EventCache.set(event_path, details)
            if ok:
                return details
            else:
                return None
    except json.decoder.JSONDecodeError:
        log.error("Error reading .details.json from %s", event_path)

    (camera_name, event_date, event_time) = event_path.rsplit("/", 3)[-3:]

    # Grab the camera, date, and time and build the URL path
    url = "motion/"+"/".join([camera_name, event_date, event_time])

    # Get the list of images, skipping thumbnail.jpg
    images = []
    for i in sorted(glob(event_path+"/*.jpg")):
        if "thumbnail.jpg" in i:
            continue
        images.append(os.path.basename(i))

    if os.path.exists(event_path+"/thumbnail.jpg"):
        thumbnail = url+"/thumbnail.jpg"
    elif images:
        thumbnail = images[len(images)//4]
    else:
        thumbnail = "images/missing.jpg"

    if images:
        start_time = image_to_dt(event_date, images[0])
        end_time   = image_to_dt(event_date, images[-1])
    else:
        # XXX How to handle an empty directory?
        start_time = datetime.now()
        end_time = datetime.now()

    # Find the videos, if they exist
    video = []
    for pth in [event_path, event_path+"/debug"]:
        for ext in ["m4v", "webm", "mp4", "ogg"]:
            if os.path.exists(pth+"/video."+ext):
                video.append(url+"/video."+ext)
                break
        else:
            video.append("images/missing.jpg")

    is_saved = os.path.exists(event_path+"/.saved")

    details = {
        "start":        start_time,
        "end":          end_time,
        "video":        video[0],
        "debug_video":  video[1],
        "thumbnail":    thumbnail,
        "images":       [],
        "saved":        is_saved,
        "event_path":   event_path,
    }

    # Adding to the cache can potentially expire it if it was an old event
    ok = EventCache.set(event_path, details)
    if not ok:
        return None

    with open(event_path+"/.details.json", "w") as f:
        json.dump(details, f, default=str)
    return details


def camera_events(log, base_dir, camera, start, end, offset, limit):
    # YYYY-MM-DD/HH-MM-SS is the format of the event directories.
    glob_path="%s/%s/????-??-??/??-??-??" % (base_dir, camera)

    # Newest to oldest, limited by offset and limit
    skipped = 0
    added = 0
    events = []
    for event_path in sorted(glob(glob_path), reverse=True):
        dt = path_to_dt(event_path)
        if dt < start or dt > end:
            continue
        if skipped < offset:
            skipped += 1
            continue

        details = event_details(log, event_path)
        if details is not None:
            events.insert(0, details)

        added += 1
        if limit > 0 and added >= limit:
            break

    return events
