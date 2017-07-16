# strix/motion/config.py
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
import os

from typing import Dict, Tuple

class MotionConfig():
    """ Parse a motion configuration file into dicts

    Last key wins. Threads are stored in self.thread["thread-N"]
    """
    config = {} # type: Dict
    thread = {} # type: Dict
    _thread_n = 0

    def thread_n(self) -> str:
        """ Return an incrementing thread-N string

        :returns: str
        """
        self._thread_n += 1
        return "thread-%d" % self._thread_n

    def split(self, s: str) -> Tuple[str, str]:
        """ Split the line into key and optional values.

        :returns: (k, v) where v may be ""
        """
        try:
            k, v = s.strip().split(" ", 1)

            # thread is a special case, can be more than 1
            if k == "thread":
                k = self.thread_n()
        except ValueError:
            k = s
            v = ""
        return (k, v)

    def parse(self, config_path: str) -> Dict:
        """ Parse a motion config file

        :returns: dict
        """
        with open(config_path) as f:
            return dict([
                 self.split(line)
                 for line in f.readlines()
                 if line.strip() and not line.startswith("#")])

    def __init__(self, config_path: str) -> None:
        self.config = self.parse(config_path)
        for t in filter(lambda k: k.startswith("thread"), self.config.keys()):
            thread_path = self.config[t]
            if not thread_path.startswith("/"):
                # Turn the relative path into an absolute one using the config_path
                thread_path = os.path.abspath(os.path.join(os.path.dirname(config_path), thread_path))
            self.thread[t] = self.parse(thread_path)
