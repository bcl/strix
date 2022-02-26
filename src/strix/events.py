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
from datetime import datetime
from glob import glob
import json
import os

import structlog

from typing import Dict, List


def path_to_dt(path: str) -> datetime:
    # Use the last 2 elements of the path to construct a Datatime
    (date, time) = path.split("/")[-2:]
    time = time.replace("-", ":")
    dt_str = "{0} {1}".format(date, time)
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

def image_to_dt(event_date: str, image: str) -> datetime:
    """ Convert an event date (YYYY-MM-DD) and image HH-MM-SS-FF

    returns a datetime object
    """
    # Trim off .jpg and the frame count
    image_time = image.rsplit('-', 1)[0]
    return datetime.strptime(event_date+"/"+image_time, "%Y-%m-%d/%H-%M-%S")


def event_details(log: structlog.BoundLogger, event_path: str) -> Dict:
#    log.info("event_details", path=event_path)

    # Have the details already been created? If so read it and return.
    try:
        if os.path.exists(event_path+"/.details.json"):
            with open(event_path+"/.details.json") as f:
                return json.load(f)
    except json.decoder.JSONDecodeError:
        log.warn("Error reading .details.json from %s", event_path)

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

#    log.debug("event_details", thumbnail=thumbnail, start_time=str(start_time), end_time=str(end_time),
#              video=video, debug_video=debug_video, saved=is_saved)

    details = {
        "start":        str(start_time),
        "end":          str(end_time),
        "video":        video[0],
        "debug_video":  video[1],
        "thumbnail":    thumbnail,
        "images":       [],
        "saved":        is_saved
    }
    with open(event_path+"/.details.json", "w") as f:
        json.dump(details, f)
    return details


def camera_events(log: structlog.BoundLogger, base_dir: str, camera: str,
                  start: datetime, end: datetime, offset: int, limit: int) -> List[Dict]:
    # YYYY-MM-DD/HH-MM-SS is the format of the event directories.
    glob_path="%s/%s/????-??-??/??-??-??" % (base_dir, camera)

    # Newest to oldest, limited by offset and limit
    skipped = 0
    added = 0
    events = []     # type: List[Dict]
    for event_path in sorted(glob(glob_path), reverse=True):
        dt = path_to_dt(event_path)
        if dt < start or dt > end:
            continue
        if skipped < offset:
            skipped += 1
            continue

        events.insert(0, event_details(log, event_path))

        added += 1
        if limit > 0 and added >= limit:
            break

    return events
