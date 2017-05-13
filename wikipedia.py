"""
Extract information from Wikipedia articles about movies.
"""

from HTMLParser import HTMLParser
import urllib2
import urllib
import re

import common

USER_AGENT = 'MovieGuide-wikipedia/0.1'

SKIPTAGS = ('table', 'sup')
NESTTAGS = ('div', 'span', 'a')
HEADTAGS = tuple('h'+str(i) for i in range(6))
SKIPSECTS = ("contents", "references", "see also", "external links", "notes")

SPACING_RE = re.compile(r'\s+', flags=re.UNICODE)

class WikipediaTextifier(HTMLParser):
    """
    Generate a plain text version of a Wikipedia article from a page like
    http://en.wikipedia.org/w/index.php?title=...&action=render
    """
    def __init__(self):
        HTMLParser.__init__(self)
        self.buffer = ''
        self.skip = 0
        self.skipsect = 0       # 10 = Skip introduction
        # Buffer for storing headings
        self.inheading = 0
        self.headingbuf = ""
        # List of external links
        self.links = []

    def _append(self, data):
        """Add data to the internal buffer"""
        if not self.skip and not self.skipsect:
            self.buffer += data

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        adict = dict(attrs)
        # Save external links
        if tag == 'a' and 'external' in adict.get('class', '') and \
                'href' in adict:
            self.links.append(adict['href'])

        # Track sections of the page to skip parsing
        if (self.skip and tag in NESTTAGS) or tag in SKIPTAGS:
            self.skip += 1
        elif tag in NESTTAGS:
            aclass = adict.get('class', '')
            astyle = adict.get('style', '')
            if 'thumbcaption' in aclass or 'quotebox' in aclass or \
                    'autonumber' in aclass or 'hatnote' in aclass or \
                    'display:none' in astyle or 'display: none' in astyle:
                self.skip += 1
        elif tag in ('p', 'br'):
            self._append("\n")

        # Special handling for settings
        elif tag in HEADTAGS:
            level = int(tag[1])
            if level <= self.skipsect:
                self.skipsect = 0
            self.inheading = level
            self.headingbuf = ""

    def handle_endtag(self, tag):
        tag = tag.lower()
        if (self.skip and tag in NESTTAGS) or tag in SKIPTAGS:
            self.skip -= 1
        elif tag in HEADTAGS:
            if self.inheading:
                self.headingbuf = self.headingbuf.replace('[edit]', '').strip()
                if self.headingbuf.lower() in SKIPSECTS:
                    self.skipsect = self.inheading
                self._append("\n\n%s %s\n\n" % ("#"*self.inheading,
                                                self.headingbuf))
                self.inheading = 0

    def handle_data(self, data):
        data = SPACING_RE.sub(' ', data)
        if self.inheading:
            self.headingbuf += data
        else:
            self._append(data)

    def handle_entityref(self, name):
        self.handle_data(self.unescape('&%s;' % (name,)))

    def handle_charref(self, name):
        self.handle_data(self.unescape('&#%s;' % (name,)))

# Regular expressions for the critical reception section
CRITICAL_RES = (
    re.compile(r'#+ (Critical.*)\s*\n((?:\s*[^#\s].+)+)',
               flags=re.UNICODE|re.I),
    re.compile(r'#+ (Reception.*)\s*\n((?:\s*[^#\s].+)+)',
               flags=re.UNICODE|re.I),
    re.compile(r'#+ (Reviews|Critics)\s*\n((?:\s*[^#\s].+)+)',
               flags=re.UNICODE|re.I),
)
PARA_RE = re.compile(r'\s*\n\s*', flags=re.UNICODE)
CRITICAL_KEYWORDS = (
    # Newspapers and magazines
    'Times', 'Herald', 'Chronicle', 'Post', 'Tribune', 'Globe', 'Mail',
    'Rolling', 'Stone', 'Edition', 'Today', 'Daily', 'Weekly',
    'Guide', 'Journal', 'Guardian',
    # 'Star', too ambiguous
    # Critics and aggregators
    'Ebert', 'Rotten', 'Metacritic', 'CinemaScore',
    # General keywords
    'eview', # Review, review, reviews, reviewed, previews, ...
    )

