#!/usr/bin/env python
"""
Python interface to the Freebase MQL API
"""

import json
import urllib2
import urllib
from time import time, sleep

USER_AGENT = 'MovieGuide-freebaseapi/0.1'

# Run queries interactively at http://www.freebase.com/query
QUERY = [{
        "/award/award_winning_work/awards_won": [{
                "award": None,
                "year": None,
                "id": None,
                "optional": True
                }],
        "/award/award_nominated_work/award_nominations": [{
                "award": None,
                "year": None,
                "id": None,
                "optional": True
                }],
        "/film/film/imdb_id": "tt0062622",
        "/film/film/netflix_id": [],
        "/film/film/trailers": [],
        "/common/topic/image": [{
                "id": None,
                "optional": True
                }],
        "wiki_en:key": [{
            "/type/key/namespace": "/wikipedia/en_id",
            "value": None,
            "optional": True
            }],
        "id": []
        }]

class FreebaseAPI(object):
    """Interface to the Freebase MQL API"""

    last_access = 0
    interval = 1

    def by_imdbid(self, imdbid):
        """Query freebase via the MQL API and return a result."""

        # Wait an interval between requests
        time_delta = self.last_access + self.interval - time()
        if time_delta > 0:
            sleep(time_delta)
        self.last_access = time()

        # Build URL
        query = QUERY
        query[0]["/film/film/imdb_id"] = imdbid
        data = {'query': json.dumps(query)}
        url = 'https://www.googleapis.com/freebase/v1/mqlread/?%s' % \
            (urllib.urlencode(data))

        # Request results
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req, timeout=8*60)
        data = response.read()

        # Parse and return response
        obj = json.loads(data)
        if 'result' in obj and len(obj['result']) > 0:
            return obj['result'][0]
        else:
            return None

if __name__ == '__main__':
    import sys
    print repr(FreebaseAPI().by_imdbid(sys.argv[1]))

