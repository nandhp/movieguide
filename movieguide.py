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
                       r'(?:1080|720|480|360|240)[pi]|' +
                       r'YouTube|Netflix|\d+x\d+|' +
                       r'^ *[\[\{]* *IJW *[\]\}:]*)',
                       #|[a-z]* *sub(title)?s?)',
                       flags=re.UNICODE|re.I)
YEAR_RE = re.compile(r'^(.*?) *[\[\(\{] *(18[89]\d|19\d\d|20[012]\d)' +
                     r' *[\]\)\}]', flags=re.UNICODE)
STRIP2_RE = re.compile(r'\([^\)]*\)|\[[^\]]*\]|\{[^\}]*\}',
                       #|:.*| *[-,;] *$|^ *[-,;] *
                       flags=re.UNICODE)
TITLE_RE = re.compile(r'"(.+?)"', flags=re.UNICODE)
#STRIP3_RE = re.compile(r'^The *', flags=re.UNICODE|re.I)
FOOTER_SUBST_RE = re.compile(r'\{(\w+)\}', flags=re.UNICODE)

def parse_title(desc):
    """Given a title of a post, try to extract a movie title and year."""
    title = None
    year = None

    # Strip useless data
    desc = SPACE_RE.sub(' ', desc).strip()
    desc = STRIP1_RE.sub('', desc).strip()

    # Try to find the year first, so we can discard everything after it.
    match = YEAR_RE.search(desc)
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
        #for group in match.group(1, 2):
        #    if group:
        #        title = group.strip()
        #        break
        title = match.group(1).strip()
    else:
        title = desc
    ## FIXME: Split on popular punctuation [-,;.:] to handle extra words
    ## at the beginning of the title. (Do this instead of deleting after ":".
    #title = STRIP3_RE.sub('', title).strip()

    # What did we get?
    return [title, year]

def config_get(config, section, key, default):
    """Get a value from a ConfigParser, with a default value if the
    key does not exist."""
    try:
        return config.get(section, key)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
        return default

class PostFilter(object):
    """Base class for post filters."""

    def __init__(self, include, exclude):
        self.include = include
        self.exclude = exclude

    def check(self, post):
        """Check if a post passes through the filter. A post is accepted by
        the filter if the include list is defined and the post is
        included or if the exclude list is defined and the post is not
        excluded.

        """
        if self.include is not None:
            # If include criteria is specified, we must match ("only")
            return self.satisfies(self.include, post)
        if self.exclude is not None:
            # If exclude criteria is specified, we must not match ("except")
            return not self.satisfies(self.exclude, post)
        return True

    def satisfies(self, criteria, post):
        """Check if a post satisfies a given criteria. Must be defined by the
        subclass.

        """
        raise NotImplementedError

class PostDomainFilter(PostFilter):
    """Filter posts by domain name."""

    def __init__(self, include, exclude):
        super(PostDomainFilter, self).__init__(include, exclude)
        self.include = self._parse_list(include)
        self.exclude = self._parse_list(exclude)

    @staticmethod
    def _parse_list(val):
        """Parse a list of domains (space-separated with possible commas)."""
        if val is None:
            return None
        domains = (j.strip(',;') for j in val.split())
        return [None if j == 'self' else j for j in domains]

    def satisfies(self, domainlist, post):
        """Check if a post's domain is in a given list, with special handling
        for self posts.

        """
        if None in domainlist and post.is_self:
            return True
        return post.domain in domainlist

class PostTitleRegExpFilter(PostFilter):
    """Filter posts by regular expressions applied to title."""

    def __init__(self, include, exclude):
        super(PostTitleRegExpFilter, self).__init__(include, exclude)
        self.include = re.compile(include, flags=re.UNICODE|re.I) \
                       if include is not None else None
        self.exclude = re.compile(exclude, flags=re.UNICODE|re.I) \
                       if exclude is not None else None

    def satisfies(self, regexp, post):
        """Check if a post's domain is in a given list, with special handling
        for self posts."""
        return regexp.search(post.decoded_title)

DEFAULT_ERRORDELAY = 60

def parse_bool(s):
    if isinstance(s, int) or isinstance(s, bool):
        return bool(s)
    s = str(s).strip().lower()
    if s in ('1', 't', 'true', 'y', 'yes'):
        return True
    if s in ('0', 'f', 'false', 'n', 'no'):
        return False
    raise ValueError("Can't parse boolean from %s" % (s,))

