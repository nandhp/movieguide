"""
Extract information from Wikipedia articles about movies.
"""

from HTMLParser import HTMLParser
from time import time, sleep
import urllib2
import urllib
import re

USER_AGENT = 'MovieGuide-wikipedia/0.1'

SKIPTAGS = ('table', 'sup')
NESTTAGS = ('div')
HEADTAGS = tuple('h'+str(i) for i in range(6))
SKIPSECTS = ("contents", "references", "see also", "external links", "notes")
class WikipediaTextifier(HTMLParser):
    """
    Generate a plain text version of a Wikipedia article from a page like
    http://en.wikipedia.org/w/index.php?title=...&action=render
    """
    def __init__(self):
        HTMLParser.__init__(self)
        self.buffer = ''
        self.skip = 0
        self.skipsect = 10      # 10 = Skip introduction
        # Buffer for storing headings
        self.inheading = 0
        self.headingbuf = ""

    def _append(self, data):
        """Add data to the internal buffer"""
        if not self.skip and not self.skipsect:
            self.buffer += data

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if (self.skip and tag in NESTTAGS) or tag in SKIPTAGS:
            self.skip += 1
        elif tag == 'div':
            adict = dict(attrs)
            if 'class' in adict and 'thumbcaption' in adict['class']:
                self.skip += 1
        elif tag in ('p', 'br'):
            self._append("\n")
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
        if self.inheading:
            self.headingbuf += data
        else:
            self._append(data)

CRITICAL_RES = (re.compile(r'#+ (Critical.*)\s*\n\s*([^#\s].+)',
                           flags=re.UNICODE|re.I),
                re.compile(r'#+ (Reception.*)\s*\n\s*([^#\s].+)',
                           flags=re.UNICODE|re.I),
                re.compile(r'#+ (Reviews)\s*\n\s*([^#\s].+)',
                           flags=re.UNICODE|re.I),
                )
WIKI_URL = "http://%s.wikipedia.org/w/index.php?curid=%s&action=render"
class Wikipedia(object):
    """Interface to Wikipedia"""

    @staticmethod
    def parse(buf, url=None):
        """Parse a Wikipedia article for interesting information."""
        parser = WikipediaTextifier()
        parser.feed(buf)
        result = {
            'critical': None, 'criticalsection': None,
            'url': 'https' + url[url.find(':'):url.rfind('&')] \
                if url else None
            }
        # Critical response
        for my_re in CRITICAL_RES:
            match = my_re.search(parser.buffer)
            if match:
                result['critical'] =  match.group(2)
                result['criticalsection'] = match.group(1)
                break
        return result

    last_access = 0
    interval = 5

    def by_url(self, url):
        """Load a Wikipedia article by URL, parse it, and return a result."""

        # Wait an interval between requests
        time_delta = self.last_access + self.interval - time()
        if time_delta > 0:
            sleep(time_delta)
        self.last_access = time()

        # Request results
        headers = {'User-Agent': USER_AGENT}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req, timeout=8*60)
        data = response.read().decode('utf-8', errors='replace')

        # Parse and return response
        return self.parse(data, url=url)

    def by_curid(self, curid, lang='en'):
        """Load a Wikipedia article by 'curid' identifier; see `by_url`."""
        return self.by_url(WIKI_URL % (urllib.quote(lang),
                                       urllib.quote(curid)))

if __name__ == '__main__':
    import sys
    print repr(Wikipedia.parse(sys.stdin.read()
                               .decode('utf-8', errors='replace')))
    #print repr(Wikipedia().by_curid(23941708))
