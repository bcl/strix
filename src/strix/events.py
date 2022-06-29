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
        self._last_check = datetime.now()
        self._check_cache = 60
        self._keep_days = 9999
        self._lock = threading.Lock()
        self._cache = {}

    def cleanup_dq(self):
        """
        Cleanup any delete_queue subdirectories that may be leftover from previous run
        """

        def dth_fn(dq_dirs):
            for dq in dq_dirs:
                if not dq.startswith(self._base_dir):
                    raise RuntimeError(f"Invalid dq path: {dq}")

                shutil.rmtree(dq, ignore_errors=True)

        base = os.path.join(self._base_dir, "delete_queue")
        dq_dirs = [os.path.join(base, dq) for dq in os.listdir(base)]

        # Start a thread to do the actual delete in the background
        dth = mp.Process(name="delete-thread",
                            target=dth_fn,
                            args=(dq_dirs,))
        dth.start()

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

    def events(self, camera=None, reverse=False):
        """
        Return a sorted list of the events
        """
        if not camera:
            return sorted(self._cache.keys(), reverse=reverse)

        cp = self._base_dir + "/" + camera
        # limit results to the selected camera
        return sorted((p for p in self._cache.keys() if p.startswith(cp)), reverse=reverse)

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

    def log_info(self, *args):
        if self._log:
            self._log.info(*args)

    def log_error(self, *args):
        if self._log:
            self._log.error(*args)

    def _expire_events(self):
        start = datetime.now()

        if start - self._last_check < timedelta(minutes=self._check_cache):
            return
        self._last_check = datetime.now()

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

        self.log_info(f"Done checking cache in {datetime.now()-start}")

        if len(remove) == 0:
            return

        # The result of the above is a dict (remove) with daily lists of events to be
        # removed. NOTE that this may not be ALL the day's events so it needs to move
        # them individually, but needs to use the Camera and date to prevent collisions
        # with other cameras while waiting for the delete to run in the background.

        # Create the temporary delete_queue directory
        delete_queue = tempfile.mkdtemp(dir=os.path.join(self._base_dir, "delete_queue"))

        # Move each day's directory to the temporary delete_queue directory
        for daypath in remove:
            # All paths should have a Camera* component
            cm = re.search("(Camera\d+)", daypath)
            if not cm:
                self.log_error(f"Camera* missing from path {daypath}")

            if cm and os.path.exists(daypath):
                # Make a directory for the day's events
                daydir = os.path.basename(daypath)
                dqdir = os.path.join(delete_queue, cm.group(), daydir)
                if not os.path.exists(dqdir):
                    os.makedirs(dqdir)

                # Move the expired events into the delete_queue/Camera*/YYYY-MM-DD/ directory
                for e in remove[daypath]:
                    self.log_info(f"MOVE: {e} -> {dqdir}")
                    shutil.move(e, dqdir)

            # Remove the events from the cache
            self.log_info(f"Removing {len(remove[daypath])} events from {daypath}")
            for e in remove[daypath]:
                del self._cache[e]

        self.log_info(f"Expire of {len(remove)} directories took: {datetime.now()-start}")

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

    total = timedelta()
    for camera in sorted(c for c in os.listdir(base_dir) if c.startswith("Camera")):
        start = datetime.now()

        # YYYY-MM-DD/HH-MM-SS is the format of the event directories.
        glob_path="%s/%s/????-??-??/??-??-??" % (base_dir, camera)
        for event_path in sorted(glob(glob_path), reverse=True):
            _ = event_details(log, event_path)
        log.info(f"{camera} event cache loaded in {datetime.now()-start} seconds")
        total += datetime.now()-start
    log.info(f"Event cache loaded in {total} seconds")

    # Next event will check for expired entries
    EventCache.reset_check()


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
    # Newest to oldest, limited by offset and limit
    skipped = 0
    added = 0
    events = []
    for event_path in EventCache.events(camera=camera, reverse=True):
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

def queue_events(log, queue_rx):
    """
    Loop, reading new event paths from the Pipe (the queue mp thread is at the other end)
    and adding their details to the EventCache
    """
    while True:
        try:
            if not queue_rx.poll(10):
                continue

            event_path = queue_rx.recv()
        except EOFError:
            break

        _ = event_details(log, event_path)
