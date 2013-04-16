#!/usr/bin/env python
"""
Python interface to the JSON API implemented by imdb/wsgi.py
"""

import json
import urllib2
import urllib
from time import time, sleep

user_agent = 'MovieGuide-jsonapi/0.1'

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

    last_access = 0
    interval = 1

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def search(self, query, year=None):
        """Perform a query via the API and return the results."""

        # Wait an interval between requests
        time_delta = self.last_access + self.interval - time()
        if time_delta > 0:
            sleep(time_delta)
        self.last_access = time()

        # Build URL
        data = {'q': unicode(query).encode('utf-8')}
        if year:
            data['y'] = str(year)
        url = '%s?%s' % (self.endpoint, urllib.urlencode(data))

        # Request results
        if True:
            headers = {'User-Agent': user_agent}
            req = urllib2.Request(url, None, headers)
            response = urllib2.urlopen(req)
            data = response.read()
        else:
            data = sample_data

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

sample_data = """{"rating": ["0000011102", 669, "6.3"], "genres": ["Comedy", "Drama", "Family"], "color_info": "Color", "plot": ["Zooey and Alec Morrison are a married couple who are struggling to bridge the painful gap that is developing between them. Unable to conceive, the Morrisons await confirmation of a child to foster. One day, a seven years old boy who calls himself Eli appears on their doorstep quite mysteriously, explaining the foster agency has sent him. The boy is old beyond his years and it becomes apparent that he is the listening ear amongst the couple's marriage breakdown. Eli offers moral support and idealistic suggestions to his foster parents on how to repair and re-kindle their love for each other. The couple begin to rebuild their foundations at home, at work and emotionally until they find the love they once had for each other. But all may not be as it seems...", null], "_score": 0.9, "title": "Foster (2011)", "cast": [["Maurice Cole", "Eli", 1, null], ["Toni Collette", "Zooey", 2, null], ["Ioan Gruffudd", "Alec", 3, null], ["Hayley Mills", "Mrs Lange", 4, null], ["Richard E. Grant", "Mr Potts", 5, null], ["Anne Reid", "Diane", 6, null], ["Daisy Beaumont", "Sarah", 8, null], ["Bobby Smalldridge", "Samuel", 10, null], ["Tim Beckmann", "Jim", null, null], ["Geoffrey Beevers", "Man in suit", null, null], ["Jeremy Child", "John Burns", null, null], ["Ed Coleman", "Lego Worker", null, null], ["Kenneth Collard", "Doctor", null, null], ["Barry Jackson", "Tom Jenkins", null, null], ["Richard James", "Doctor", null, null], ["Akira Koieyama", "Japanese buyer", null, null], ["Siu Hun Li", "Delivery Man", null, null], ["Dan Mersh", "Bank Manager", null, null], ["Robert Morgan", "Mr. Carter", null, null], ["Nish Nathwani", "Taxi Driver", null, null], ["Habte. Tsion", "Young Girl", null, null], ["Helen Anderson", "Headmistress", null, null], ["Annabelle Dowler", "Mother", null, null], ["Esme Folley", "Receptionist", null, null], ["Haruka Kuroda", "Translator", null, null], ["Ella-Pearl Marshall-Pinder", "Little Girl", null, null], ["Audrey Newman", "Audrey", null, null], ["Jane Perry", "June", null, null], ["Jo Wyatt", "Jane", null, null]], "directors": [["Jonathan Newman", null, null, null]], "writers": [["Jonathan Newman", null, null, "  (written by)"]], "certificates": ["PG", "USA"], "running_time": 90}"""

if __name__ == '__main__':
    iface = IMDbAPI('http://localhost:8051/imdb')
    print iface.search('Foster')

