# strix/__init__.py
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
import multiprocessing as mp
import os
import re
import time

from . import api
from . import cmdline
from . import events
from . import queue
from . import logger
from . import motion

## Check the motion args
## Start the queue watcher thread
## Start the bottle/API thread
## Wait for a signal to shutdown

def check_motion_config(config_path):
    """ Check the config file to make sure the settings match what Strix needs.
    """
    picture_filename = "%Y-%m-%d/%v/%H-%M-%S-%q"
    on_event_end_re = r".*touch (.*)/queue/Camera%t_%Y-%m-%d_%v"
    target_dir_re = r"(.*)/Camera\d+"

    errors = []
    base_target_dir = ""
    base_queue_dir = ""
    found_pf = False

    cfg = motion.config.MotionConfig(config_path)

    # If there are threads, check their settings instead
    for c in [cfg.config] + \
             [cfg.thread[cc] for cc in filter(lambda k: k.startswith("thread"), cfg.config.keys())]:
        if c.get("picture_filename", "") == picture_filename:
            found_pf = True

        on_event_end = c.get("on_event_end", "")
        if on_event_end:
            em = re.match(on_event_end_re, on_event_end)
            if not em or not em.groups():
                continue
            # Above errors will be caught by not having base_queue_dir set.
            if not base_queue_dir:
                base_queue_dir = em.group(1)
            elif base_queue_dir != em.group(1):
                errors += ["All of the paths in on_event_end MUST match."]

        target_dir = c.get("target_dir", "")
        if target_dir:
            tm = re.match(target_dir_re, target_dir)
            if not tm or not tm.groups():
                continue
            # Above errors will be caught by not having base_target_dir set.
            if not base_target_dir:
                base_target_dir = tm.group(1)
            elif base_target_dir != tm.group(1):
                errors += ["All of the base paths in target_dir MUST match."]

    if not base_target_dir:
        errors += ["Could not find a target_dir setting. The last directory must be /CameraX"]
    if not base_queue_dir:
        errors += ["Could not find an on_event_end setting. It must be set to /usr/bin/touch <TARGET_DIR>/queue/Camera%t_%Y-%m-%d_%v"]
    if base_target_dir and base_queue_dir and base_target_dir != base_queue_dir:
        errors += ["The target_dir and the base dir for on_event_end MUST match. eg. /var/lib/motion/"]
    if not found_pf:
        errors += ["picture_filename MUST be set to %s" % picture_filename]

    return (base_target_dir, errors)


def run():
    parser = cmdline.parser(queue.max_cores())
    opts = parser.parse_args()

    try:
        (base_dir, errors) = check_motion_config(opts.config)
    except Exception as e:
        errors = [str(e)]

    if errors:
        def p_e(e):
            print("ERROR: %s" % e)
        list(map(p_e, errors))
        return False

    # Start logger thread
    logger_queue = mp.JoinableQueue()
    logger_quit = mp.Event()
    logger_thread = mp.Process(name="logger-thread",
                                target=logger.listener,
                                args=(logger_queue, logger_quit, opts.log))
    logger_thread.start()
    running_threads = [(logger_thread, logger_quit)]

    # Setup a console logger for the startup messages
    import logging
    log = logging.getLogger("startup-logging")
    log.setLevel(level=logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    log.addHandler(ch)

    # Initialize Event Cache settings
    events.EventCache.logger(log)
    events.EventCache.base_dir(base_dir)
    events.EventCache.keep(opts.keep_days)
    events.EventCache.check_cache(opts.check_cache)
    events.preload_cache(log, base_dir)

    # Start queue monitor and processing thread (starts its own Multiprocessing threads)
    queue_path = os.path.abspath(os.path.join(base_dir, "queue/"))
    if not os.path.exists(queue_path):
        print("ERROR: %s does not exist. Is motion running?" % queue_path)
        return False
    queue_quit = mp.Event()
    queue_thread = mp.Process(name="queue-thread",
                              target=queue.monitor_queue,
                              args=(logger_queue, base_dir, queue_quit, opts.max_cores))
    queue_thread.start()
    running_threads += [(queue_thread, queue_quit)]

    # Start API thread (may start its own threads to handle requests)
    api_quit = mp.Event()
    api_thread = mp.Process(name="api-thread",
                            target=api.run_api,
                            args=(logger_queue, base_dir, opts.host, opts.port, opts.debug))
    api_thread.start()
    running_threads += [(api_thread, api_quit)]

    # Wait until it is told to exit
    try:
        while True:
            time.sleep(10)
    except Exception as e:
        print("ERROR: %s" % e)
    except KeyboardInterrupt:
        print("Exiting due to ^C")

    # Tell the threads to quit
    for _thread, event in running_threads:
        event.set()

    # Wait until everything is done
    print("Waiting for threads to quit")
    for thread, _event in running_threads:
        thread.join()

    return True