class IDMap(object):
    """Helper class to map string keys to numeric values."""

    def __init__(self, dbh):
        self.dbh = dbh

    def lookup(self, column, value):
        """Lookup the numeric value associated with the given string value for
        a particular column."""

        if value is None:
            return None
        dbc = self.dbh.cursor()
        dbc.execute("INSERT OR IGNORE INTO {0} ({0}) VALUES (?)"
                    .format(column), [value])
        dbc.execute("SELECT {0}_id FROM {0} WHERE {0}=?"
                    .format(column), [value])
        row = dbc.fetchone()
        assert row and row[0]
        return row[0]

class MovieGuide(object):
    """Class encapsulating variables for the bot."""

    def __init__(self):
        # Load configuration file
        config = ConfigParser.SafeConfigParser()
        config.read(['movieguide.conf', 'movieguide.ini'])
        r_conf = dict((i, config.get('reddit', i)) for i in
                      ('username', 'password',))
        s_conf = dict((i, config.get('settings', i)) for i in
                      ('imdburl','freebasekey'))

        # Database filename
        self.dbfile = config.get('settings', 'database')

        # Backup configuration
        self.backup_url = config_get(config, 'backup', 'url', None)
        self.backup_auth = (config_get(config, 'backup', 'username', None),
                            config_get(config, 'backup', 'password', None))
        if self.backup_auth[0] is None or self.backup_auth[1] is None:
            self.backup_auth = ()
        self.last_full = date.today()
        self.last_incr = datetime.min

        # Default listing settings: sort mode (new, top, etc.) and limit
        r_conf['mode'] = config_get(config, 'reddit', 'mode', 'new')
        r_conf['limit'] = config_get(config, 'reddit', 'limit', 100)
        r_conf['flairclass'] = config_get(config, 'reddit', 'flairclass', None)
        for key in ('exclude_domains', 'include_domains',
                    'exclude_title', 'include_title'):
            r_conf[key] = config_get(config, 'reddit', key, None)

        # FIXME: More general flair templating
        r_conf['genreflairsep'] = config_get(config, 'reddit',
                                             'genreflairsep', ', ')
        r_conf['genreflairdefault'] = config_get(config, 'reddit',
                                                 'genreflairdefault', None)

        # Title parsing settings
        r_conf['prefer_series'] = config_get(config, 'reddit',
                                             'prefer_series', False)

        # Heartbeat file
        self.heartbeatfile = config_get(config, 'settings', 'heartbeat', None)
        self.errordelay = DEFAULT_ERRORDELAY

        # Subreddits and subreddit settings
        self.fetch = []
        self.subreddits = {}
        for section in config.sections():
            if not section.startswith('/r/'):
                continue
            subreddits = section[3:]
            # Read options from section
            settings = dict((i, config_get(config, section, i, r_conf[i]))
                            for i in ('mode', 'limit', 'flairclass',
                                      'exclude_domains', 'include_domains',
                                      'exclude_title', 'include_title',
                                      'genreflairsep', 'genreflairdefault',
                                      'prefer_series'))
            settings['limit'] = int(settings['limit'])
            settings['prefer_series'] = parse_bool(settings['prefer_series'])

            settings['criteria'] = []

            # List of included/excluded domains
            for criteria_setting, criteria_class in (
                    ('domains', PostDomainFilter),
                    ('title', PostTitleRegExpFilter)
            ):
                criteria = criteria_class(
                    settings['include_' + criteria_setting],
                    settings['exclude_' + criteria_setting]
                )
                settings['criteria'].append(criteria)

            settings['genreflairsep'] = settings['genreflairsep'] \
                .decode('string_escape')

            self.fetch.append((subreddits, settings))
            for sr in subreddits.split('+'):
                self.subreddits[sr.lower()] = settings

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
        self.idmap = IDMap(self.db)

        # Access reddit
        print "Connecting..."
        self.reddit = praw.Reddit(user_agent=USER_AGENT)
        print "Logging in as %s..." % r_conf['username']
        self.reddit.login(username=r_conf['username'],
                          password=r_conf['password'])

        # IMDb API
        self.author = author.Author(imdburl=s_conf['imdburl'],
                                    freebasekey=s_conf['freebasekey'])

    def heartbeat(self):
        """Update heartbeat file (if configured) with current timestamp."""
        if self.heartbeatfile:
            heartbeatfh = open(self.heartbeatfile, 'w')
            heartbeatfh.write('ALLOK %s' % (time.time(),))
            heartbeatfh.close()
        self.errordelay = DEFAULT_ERRORDELAY

    def fetch_new_posts(self, subreddit, options):
        """Process new submissions to the subreddit."""

        mode = options['mode']
        limit = options['limit']
        criteria = options['criteria']

        # For decoding HTML entities, which still show up in the praw output
        _htmlparser = HTMLParser()
        # Database cursor
        dbc = self.db.cursor()

        sr = self.reddit.get_subreddit(subreddit)

        # Get new submissions
        # Get correct PRAW function: new => get_new,
        #                            top-year => get_top_from_year
        sr_get = getattr(sr, 'get_' + '_from_'.join(mode.split('-')))
        print "Checking for %d %s posts in %s..." % (limit, mode, str(sr))

        posts = sr_get(limit=limit)
        nfound = 0
        nskipped = 0
        for post in posts:
            post.decoded_title = _htmlparser.unescape(post.title)
            # Check post against configured criteria
            if not all(x.check(post) for x in criteria):
                nskipped += 1
                continue
            # FIXME: Track the most recent post that we've processed, continue
            #        until we hit our last timestamp.
            # if lastsuccess < post.created_utc:
            #     lastsuccess = post.created_utc
            dbc.execute("SELECT 1 FROM history WHERE postid=?", [post.id])
            if not dbc.fetchone():
                subreddit_id = self.idmap.lookup('subreddit',
                                                 post.subreddit.display_name)
                dbc.execute("INSERT INTO history(postid, subreddit_id, " +
                            "posttitle, status) VALUES (?, ?, ?, ?)",
                            [post.id, subreddit_id,
                             post.decoded_title, STATUS_WAITING])
                nfound += 1
        self.db.commit()
        print "Discovered %d new posts (%d skipped)." % (nfound, nskipped)

    def process_posts(self):
        """
            Given a post object from praw:
            1. Check the database to see if the post has been already seen.
            2. Parse the title and look up movie data.
            3. Post the comment, if any.
            4. Save a record in the database.
        """

        dbc = self.db.cursor()
        pending = dbc.execute("SELECT postid, subreddit, posttitle " +
                              "FROM history " +
                              "LEFT JOIN subreddit USING (subreddit_id) " +
                              "WHERE status=? ORDER BY postid DESC",
                              [STATUS_WAITING]).fetchall()

        print "Processing %d posts." % len(pending)

        # Don't spend more than two intervals processing posts
        end_time = time.time() + 2*INTERVAL*60

        for row in pending:
            postid, subreddit, posttitle = row
            # Check if item has already been processed
            print (u"Found http://redd.it/%s %s in /r/%s" %
                   (postid, posttitle, subreddit)).encode('utf-8')

            # Get per-subreddit settings
            settings = self.subreddits[subreddit.lower()]

            # Parse item titles
            title, year = parse_title(posttitle)
            if settings['prefer_series'] and '"' not in title:
                title = '"' + title + '"'
            print (u"Parsed title: %s (%s)" % (title, str(year))) \
                .encode('utf-8')

            # Generate a review
            movie, comment_text = self.author.process_item(title, year)
            comment_status = STATUS_NOMATCH if comment_text is None \
                else STATUS_EXACT
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
                comment_text += FOOTER_SUBST_RE.sub(footersubfunc, self.footer)
                print comment_text.encode('utf-8')
                # Post review as a comment, maybe updating flair
                post = praw.objects.Submission.from_id(self.reddit, postid)
                # FIXME: Skip if post.archived
                try:
                    if settings['flairclass'] is not None:
                        # FIXME: Organize, make more generic, flexible.
                        if 'genres' in movie and (movie['genres'] or settings['genreflairdefault']):
                            self.reddit.set_flair(subreddit, post,
                                                  settings['genreflairsep'].join(movie['genres']) if movie['genres'] else settings['genreflairdefault'],
                                                  settings['flairclass'])
                        # Update flair first: In event of failure,
                        # repeated flair updates are less harmful than
                        # repeated comments

                    # Post comment
                    comment = post.add_comment(comment_text)
                    comment_id = comment.id
                except praw.errors.APIException, exception:
                    if exception.error_type in ('TOO_OLD', 'DELETED_LINK',
                                                'THREAD_LOCKED'):
                        print "[Can't post comment: %s]" % \
                            (exception.error_type,)
                    else:
                        raise
            else:
                print "[Nothing to say]"

            # Update database entry
            movietitle = self.idmap.lookup('title',
                                           movie['title'] if movie else None)
            dbc.execute("UPDATE history SET status=?, commentid=?, " +
                        "title_id=? WHERE postid=?",
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
        for subreddit, options in self.fetch:
            self.fetch_new_posts(subreddit, options)
            time.sleep(2)

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
                if self.errordelay < 3600:
                    self.errordelay *= 2
            else:
                break

if __name__ == '__main__':
    MovieGuide().daemon()

