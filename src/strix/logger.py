# logger.py
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
import sys
import logging
from logging.handlers import RotatingFileHandler, QueueListener, QueueHandler
import multiprocessing as mp

import structlog


structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

def listener(queue: mp.Queue, stop_event: mp.Event, log_path: str) -> None:
    handler = RotatingFileHandler(log_path, maxBytes=100*1024**2, backupCount=10)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    queue_listener = QueueListener(queue, handler)
    queue_listener.start()
    stop_event.wait()
    queue_listener.stop()


def log(queue: mp.Queue) -> structlog.BoundLogger:
    handler = QueueHandler(queue)
    root = structlog.get_logger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return root
