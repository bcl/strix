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
import os
import time
import multiprocessing as mp

## Handle watching the queue and dispatching movie creation and directory moving

def process_event(event):
    print("Processing %s" % event)

    # Convert event to a path, replace _ with /
    # Make sure it exists
    # Make a ./debug/ directory and move the *m.jpg files into it
    # Make a movie out of the jpg files with ffmpeg
    # Make a movie out of the debug images
    # Create a thumbnail
    # Move the directory to its final location

def monitor_queue(queue_path, quit):
    threads = []

    while not quit.is_set():
        time.sleep(5)
        # Remove any threads from the list that have finished
        for t in threads[:]:
            if not t.is_alive():
                threads.remove(t)

        print("Checking %s" % queue_path)
        for event in glob(os.path.join(queue_path, "*")):
            os.unlink(event)
            thread = mp.Process(target=process_event, args=(event,))
            threads.append(thread)
            thread.start()

    print("monitor_queue waiting for threads to finish")
    for t in threads:
        t.join()

    print("monitor_queue is quitting")
