#!/usr/bin/env python
"""
MovieGuide reddit bot
"""

import praw
import omdbapi
import re
import HTMLParser
import sqlite3
import ConfigParser
import codecs
from time import sleep

user_agent = 'movieguide.py/0.1 (written by /u/nandhp)'


STATUS_WAITING = 0
STATUS_NOMATCH = 1
STATUS_PARTIAL = 2
STATUS_EXACT = 5

# Load configuration file
config = ConfigParser.SafeConfigParser()
config.read(['movieguide.conf', 'movieguide.ini'])
username = config.get('reddit', 'username')
password = config.get('reddit', 'password')
default_subreddit = config.get('reddit', 'subreddit')
default_mode = config.get('reddit', 'mode')
database = config.get('settings', 'database')
footer = ''
try:
    footerfile = config.get('settings', 'signature')
    if footerfile:
        f = codecs.open(footerfile, 'r', 'utf-8')
        footer = f.read()
        f.close()
except ConfigParser.NoOptionError:
    pass

# Database for storing history
print "Opening database..."
db = sqlite3.connect(database)
dbc = db.cursor()

# Access reddit
print "Connecting..."
r = praw.Reddit(user_agent=user_agent)
print "Logging in as %s..." % username
r.login(username=username, password=password)

# For decoding HTML entities, which still show up in the praw output
htmlparser = HTMLParser.HTMLParser()

# Regular expressions for mangling post titles
spacere = re.compile(r'\s+')
strip1re = re.compile(r'(TV|HD|Full(?: Movie| HD)?|Fixed|(?:1080|720)[pi]'
    +r'|\d+x\d+|YouTube|Part *[0-9/]+|[a-z]* *sub(title)?s?)',
    flags=re.I)
yearre = re.compile(r'^(.*?) *[\[\(\{] *(18[89]\d|19\d\d|20[012]\d) *[\]\)\}]')
strip2re = re.compile(r'\([^\)]*\)|\[[^\]]*\]|:.*| *[-,;] *$|^ *[-,;] *',
    flags=re.I)
titlere = re.compile(r'\"(.+?)\"|^(.+)$',)
strip3re = re.compile(r'^The *', flags=re.I)

def process_movies(subreddit, mode='new'):
    """Process new submissions to the subreddit."""

    # Get new submissions
    sr = r.get_subreddit(subreddit)
    func = subreddit_get_func(sr, mode)
    print "Checking for %s posts in /r/%s..." % (mode, subreddit)
    lastsuccess = 0

    items = func(limit=100, url_data={'limit': 100})

    for item in items:
        # FIXME: Track the most recent post that we've handled, continue
        #        until we hit our last timestamp.
        # if lastsuccess < item.created_utc:
        #     lastsuccess = item.created_utc
        handle_post(item)
    print "No more items in /r/%s." % subreddit

def subreddit_get_func(sr, mode):
    """Return function for obtaining posts by specified mode."""
    if mode == 'new':
        return sr.get_new_by_date
    elif mode == 'rising':
        return sr.get_new_by_rising
    elif mode == 'hot':
        return sr.get_hot
    elif mode == 'top-all':
        return sr.get_top_from_all
    elif mode == 'top-year':
        return sr.get_top_from_year
    elif mode == 'top-month':
        return sr.get_top_from_month
    elif mode == 'top-week':
        return sr.get_top_from_week
    elif mode == 'top-day':
        return sr.get_top_from_day
    elif mode == 'top-hour':
        return sr.get_top_from_hour
    else:
        raise ValueError('Unknown subreddit fetch mode')


def handle_post(item):
    """
        Given a post object from praw:
        1. Check the database to see if the post has been already seen.
        2. Parse the title and look up movie data.
        3. Post the comment, if any.
        4. Save a record in the database.
    """ 
    # Check if item has already been handled
    print "Found http://redd.it/%s %s" % (item.id, item.title)
    dbc.execute("SELECT * FROM history WHERE postid=?", [item.id])
    old = dbc.fetchone()
    if old: # and old.status[1] != 0
        print "Already handled %s." % item.id
        return
    # Parse item titles
    title, year = parse_title(htmlparser.unescape(item.title))
    print "Parsed title: %s (%s)" % (title, str(year))

    # Generate a review
    comment_status, comment_text = handle_movie(title, year)
    comment_id = None
    if comment_text:
        print comment_text
        # Post review as a comment
        comment = item.add_comment(comment_text)
        comment_id = comment.id
    else:
        print "[Nothing to say]"

    # Save to database
    # if old: UPDATE
    dbc.execute("INSERT INTO history(postid, status, commentid) VALUES (?, ?, ?)",
                [item.id, comment_status, comment_id])
    db.commit()
    sleep(5)
        
def parse_title(desc):
    """Given a title of a post, try to extract a movie title and year."""
    title = None
    year = None

    # Strip useless data
    desc = re.sub(spacere, ' ', desc).strip()
    desc = re.sub(strip1re, '', desc).strip()

    # Try to find the year first, so we can discard everything after it.
    match = re.search(yearre, desc)
    if match:
        year = int(match.group(2))
        desc = match.group(1)

    # Now that we've found the year, remove some additional data
    replacements = 1 
    while replacements > 0:
        desc, replacements = re.subn(strip2re, '', desc)
    desc = desc.strip()

    # Now pull out something that looks like a title.
    match = re.search(titlere, desc)
    if match:
        for group in match.group(1, 2):
            if group:
                title = group.strip()
    else:
        title = desc
    # FIXME: Split on popular punctuation [-,;.:] to handle extra words
    # at the beginning of the title. (Do this instead of deleting after ":".
    title = re.sub(strip3re, '', title).strip()

    # What did we get?
    return [title, year]

def handle_movie(title, year):
    """Look up a movie and return a review."""
    try:
        # Look up the record for this exact movie.
        movie = omdbapi.lookup(title=title, year=year, fullplot=True)
        return (STATUS_EXACT, write_review(movie))
    except omdbapi.OMDbError:
        # If we didn't find anything, try a search.
        try:
            results = omdbapi.lookup(search=title)
            return (STATUS_PARTIAL, write_disambiguation(results))
        except omdbapi.OMDbError:
            # Wow; this movie doesn't exist at all.
            return (STATUS_NOMATCH, None)


def write_review(movie):
    """We found the movie. Write a review."""
    # Compute star rating
    rating_int = int(round(float(movie["imdbRating"])))
    rating_str = "&#9733;" * rating_int + "&#9734;" * (10 - rating_int)

    # Build comment
    return """**[%s (%s)](%s)** [%s, %s]    
%s    
%s %s/10 (%s votes)

%s    
Director: %s; Writer: %s

> %s

%s""" % (
        movie["Title"], movie["Year"], omdbapi.imdb_url(movie),
        movie["Rated"], movie["Runtime"], # movie["Released"],
        movie["Genre"],
        rating_str, movie["imdbRating"], movie["imdbVotes"],
        movie["Actors"], movie["Director"], movie["Writer"],
        movie["Plot"], #movie["Poster"],
        footer
    )

def write_disambiguation(results):
    """
        We didn't find an exact match, but we found some similar movies.
        Link to them.
    """ 
    comment = "Sorry, I didn't find an exact match. Similar titles include:\n\n"
    for movie in results:
        comment += "* [%s (%s)](%s)\n" \
            % (movie["Title"], movie["Year"], omdbapi.imdb_url(movie))
    comment += "\n"+footer
    return comment

if __name__ == '__main__':
    process_movies(default_subreddit, default_mode)

