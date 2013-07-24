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
from datetime import datetime, date, timedelta

import jsonapi
import author, backup

USER_AGENT = 'MovieGuide/0.2 (by /u/nandhp)'

# Polling interval
INTERVAL = 3

# Post statuses in database
STATUS_WAITING = 0
STATUS_NOMATCH = 1
STATUS_PARTIAL = 2
STATUS_EXACT = 5

# Regular expressions for mangling post titles
SPACE_RE = re.compile(r'\s+', flags=re.UNICODE)
STRIP1_RE = re.compile(r'(TV|HD|Full(?: Movie| HD)?|Fixed|'+
                       r'(?:1080|720|480)[pi]|' +
                       r'YouTube|Netflix|\d+x\d+|Part *[0-9/]+|' +
                       r'^ *[\[\{]* *IJW *[\]\}:]*)',
                       #|[a-z]* *sub(title)?s?)',
                       flags=re.I|re.UNICODE)
YEAR_RE = re.compile(r'^(.*?) *[\[\(\{] *(18[89]\d|19\d\d|20[012]\d)' +
                     r' *[\]\)\}]', flags=re.UNICODE)
STRIP2_RE = re.compile(r'\([^\)]*\)|\[[^\]]*\]|\{[^\}]*\}',
                       #|:.*| *[-,;] *$|^ *[-,;] *
                       flags=re.UNICODE)
TITLE_RE = re.compile(r'\"(.+?)\"|^(.+)$', flags=re.UNICODE)
#STRIP3_RE = re.compile(r'^The *', flags=re.I|re.UNICODE)
FOOTER_SUBST_RE = re.compile(r'\{(\w+)\}', flags=re.UNICODE)

def parse_title(desc):
    """Given a title of a post, try to extract a movie title and year."""
    title = None
    year = None

    # Strip useless data
    desc = SPACE_RE.sub(' ', desc).strip()
    desc = STRIP1_RE.sub('', desc).strip()

    # Try to find the year first, so we can discard everything after it.
    match = re.search(YEAR_RE, desc)
    if match:
        year = int(match.group(2))
        desc = match.group(1)

    # Now that we've found the year, remove some additional data
    replacements = 1
    while replacements > 0:
        desc, replacements = STRIP2_RE.subn('', desc)
    desc = desc.strip()

    # Now pull out something that looks like a title.
    match = TITLE_RE.search(desc)
    if match:
        for group in match.group(1, 2):
            if group:
                title = group.strip()
    else:
        title = desc
    ## FIXME: Split on popular punctuation [-,;.:] to handle extra words
    ## at the beginning of the title. (Do this instead of deleting after ":".
    #title = STRIP3_RE.sub('', title).strip()

    # What did we get?
    return [title, year]

DEFAULT_ERRORDELAY = 60

