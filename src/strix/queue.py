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
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import time

from PIL import Image
import structlog

from . import logger

THUMBNAIL_SIZE = (640, 480)

# More than 5 minute events have a timelapse created
TIMELAPSE_MIN = 5 * 60 * 5

def max_cores() -> int:
    return max(1, mp.cpu_count() // 2)


def GetImageDescriptions(path):
    """
    Extract EXIF ImageDescription for all the images in the directory
    """
    ## Run exiftool on the files
    cmd = ["exiftool", "-json", "-q", "-ImageDescription", path]
    try:
        out = subprocess.check_output(cmd)
        j = json.loads(out)
        return [d for d in j if "ImageDescription" in d]
    except subprocess.CalledProcessError:
        pass

    return []


def DescriptionDict(desc):
    """
    Split the motion info into dict entries

    <changed>-<noise>-<width>-<height>-<X>-<Y>
    """
    try:
        changed, noise, width, height, x, y = desc.split("-")
        return {
            "changed": int(changed),
            "noise": int(noise),
            "width": int(width),
            "height": int(height),
            "x": int(x),
            "y": int(y),
            "area": int(width) * int(height)
        }
    except ValueError:
        return {
            "changed": 0,
            "noise": 0,
            "width": 0,
            "height": 0,
            "x": 0,
            "y": 0,
            "area": 0
        }


def BestThumbnail(path):
    """
    Make a best guess at the image to use for a thumbnail

    Use the one with the most changes.
    """
    data = GetImageDescriptions(path)

    images = []
    for i in data:
        images.append({"name": i["SourceFile"], "description": DescriptionDict(i["ImageDescription"])})
    sorted_images = sorted(images, key=lambda i: i["description"]["changed"], reverse=True)
    return sorted_images[0]["name"]


## Handle watching the queue and dispatching movie creation and directory moving

def process_event(log: structlog.BoundLogger, base_dir: str, event: str, queue_tx) -> None:
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

    ffmpeg_cmd = ["ffmpeg", "-f", "image2", "-pattern_type", "glob", "-framerate", "5",
            "-i", "*.jpg", "-vf", "scale=1280:-2"]

    # Make a timelapse for events that are too long
    if len(glob(f"{event_path}/*jpg")) > TIMELAPSE_MIN:
        ffmpeg_cmd += ["-vf", "setpts=0.0625*PTS"]

    ffmpeg_cmd += ["-c:v", "h264", "-b:v", "2M", "video.m4v"]
    log.debug("ffmpeg cmdline", ffmpeg_cmd=ffmpeg_cmd)

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

    try:
        # Get the image with the highest change value
        thumbnail = BestThumbnail(event_path)
        im = Image.open(thumbnail)
        # im.size will get the actual size of the image
        im.thumbnail(THUMBNAIL_SIZE)
        im.save(os.path.join(event_path, "thumbnail.jpg"), "JPEG")
    except Exception as e:
        log.error("Failed to create thumbnail", exception=str(e))

    # Move the directory to its final location
    try:
        # Use the time of the first image
        images = sorted(list(glob(os.path.join(event_path, "*-*-*-*.jpg"))))
        first_jpg = os.path.split(images[0])[1]
        first_time = first_jpg.rsplit("-", 1)[0]
        event_path_base = os.path.split(event_path)[0]
        dest_path = os.path.join(event_path_base, first_time)
        if not os.path.exists(dest_path):
            os.rename(event_path, dest_path)
        log.info("Moved event to final location", dest_path=dest_path)

        # Tell the event thread/process about the new path
        queue_tx.send(dest_path)
    except Exception as e:
        log.error("Moving to destination failed", event_path=event_path, exception=str(e))

def monitor_queue(logging_queue, base_dir, quit, max_threads, queue_tx):
    threads = []
    log = logger.log(logging_queue)

    queue_path = os.path.abspath(os.path.join(base_dir, "queue/"))
    log.info("Started queue monitor", queue_path=queue_path)
    while not quit.is_set():
        time.sleep(5)
        # Remove any threads from the list that have finished
        for t in threads[:]:
            if not t.is_alive():
                threads.remove(t)

        for event_file in glob(os.path.join(queue_path, "*")):
            # Limit the number of processes to 1/2 the number of cpus (or 1)
            if len(threads) >= max_threads:
                break

            os.unlink(event_file)
            event = os.path.split(event_file)[-1]
            thread = mp.Process(target=process_event, args=(log, base_dir, event, queue_tx))
            threads.append(thread)
            thread.start()

    log.info("monitor_queue waiting for threads to finish")
    for t in threads:
        t.join()

    log.info("monitor_queue is quitting")
