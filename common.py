from time import time, sleep

class RateLimit(object):
    """Rate-limit requests to an API."""

    def __init__(self, interval):
        self.last_access = 0
        self.interval = interval

    def wait(self):
        """Wait until the given interval has passed since the last call."""
        time_delta = self.last_access + self.interval - time()
        if time_delta > 0:
            sleep(time_delta)
        self.last_access = time()
