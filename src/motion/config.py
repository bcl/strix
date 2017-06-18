import os

class MotionConfig():
    """ Parse a motion configuration file into dicts

    Last key wins. Threads are stored in self.thread["thread-N"]
    """
    config = {}
    thread = {}
    _thread_n = 0

    def thread_n(self):
        """ Return an incrementing thread-N string

        :returns: str
        """
        self._thread_n += 1
        return "thread-%d" % self._thread_n

    def split(self, s):
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

    def parse(self, config_path):
        """ Parse a motion config file

        :returns: dict
        """
        with open(config_path) as f:
            return dict([
                 self.split(line)
                 for line in f.readlines()
                 if line.strip() and not line.startswith("#")])

    def __init__(self, config_path):
        self.config = self.parse(config_path)
        for t in filter(lambda k: k.startswith("thread"), self.config.keys()):
            thread_path = self.config[t]
            if not thread_path.startswith("/"):
                # Turn the relative path into an absolute one using the config_path
                thread_path = os.path.abspath(os.path.join(os.path.dirname(config_path), thread_path))
            self.thread[t] = self.parse(thread_path)
