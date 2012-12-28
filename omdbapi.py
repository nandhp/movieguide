#!/usr/bin/env python
"""
Python interface with http://www.omdbapi.com/
"""

import json
import urllib2
import urllib
from time import time, sleep

user_agent = 'omdbapi.py/0.1'
last_access = 0
interval = 5

class OMDbError(Exception):
    """Exception class for module."""
    def __init__(self, error, data):
        Exception.__init__(self)
        self.error = error
        self.data = data
    def __str__(self):
        return repr([self.error, self.data])

# Movie JSON
def lookup(title=None, year=None, search=None, imdbid=None, fullplot=False):
    """Perform a query via The OMDb API and return the results."""

    # Wait an interval between requests
    global last_access
    time_delta = last_access+interval-time()
    if time_delta > 0:
        sleep(time_delta)
    last_access = time()

    # Build URL
    data = {'plot': 'full' if fullplot else 'short'}
    if title:
        data['t'] = str(title)
    if year:
        data['y'] = str(year)
    if search:
        data['s'] = str(search)
    if imdbid:
        data['i'] = str(imdbid)
    url = 'http://www.omdbapi.com/?%s' % urllib.urlencode(data)

    # Request results
    if True:
        headers = {'User-Agent': user_agent}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req)
        data = response.read()
    else:
        data = sample_search

    # Parse response
    obj = json.loads(data)
    if search and 'Search' in obj:
        return obj['Search']
    elif 'Response' not in obj or obj['Response'] != 'True':
        msg = obj['Error'] if 'Error' in obj else 'Failed to parse data'
        raise OMDbError(msg, obj)
    elif not search and 'Title' in obj:
        return obj
    else:
        raise OMDbError('Failed to parse data', obj)

def imdb_url(movie):
    """Build a URL to the IMDb page of a movie object."""
    return 'http://www.imdb.com/title/%s/' % movie['imdbID']

sample_data = """{"Title":"Foster","Year":"2011","Rated":"PG","Released":"04 Apr 2012","Runtime":"1 h 30 min","Genre":"Comedy, Drama, Family","Director":"Jonathan Newman","Writer":"Jonathan Newman","Actors":"Maurice Cole, Toni Collette, Ioan Gruffudd, Hayley Mills","Plot":"Zooey and Alec Morrison are a married couple who are struggling to bridge the painful gap that is developing between them. Unable to conceive, the Morrisons await confirmation of a child to foster. One day, a seven years old boy who calls himself Eli appears on their doorstep quite mysteriously, explaining the foster agency has sent him. The boy is old beyond his years and it becomes apparent that he is the listening ear amongst the couple's marriage breakdown. Eli offers moral support and idealistic suggestions to his foster parents on how to repair and re-kindle their love for each other. The couple begin to rebuild their foundations at home, at work and emotionally until they find the love they once had for each other. But all may not be as it seems...","Poster":"http://ia.media-imdb.com/images/M/MV5BMjMyNzUyMTI1NV5BMl5BanBnXkFtZTcwNTY1OTE3Nw@@._V1_SX300.jpg","imdbRating":"6.3","imdbVotes":"597","imdbID":"tt1629443","Response":"True"}"""
sample_search = """{"Search":[{"Title":"The Bourne Ultimatum","Year":"2007","imdbID":"tt0440963"},{"Title":"The Bourne Identity","Year":"2002","imdbID":"tt0258463"},{"Title":"The Bourne Supremacy","Year":"2004","imdbID":"tt0372183"},{"Title":"The Bourne Legacy","Year":"2012","imdbID":"tt1194173"},{"Title":"The Bourne Identity","Year":"1988","imdbID":"tt0094791"}]}"""
