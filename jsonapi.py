#!/usr/bin/env python
"""
Python interface to the JSON API implemented by imdb/wsgi.py
"""

import json
import urllib2
import urllib

import common

USER_AGENT = 'MovieGuide-jsonapi/0.1'

class IMDbError(Exception):
    """Exception class for module."""
    def __init__(self, error, data):
        Exception.__init__(self)
        self.error = error
        self.data = data
    def __str__(self):
        return repr([self.error, self.data])

# Movie JSON
class IMDbAPI(object):
    """Interface to the JSON API implemented by imdb/wsgi.py"""

    ratelimit = common.RateLimit(1)

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def search(self, query, year=None):
        """Perform a query via the API and return the results."""

        self.ratelimit.wait()

        # Build URL
        data = {'q': unicode(query).encode('utf-8')}
        if year:
            data['y'] = str(year)
        url = '%s?%s' % (self.endpoint, urllib.urlencode(data))

        # Request results
        if True:
            headers = {'User-Agent': USER_AGENT}
            req = urllib2.Request(url, None, headers)
            response = urllib2.urlopen(req, timeout=8*60)
            data = response.read()
        #else:
        #    data = _SAMPLE_DATA

        # Parse response
        obj = json.loads(data)

        # If there are no votes, return 0 instead of N/A
        if 'imdbRating' in obj and 'imdbVotes' in obj and \
           (obj['imdbRating'] == 'N/A' or obj['imdbVotes'] == 'N/A'):
            obj['imdbRating'] = 0
            obj['imdbVotes'] = 0

        if 'title' in obj and '_score' in obj:
            return obj
        else:
            msg = obj['_error'] if '_error' in obj else 'Failed to parse data'
            raise IMDbError(msg, obj)

def _main():
    """Utility function for command-line testing."""
    iface = IMDbAPI('http://localhost:8051/imdb')
    print iface.search('Foster')

if __name__ == '__main__':
    _main()

