#!/usr/bin/env python
"""
Python interface to Wikidata
"""

import json
import urllib2
import urllib

import common, wikipedia

USER_AGENT = 'MovieGuide-wikidata/0.1'

class WikidataItem(object):
    """Interface to a Wikidata item"""

    ratelimit = common.RateLimit(5)

    def __init__(self, itemid):
        self.key = 'Q%d' % (itemid,)

        self.ratelimit.wait()

        # Request item
        url = 'https://www.wikidata.org/entity/%s.json' % (self.key,)
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req, timeout=8*60)
        data = response.read()

        # Extract object from response
        self.obj = json.loads(data)
        assert self.obj['entities'] and self.key in self.obj['entities']
        self.obj = self.obj['entities'][self.key]

    def get_claim(self, prop):
        claims = self.obj['claims']
        if prop not in claims:
            return None
        values = []
        for v in claims[prop]:
            snak = v['mainsnak']
            if snak['datatype'] == 'string':
                assert snak['datavalue']['type'] == 'string'
                values.append(snak['datavalue']['value'])
            else:
                raise NotImplementedError
            # FIXME: handle rank, etc.
        return values

    def get_sitelink(self, wiki):
        sitelinks = self.obj.get('sitelinks', {})
        if wiki not in sitelinks:
            return None
        assert 'title' in sitelinks[wiki]
        return sitelinks[wiki]['title']

    def wikipedia_url(self, lang='en'):
        enwiki = self.get_sitelink(lang + 'wiki')
        return wikipedia.url_from_title(enwiki) if enwiki else None

    def wikidata_url(self):
        return "https://www.wikidata.org/wiki/%s" % (self.key,)

    # FIXME: Format these automatically using P1630.

    def freebase_url(self):
        #value = self.get_claim('P646') # Freebase identifier
        #return "http://www.freebase.com%s" % (value[0],) if value else None
        return None

    def rotten_tomatoes_url(self):
        value = self.get_claim('P646') # Rotten Tomatoes identifier
        return "http://www.rottentomatoes.com/%s" % (value[0],) \
            if value else None

    def metacritic_url(self):
        value = self.get_claim('P1712') # Metacritic ID
        return "http://www.metacritic.com/%s" % (value[0],) if value else None

    def netflix_url(self):
        value = self.get_claim('P1874') # Netflix Identifier
        return "http://movies.netflix.com/WiMovie/%s" % (value[0],) \
            if value else None

    def award_nominations(self):
        return []

    def awards_won(self):
        return []

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

# Run queries interactively at https://wdq.wmflabs.org/wdq/
class WikidataQuery(object):
    """Interface to the (experimental) WikidataQuery API"""

    ratelimit = common.RateLimit(5)

    def __init__(self):
        pass

    def by_imdbid(self, imdbid):
        """Query Wikidata via WikidataQuery API and return a result."""

        self.ratelimit.wait()

        # Build URL
        query = 'STRING[345:"%s"]' % (imdbid,)
        data = {'q': query}
        url = 'https://wdq.wmflabs.org/api?%s' % \
              (urllib.urlencode(data),)

        # Request results
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req, timeout=8*60)
        data = response.read()
        obj = json.loads(data)

        # Return response
        assert obj['status']['error'] == 'OK' and 'items' in obj
        assert len(obj['items']) == obj['status']['items']
        if obj['items']:
            return WikidataItem(max(obj['items']))
        else:
            return None

if __name__ == '__main__':
    import sys
    print repr(WikidataQuery().by_imdbid(sys.argv[1]))

