#!/usr/bin/env python
"""
MovieGuide reddit bot
"""

import praw
import re
from HTMLParser import HTMLParser
import sqlite3
import ConfigParser
import codecs
import time

import jsonapi
from author import write_review

user_agent = 'MovieGuide/0.2 (by /u/nandhp)'

# Post statuses in database
STATUS_WAITING = 0
STATUS_NOMATCH = 1
STATUS_PARTIAL = 2
STATUS_EXACT = 5

# Regular expressions for mangling post titles
spacere = re.compile(r'\s+', flags=re.UNICODE)
strip1re = re.compile(r'(TV|HD|Full(?: Movie| HD)?|Fixed|(?:1080|720)[pi]'
    +r'|\d+x\d+|YouTube|Part *[0-9/]+)', #|[a-z]* *sub(title)?s?)',
    flags=re.I|re.UNICODE)
yearre = re.compile(r'^(.*?) *[\[\(\{] *(18[89]\d|19\d\d|20[012]\d) *[\]\)\}]',
    flags=re.UNICODE)
strip2re = re.compile(r'\([^\)]*\)|\[[^\]]*\]',#|:.*| *[-,;] *$|^ *[-,;] *
    flags=re.I|re.UNICODE)
titlere = re.compile(r'\"(.+?)\"|^(.+)$', flags=re.UNICODE)
#strip3re = re.compile(r'^The *', flags=re.I|re.UNICODE)
footersubre = re.compile(r'\{(\w+)\}', flags=re.UNICODE)

# For decoding HTML entities, which still show up in the praw output
_htmlparser = HTMLParser()

def fetch_new_posts(r, db, subreddit, mode='new'):
    """Process new submissions to the subreddit."""

    dbc = db.cursor()
    sr = r.get_subreddit(subreddit)

    # Get new submissions
    # Get correct PRAW function: new => get_new, top-year => get_top_from_year 
    sr_get = getattr(sr, 'get_'+'_from_'.join(mode.split('-')))
    print "Checking for %s posts in %s..." % (mode, str(sr))

    posts = sr_get(limit=100)
    count = 0
    for post in posts:
        # FIXME: Track the most recent post that we've handled, continue
        #        until we hit our last timestamp.
        # if lastsuccess < post.created_utc:
        #     lastsuccess = post.created_utc
        dbc.execute("SELECT * FROM history WHERE postid=?", [post.id])
        if not dbc.fetchone():
            title = _htmlparser.unescape(post.title)
            dbc.execute("INSERT INTO history(postid, posttitle, status)" +
                " VALUES (?, ?, ?)", [post.id, title, STATUS_WAITING])
            count += 1
    db.commit()
    print "Found %d new posts from %s." % (count, str(sr))

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
    ## FIXME: Split on popular punctuation [-,;.:] to handle extra words
    ## at the beginning of the title. (Do this instead of deleting after ":".
    #title = re.sub(strip3re, '', title).strip()

    # What did we get?
    return [title, year]

def handle_posts(r, db, imdb, footer):
    """
        Given a post object from praw:
        1. Check the database to see if the post has been already seen.
        2. Parse the title and look up movie data.
        3. Post the comment, if any.
        4. Save a record in the database.
    """ 

    dbc = db.cursor()
    pending = dbc.execute("SELECT postid, posttitle" +
        " FROM history WHERE status=?", [STATUS_WAITING]).fetchall()

    for row in pending:
        postid, posttitle = row
        # Check if item has already been handled
        print "Found http://redd.it/%s %s" % (postid, posttitle)

        # Parse item titles
        title, year = parse_title(posttitle)
        print "Parsed title: %s (%s)" % (title, str(year))

        # Generate a review
        try:
            # Look up the record for this movie.
            movie = imdb.search(title, year=year)
            comment_text = write_review(movie)
            comment_status = STATUS_EXACT
        except jsonapi.IMDbError:
            # Wow; this movie doesn't exist at all.
            movie = None
            comment_text = None
            comment_status = STATUS_NOMATCH
        comment_id = None

        # FIXME: Trap SIGTERM for rest of iteration
        if comment_text is not None:
            def footersubfunc(match):
                """Substitution handler for comment footer."""
                txt = match.group(1)
                if txt == 'itemid':
                    return postid
                elif txt == 'score' and '_score' in movie:
                    return '%.2f' % (movie['_score'],)
                else:
                    return '(Error)'
            comment_text += "\n\n" + re.sub(footersubre, footersubfunc, footer)
            print comment_text
            # Post review as a comment
            post = praw.objects.Submission.from_id(r, postid)
            try:
                comment = post.add_comment(comment_text)
                comment_id = comment.id
            except praw.errors.APIException, e:
                if e.error_type == 'TOO_OLD':
                    print "[Can't post comment: archived by reddit]"
                else:
                    raise
        else:
            print "[Nothing to say]"

        # Update database entry
        movietitle = movie['title'] if movie else None
        dbc.execute("UPDATE history SET status=?, commentid=?, title=?" +
            " WHERE postid=?",
            [comment_status, comment_id, movietitle, postid])
        db.commit()
        time.sleep(5)

def main(interval=3):
    """Main function, monitor every three minutes."""

    # Load configuration file
    config = ConfigParser.SafeConfigParser()
    config.read(['movieguide.conf', 'movieguide.ini'])
    r_conf = dict((i, config.get('reddit', i))
        for i in ('username', 'password', 'subreddit', 'mode')) 
    s_conf = dict((i, config.get('settings', i))
        for i in ('database', 'imdburl'))
    # Load footer
    s_conf['footer'] = ''
    try:
        footerfile = config.get('settings', 'signature')
        if footerfile:
            f = codecs.open(footerfile, 'r', 'utf-8')
            s_conf['footer'] = f.read()
            f.close()
    except ConfigParser.NoOptionError:
        pass

    # Database for storing history
    print "Opening database..."
    db = sqlite3.connect(s_conf['database'])

    # Access reddit
    print "Connecting..."
    r = praw.Reddit(user_agent=user_agent)
    print "Logging in as %s..." % r_conf['username']
    r.login(username=r_conf['username'], password=r_conf['password'])

    # IMDb API
    imdb = jsonapi.IMDbAPI(s_conf['imdburl'])

    while True:
        # Download new posts from reddit
        fetch_new_posts(r, db, r_conf['subreddit'], r_conf['mode'])
        # Add reviews to new posts
        handle_posts(r, db, imdb=imdb, footer=s_conf['footer'])
        # Sleep a while
        now = time.time()
        delaysec = interval*60
        print "Sleeping until %s (%d min)" % \
            (time.ctime(now+delaysec), interval)
        time.sleep(delaysec)

if __name__ == '__main__':
    main()