INTRO_RE = re.compile(r'^\s*((?:\s*[^#\s].+)+)', flags=re.UNICODE|re.I)
SUMMARY_RE = re.compile(r'the film(?:\'s )? (?!was)(?!(?:[a-z]* )+' +
                        '(?:premiere|release|box office))' +
                        r'|the stor[yi]|deals with|portray|depict|follow',
                        flags=re.UNICODE|re.I)

XREF_RE = {
    'Rotten Tomatoes': re.compile(r'//www\.rottentomatoes\.com/m/'),
    'Metacritic': re.compile(r'//www\.metacritic\.com/(tv|movie)/'),
    }

def url_from_curid(curid, lang='en'):
    """Generate a Wikipedia URL from a curid."""
    return "http://%s.wikipedia.org/w/index.php?curid=%s&action=render" % \
        (urllib.quote(lang), urllib.quote(curid))

def url_from_title(title, lang='en'):
    """Generate a Wikipedia URL from a page title."""
    return "http://%s.wikipedia.org/w/index.php?title=%s&action=render" % \
        (urllib.quote(lang), urllib.quote(unicode(title).encode('utf-8')))

class Wikipedia(object):
    """Interface to Wikipedia"""

    @staticmethod
    def parse(buf, url=None):
        """Parse a Wikipedia article for interesting information."""
        parser = WikipediaTextifier()
        parser.feed(buf)
        result = {
            'critical': None, 'criticalsection': None,
            'summary': None,
            'url': 'https' + url[url.find(':'):url.rfind('&')] \
                if url else None,
            }

        # Critical response
        for my_re in CRITICAL_RES:
            match = my_re.search(parser.buffer)
            if match:
                result['criticalsection'] = match.group(1)
                paras = PARA_RE.split(match.group(2))
                # Return the first paragraph containing a critical keyword
                for para in paras:
                    for keyword in CRITICAL_KEYWORDS:
                        if keyword in para:
                            result['critical'] = para.strip()
                            break
                    else:
                        continue
                    break
                else:
                    # If no such paragraph, return the first paragraph
                    result['critical'] = paras[0].strip()
                break

        # Summary from introduction
        match = INTRO_RE.search(parser.buffer)
        if match:
            paras = PARA_RE.split(match.group(1))
            # Return the first paragraph containing a plot summary keyword
            for para in paras:
                if SUMMARY_RE.search(para):
                    result['summary'] = para.strip()
                    break
            else:
                # If no such paragraph, return the first paragraph
                result['summary'] = paras[0].strip()

        # Avoid accidental JavaScript
        for data in (x for x in (result['summary'], result['critical']) if x):
            for check in ('function mfTemp', 'document.getElement',
                          '.className', ';}', '){', '{var'):
                assert check not in result['summary']

        # URLs for Rotten Tomatoes, Metacritic, etc.
        for url in parser.links:
            for name, re in XREF_RE.items():
                if re.search(url):
                    result[name + "_url"] = url

        return result

    ratelimit = common.RateLimit(5)

    def by_url(self, url):
        """Load a Wikipedia article by URL, parse it, and return a result."""

        self.ratelimit.wait()

        # Request results
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        try:
            response = urllib2.urlopen(req, timeout=8*60)
        except urllib2.HTTPError as e:
            if e.code < 400 or e.code > 499:
                raise
            data = ''
            print "Ignoring error %d from Wikipedia" % (e.code,)
        else:
            data = response.read().decode('utf-8', errors='replace')

        # Parse and return response
        return self.parse(data, url=url)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        for x in sys.argv[1:]:
            print repr(Wikipedia().by_url(url_from_curid(x)))
    else:
        print repr(Wikipedia.parse(sys.stdin.read()
                                   .decode('utf-8', errors='replace')))
