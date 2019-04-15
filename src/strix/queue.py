# queue.py
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
from glob import glob
import multiprocessing as mp
import os
import shutil
import subprocess
import time

from PIL import Image
import structlog

from typing import List

from . import logger

THUMBNAIL_SIZE = (640, 480)

## Handle watching the queue and dispatching movie creation and directory moving

def process_event(log: structlog.BoundLogger, base_dir: str, event: str) -> None:
    log.info(event_path=event, base_dir=base_dir)

    # The actual path is the event with _ replaced by /
    event_path = os.path.join(base_dir, event.replace("_", os.path.sep))
    if not os.path.isdir(event_path):
        log.error("event_path doesn't exist", event_path=event_path)
        return

    debug_path = os.path.join(event_path, "debug")
    try:
        os.mkdir(debug_path, mode=0o755)
    except Exception as e:
        log.error("Failed to create debug directory", exception=str(e))
        return

    # Move the debug images into ./debug/
    try:
        for debug_img in glob(os.path.join(event_path, "*m.jpg")):
            shutil.move(debug_img, debug_path)
    except Exception as e:
        log.debug("Failed to move debug images into ./debug/")

    ffmpeg_cmd = ["ffmpeg", "-f", "image2", "-pattern_type", "glob", "-r", "10", "-i", "*.jpg", "-c:v",
                  "libvpx", "-crf", "10", "-b:v", "2M", "video.webm"]

    # Make a movie out of the jpg images with ffmpeg
    try:
        subprocess.run(ffmpeg_cmd, cwd=event_path, check=True)
    except Exception as e:
        log.error("Failed to create video", exception=str(e))

    # Make a movie out of the debug jpg images with ffmpeg
    try:
        subprocess.run(ffmpeg_cmd, cwd=debug_path, check=True)
    except Exception as e:
        log.error("Failed to create debug video", exception=str(e))

    # Create a thumbnail of the 25% image of the capture, on the theory that it
    # has the best chance of being 'interesting' since it is near the trigger point
    try:
        images = sorted(list(glob(os.path.join(event_path, "*.jpg"))))
        idx = images[int(len(images)//4)]
        im = Image.open(idx)
        # im.size will get the actual size of the image
        im.thumbnail(THUMBNAIL_SIZE)
        im.save(os.path.join(event_path, "thumbnail.jpg"), "JPEG")
    except Exception as e:
        log.error("Failed to create thumbnail", exception=str(e))

    # Move the directory to its final location
    try:
        # Use the time of the first image
        first_jpg = os.path.split(images[0])[1]
        first_time = first_jpg.rsplit("-", 1)[0]
        event_path_base = os.path.split(event_path)[0]
        dest_path = os.path.join(event_path_base, first_time)
        log.info("Moved event to final location", dest_path=dest_path)
        if not os.path.exists(dest_path):
            os.rename(event_path, dest_path)
    except Exception as e:
        log.error("Moving to destination failed", event_path=event_path, exception=str(e))

def monitor_queue(logging_queue: mp.Queue, base_dir: str, quit: mp.Event) -> None:
    threads = [] # type: List[mp.Process]
    log = logger.log(logging_queue)

    queue_path = os.path.abspath(os.path.join(base_dir, "queue/"))
    log.info("Started queue monitor", queue_path=queue_path)
    while not quit.is_set():
        time.sleep(5)
        # Remove any threads from the list that have finished
        for t in threads[:]:
            if not t.is_alive():
                threads.remove(t)

        log.debug("queue check", queue_path=queue_path)
        for event_file in glob(os.path.join(queue_path, "*")):
            # Limit the number of processes
            if len(threads) > mp.cpu_count():
                log.debug("Too many running threads (%d), not adding a new one yet.", len(threads))
                break

            os.unlink(event_file)
            event = os.path.split(event_file)[-1]
            thread = mp.Process(target=process_event, args=(log, base_dir, event))
            threads.append(thread)
            thread.start()

    log.info("monitor_queue waiting for threads to finish")
    for t in threads:
        t.join()

    log.info("monitor_queue is quitting")