class MovieGuide(object):
    """Class encapsulating variables for the bot."""

    def __init__(self):
        # Load configuration file
        config = ConfigParser.SafeConfigParser()
        config.read(['movieguide.conf', 'movieguide.ini'])
        r_conf = dict((i, config.get('reddit', i)) for i in
                      ('username', 'password',))
        s_conf = dict((i, config.get('settings', i)) for i in
                      ('imdburl',))

        # Database filename
        self.dbfile = config.get('settings', 'database')

        # Backup configuration
        try:
            self.backup_url = config.get('backup', 'url')
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            self.backup_url = None
        try:
            self.backup_auth = (config.get('backup', 'username'),
                                config.get('backup', 'password'))
        except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
            self.backup_auth = ()
        self.last_full = date.today()
        self.last_incr = datetime.min

        # Subreddit and mode (new, top, etc.) settings
        self.subreddit = config.get('reddit', 'subreddit')
        try:
            self.mode = config.get('reddit', 'mode')
        except ConfigParser.NoOptionError:
            self.mode = 'new'
        try:
            self.fetchlimit = int(config.get('reddit', 'limit'))
        except ConfigParser.NoOptionError:
            self.fetchlimit = 100

        # Heartbeat file
        try:
            self.heartbeatfile = config.get('settings', 'heartbeat')
        except ConfigParser.NoOptionError:
            self.heartbeatfile = None
        self.errordelay = DEFAULT_ERRORDELAY

        # Load footer
        self.footer = ''
        try:
            footerfile = config.get('settings', 'signature')
            if footerfile:
                footerfh = codecs.open(footerfile, 'r', 'utf-8')
                self.footer = footerfh.read()
                footerfh.close()
        except ConfigParser.NoOptionError:
            pass

        # Database for storing history
        print "Opening %s..." % self.dbfile
        self.db = sqlite3.connect(self.dbfile)

        # Access reddit
        print "Connecting..."
        self.reddit = praw.Reddit(user_agent=USER_AGENT)
        print "Logging in as %s..." % r_conf['username']
        self.reddit.login(username=r_conf['username'],
                          password=r_conf['password'])

        # IMDb API
        self.imdb = jsonapi.IMDbAPI(s_conf['imdburl'])

    def heartbeat(self):
        """Update heartbeat file (if configured) with current timestamp."""
        if self.heartbeatfile:
            heartbeatfh = open(self.heartbeatfile, 'w')
            heartbeatfh.write('OK %s' % (time.time(),))
            heartbeatfh.close()
        self.errordelay = DEFAULT_ERRORDELAY

    def fetch_new_posts(self, subreddit=None, mode=None):
        """Process new submissions to the subreddit."""

        # Default to instance parameters
        if subreddit is None:
            subreddit = self.subreddit
        if mode is None:
            mode = self.mode

        # For decoding HTML entities, which still show up in the praw output
        _htmlparser = HTMLParser()
        # Database cursor
        dbc = self.db.cursor()

        sr = self.reddit.get_subreddit(subreddit)

        # Get new submissions
        # Get correct PRAW function: new => get_new,
        #                            top-year => get_top_from_year 
        sr_get = getattr(sr, 'get_' + '_from_'.join(mode.split('-')))
        print "Checking for %s posts in %s..." % (mode, str(sr))

        posts = sr_get(limit=self.fetchlimit)
        count = 0
        for post in posts:
            # FIXME: Track the most recent post that we've processed, continue
            #        until we hit our last timestamp.
            # if lastsuccess < post.created_utc:
            #     lastsuccess = post.created_utc
            dbc.execute("SELECT * FROM history WHERE postid=?", [post.id])
            if not dbc.fetchone():
                title = _htmlparser.unescape(post.title)
                dbc.execute("INSERT INTO history(postid, posttitle, status)" +
                    " VALUES (?, ?, ?)", [post.id, title, STATUS_WAITING])
                count += 1
        self.db.commit()
        print "Discovered %d new posts." % count

    def process_posts(self):
        """
            Given a post object from praw:
            1. Check the database to see if the post has been already seen.
            2. Parse the title and look up movie data.
            3. Post the comment, if any.
            4. Save a record in the database.
        """

        dbc = self.db.cursor()
        pending = dbc.execute("SELECT postid, posttitle FROM history " +
                              "WHERE status=? ORDER BY postid DESC",
                              [STATUS_WAITING]).fetchall()

        print "Processing %d posts." % len(pending)

        # Don't spend more than two intervals processing posts
        end_time = time.time() + 2*INTERVAL*60

        for row in pending:
            postid, posttitle = row
            # Check if item has already been processed
            print (u"Found http://redd.it/%s %s" % (postid, posttitle)) \
                .encode('utf-8')

            # Parse item titles
            title, year = parse_title(posttitle)
            print (u"Parsed title: %s (%s)" % (title, str(year))) \
                .encode('utf-8')

            # Generate a review
            try:
                # Look up the record for this movie.
                movie = self.imdb.search(title, year=year)
                comment_text = author.write_review(movie)
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
                comment_text += "\n\n" + \
                                FOOTER_SUBST_RE.sub(footersubfunc, self.footer)
                print comment_text.encode('utf-8')
                # Post review as a comment
                post = praw.objects.Submission.from_id(self.reddit, postid)
                try:
                    comment = post.add_comment(comment_text)
                    comment_id = comment.id
                except praw.errors.APIException, exception:
                    if exception.error_type in ('TOO_OLD','DELETED_LINK'):
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
            self.db.commit()

            # Report heartbeat
            self.heartbeat()

            time.sleep(5)
            # If we're taking to long, pause and come back
            if time.time() > end_time:
                return False

        # We have finished processing all posts, report heartbeat and
        # return true.
        self.heartbeat()
        return True

    def do_backup(self):
        """Upload a database backup."""
        if self.backup_url:
            now = datetime.now()
            now_date = now.date()
            # Do a full backup right after midnight
            full = now_date != self.last_full
            # Insist on an incremental backup at least every 30 minutes,
            # but don't send a backup of less than 12 lines.
            min_size = 12 if now-self.last_incr < timedelta(minutes=30) else 0
            if backup.run_backup(self.dbfile,
                                 self.backup_url, self.backup_auth,
                                 full_backup=full, min_size=min_size):
                # The backup was not skipped (occured or no changes)
                self.last_incr = now
                if full:
                    self.last_full = now_date

    def do_one_loop(self):
        """Download new posts, post comments for a while, and send a backup."""
        # Perform backup
        self.do_backup()
        # No try...except! If backup fails, we want to be noticed and
        # fixed (We don't want to generate more data!)

        # Download new posts from reddit
        self.fetch_new_posts()

        # Add reviews to new posts
        done = self.process_posts()

        # Return True if process_posts has completed
        return done

    def main(self):
        """Main function for operation as a daemon."""
        while True:
            # Sleep a while, if done handling posts
            if self.do_one_loop():
                now = time.time()
                delaysec = INTERVAL*60
                print "Sleeping until %s (%d min)" % \
                    (time.ctime(now+delaysec), INTERVAL)
                time.sleep(delaysec)
            else:
                print "Not finished handling posts, not sleeping"

    def daemon(self):
        """Run as an auto-restarting daemon"""
        import traceback
        while True:
            try:
                self.main()
            except Exception, eobj:
                estr = "NOTOK %s\nException: %s\n%s\n" % \
                       (time.time(), eobj, traceback.format_exc())
                estr += "\nRestarting in %d seconds\n%s\n" % \
                    (self.errordelay, time.asctime())
                if self.heartbeatfile:
                    try:
                        outfh = open(self.heartbeatfile, 'w')
                        outfh.write(estr)
                        outfh.close()
                    except Exception, eobj:
                        estr += "\nAlso, %s while writing to %s.\n" % \
                                (eobj, self.heartbeatfile)
                print estr
                time.sleep(self.errordelay)
                self.errordelay *= 2
            else:
                break

if __name__ == '__main__':
    MovieGuide().daemon()

