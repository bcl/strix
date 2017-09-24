# api.py
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
from gevent import monkey; monkey.patch_all()
from datetime import datetime
import multiprocessing as mp
import os

from bottle import route, run, static_file, request, Response

from . import logger
from .events import camera_events

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
def timestr_to_dt(rfc_str: str) -> datetime:
    return datetime.strptime(rfc_str, TIME_FORMAT)

def run_api(logging_queue: mp.Queue, base_dir: str, host: str, port: int, debug: bool) -> None:
    log = logger.log(logging_queue)
    log.info("Starting API", base_dir=base_dir, host=host, port=port, debug=debug)

    @route('/')
    @route('/<filename>')
    def serve_root(filename: str = "index.html") -> Response:
        return static_file(filename, root=os.path.dirname(__file__)+"/ui")

    @route('/motion/<filepath:path>')
    def serve_motion(filepath: str) -> Response:
        return static_file(filepath, root=base_dir)

    @route('/api/events/<cameras>')
    def serve_events(cameras: str) -> Response:
        start = timestr_to_dt(request.query.get("start", "1985-10-26 01:22:00"))
        end   = timestr_to_dt(request.query.get("end", datetime.now().strftime(TIME_FORMAT)))
        offset= int(request.query.get("offset", "0"))
        limit = int(request.query.get("limit", "10"))
        camera_list = cameras.split(",")
#        log.debug("serve_events", camera_list=camera_list, start=str(start), end=str(end), offset=offset, limit=limit)

        events = {}
        for camera in camera_list:
            events[camera] = camera_events(log, base_dir, camera, start, end, offset, limit)

#        log.debug("serve_events", events=events)
        return {"start":    str(start),
                "end":      str(end),
                "offset":   offset,
                "limit":    limit,
                "events":   events}

    run(host=host, port=port, debug=debug, server="gevent")
