# cmdline.py
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
import argparse

version = "DEVEL"

def parser() -> argparse.ArgumentParser:
    """ Return the ArgumentParser"""

    parser = argparse.ArgumentParser(description="Motion Camera Web Interface")

    required = parser.add_argument_group("required arguments")
    required.add_argument("-c", "--config",
                          help="Path to motion.conf",
                          required=True, metavar="MOTION")

    # optional arguments
    optional = parser.add_argument_group("optional arguments")
    optional.add_argument("-H", "--host",
                          help="Host or IP to bind to (127.0.0.1)",
                          metavar="HOSTNAME|IP",
                          default="127.0.0.1")
    optional.add_argument("-P", "--port",
                          help="Post to bind to (8000)",
                          metavar="PORT",
                          default=8000)
    optional.add_argument("-n", "--noqueue",
                          help="Do not process queue events",
                          action="store_true", default=False)
    optional.add_argument("-l", "--log",
                          help="Path to logfile (/var/tmp/strix.log)",
                          metavar="LOGFILE",
                          default="/var/tmp/strix.log")

    # add the show version option
    parser.add_argument("-V", help="show program's version number and exit",
                      action="version", version=version)

    return parser
