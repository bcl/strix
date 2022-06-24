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
import os

# Fix mimetypes so that it recognized m4v as video/mp4
import mimetypes
mimetypes.add_type("video/mp4", ".m4v")

from bottle import install, route, run, static_file, request, Response, JSONPlugin
from json import dumps
from threading import Thread

from . import logger
from .events import camera_events, EventCache, queue_events

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
def timestr_to_dt(rfc_str):
    return datetime.strptime(rfc_str, TIME_FORMAT)

def run_api(logging_queue, base_dir, cameras, host, port, debug, queue_rx):
    log = logger.log(logging_queue)
    log.info("Starting API", base_dir=base_dir, cameras=cameras, host=host, port=port, debug=debug)
    EventCache.logger(log)

    # Listen to queue_rx for new events
    th = Thread(target=queue_events, args=(log, queue_rx))
    th.start()

    @route('/')
    @route('/<filename>')
    def serve_root(filename="index.html"):
        return static_file(filename, root=os.path.dirname(__file__)+"/ui")

    @route('/motion/<filepath:path>')
    def serve_motion(filepath):
        return static_file(filepath, root=base_dir)

    @route('/api/cameras/list')
    def serve_cameras_list() -> Response:
        return {"cameras": cameras}

    @route('/api/events/<cameras>')
    def serve_events(cameras):
        # request.query is a bottle.MultiDict which pylint doesn't understand
        # pylint: disable=no-member
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

    # Use str as default in json dumps for objects like datetime
    install(JSONPlugin(json_dumps=lambda s: dumps(s, default=str)))
    run(host=host, port=port, debug=debug, server="gevent")

    th.join(30)
