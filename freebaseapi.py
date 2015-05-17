#!/usr/bin/env python
"""
Python interface to the Freebase MQL API
"""

import json
import urllib2
import urllib

import common, wikipedia

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

class FreebaseTopic(object):
    def __init__(self, obj):
        self.obj = obj

    def wikipedia_url(self, lang='en'):
        if lang != 'en':
            return None
        enwiki = self.obj['wiki_en:key'] or []
        if len(enwiki) != 1:
            # Freebase returned multiple Wikipedia links; don't try to
            # disambiguate
            return None
        enwiki = enwiki[0]
        if not enwiki or not enwiki.get('value', None):
            return None
        return wikipedia.url_from_curid(enwiki['value'])

    def wikidata_url(self):
        return None

    def freebase_url(self):
        if 'id' not in self.obj or not self.obj['id']:
            return None
        return "http://www.freebase.com%s" % (self.obj['id'][0],)

    def rotten_tomatoes_url(self):
        return None

    def metacritic_url(self):
        return None

    def netflix_url(self):
        key = '/film/film/netflix_id'
        if key not in self.obj or not self.obj[key]:
            return None
        return "http://movies.netflix.com/WiMovie/%s" % (self.obj[key][0],)

    def award_nominations(self):
        return self.obj['/award/award_nominated_work/award_nominations']

    def awards_won(self):
        return self.obj['/award/award_winning_work/awards_won']

    def __repr__(self):
        return """<%s instance:
  Wikipedia: %s
  Wikidata: %s
  Freebase: %s
  Rotten Tomatoes: %s
  Metacritic: %s
  Netflix: %s
  Award nominations: %s
  Awards won: %s
>""" % (self.__class__.__name__, self.wikipedia_url(),
        self.wikidata_url(), self.freebase_url(),
        self.rotten_tomatoes_url(), self.metacritic_url(),
        self.netflix_url(), self.award_nominations(), self.awards_won())

class FreebaseAPI(object):
    """Interface to the Freebase MQL API"""

    ratelimit = common.RateLimit(1)
    key = None

    def __init__(self, key=None):
        self.key = key

    def by_imdbid(self, imdbid):
        """Query freebase via the MQL API and return a result."""

        self.ratelimit.wait()

        # Build URL
        query = QUERY
        query[0]["/film/film/imdb_id"] = imdbid
        data = {'query': json.dumps(query)}
        if self.key:
            data['key'] = self.key
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
            return FreebaseTopic(obj['result'][0])
        else:
            return None

if __name__ == '__main__':
    import sys
    print repr(FreebaseAPI().by_imdbid(sys.argv[1]))

