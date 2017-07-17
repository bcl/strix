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
import threading

from PIL import Image

from typing import List

THUMBNAIL_SIZE = (640, 480)

## Handle watching the queue and dispatching movie creation and directory moving

def process_event(base_dir: str, event: str) -> None:
    print("Processing %s" % event)
    print("base_dir = %s" % base_dir)

    # The actual path is the event with _ replaced by /
    event_path = os.path.join(base_dir, event.replace("_", os.path.sep))
    if not os.path.isdir(event_path):
        print("ERROR: event_path '%s' doesn't exist" % event_path)
        return

    debug_path = os.path.join(event_path, "debug")
    try:
        os.mkdir(debug_path, mode=0o755)
    except Exception as e:
        print("ERROR: Failed to create debug directory: %s" % e)
        return

    # Move the debug images into ./debug/
    try:
        for debug_img in glob(os.path.join(event_path, "*m.jpg")):
            shutil.move(debug_img, debug_path)
    except Exception as e:
        print("ERROR: Failed to move debug images")

    ffmpeg_cmd = ["ffmpeg", "-f", "image2", "-pattern_type", "glob", "-r", "10", "-i", "*.jpg", "-c:v",
                  "libvpx", "-crf", "10", "-b:v", "2M", "video.webm"]

    # Make a movie out of the jpg images with ffmpeg
    try:
        subprocess.run(ffmpeg_cmd, cwd=event_path, check=True)
    except Exception as e:
        print("ERROR: Failed to create video: %s" % e)

    # Make a movie out of the debug jpg images with ffmpeg
    try:
        subprocess.run(ffmpeg_cmd, cwd=debug_path, check=True)
    except Exception as e:
        print("ERROR: Failed to create debug video: %s" % e)

    # Create a thumbnail of the middle image of the capture, on the theory that it
    # has the best chance of being 'interesting'.
    try:
        images = sorted(list(glob(os.path.join(event_path, "*.jpg"))))
        middle = images[int(len(images)/2)]
        im = Image.open(middle)
        # im.size will get the actual size of the image
        im.thumbnail(THUMBNAIL_SIZE)
        im.save(os.path.join(event_path, "thumbnail.jpg"), "JPEG")
    except Exception as e:
        print("ERROR: Failed to create thumbnail: %s" % e)

    # Move the directory to its final location
    try:
        # Use the time of the first image
        first_jpg = os.path.split(images[0])[1]
        first_time = first_jpg.rsplit("-", 1)[0]
        event_path_base = os.path.split(event_path)[0]
        dest_path = os.path.join(event_path_base, first_time)
        print("INFO: Destination path is %s" % dest_path)
        if not os.path.exists(dest_path):
            os.rename(event_path, dest_path)
    except Exception as e:
        print("ERROR: Moving %s to destination failed: %s" % (event_path, e))

def monitor_queue(base_dir: str, quit: threading.Event) -> None:
    threads = [] # type: List[mp.Process]

    queue_path = os.path.abspath(os.path.join(base_dir, "queue/"))
    while not quit.is_set():
        time.sleep(5)
        # Remove any threads from the list that have finished
        for t in threads[:]:
            if not t.is_alive():
                threads.remove(t)

        print("Checking %s" % queue_path)
        for event_file in glob(os.path.join(queue_path, "*")):
            os.unlink(event_file)
            event = os.path.split(event_file)[-1]
            thread = mp.Process(target=process_event, args=(base_dir, event))
            threads.append(thread)
            thread.start()

    print("monitor_queue waiting for threads to finish")
    for t in threads:
        t.join()

    print("monitor_queue is quitting")
