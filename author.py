"""
Review-writing module for MovieGuide
"""

import re, urllib, random
from datetime import date
import jsonapi, freebaseapi, wikipedia

def grouped_num(num, char=',', size=3):
    """Impose digit grouping on integer num"""
    my_str = str(int(num))
    out = []
    i = len(my_str)
    while i >= size:
        out.append(my_str[i-size:i])
        i -= size
    if i > 0:
        assert(i < size)
        out.append(my_str[0:i])
    return char.join(reversed(out))

# From snudown, &()- removed; only escape . after a digit.
MARKDOWN_SPECIAL_RE = re.compile(r'[\\`*_{}\[\]#+!:|<>/^~]|(?<=\d)\.',
                                 flags=re.UNICODE)
def escape_markdown(data):
    """Escape characters with special meaning in Markdown."""
    def _replacement(match):
        """Backslash-escape all characters matching MARKDOWN_SPECIAL_RE."""
        return '\\' + match.group(0)
    return MARKDOWN_SPECIAL_RE.sub(_replacement, data)

QV_RE = re.compile(r"(?:'([^']+?)(?: \([A-Z]+\))?'|_([^_]+?)_) ?\(qv\)",
                       flags=re.UNICODE)
def strip_qv(data):
    """Remove IMDb's qv-linking."""
    def _replacement(match):
        """Return first or second group from QV_RE."""
        return match.group(1) or match.group(2)
    return QV_RE.sub(_replacement, data)

def imdb_url(movie):
    """Build a URL to the IMDb page of a movie object."""
    return 'http://www.imdb.com/Title?%s' % \
        (urllib.quote_plus(movie['title'].encode('iso-8859-1')),)

# Transformations to apply to certificate strings
def certificate_usa(text):
    """Transform USA rating as appropriate for display."""
    if text.startswith('TV'):
        url = 'TV_Parental_Guidelines#Ratings'
    else:
        url = 'Motion_Picture_Association_of_America_film_rating_system#Ratings'
    return '[USA:%s](https://en.wikipedia.org/wiki/%s)' % \
        (escape_markdown(text), url)

CERTIFICATE_FUNCS = {
    'USA': certificate_usa,
}

YEAR_RE = re.compile(r'.*\(([0-9]+)[/\)]', flags=re.UNICODE)

# Invent plots
def invent_plot(movie):
    """Invent a plot summary if IMDb doesn't provide one."""
    def recent_movie(movie):
        """Movie is from this year (or later)"""
        # FIXME: January/February treat as previous year
        match = YEAR_RE.match(movie['title'])
        return (match and int(match.group(1)) >= date.today().year)
    if recent_movie(movie):
        return "Sorry, I don't have a plot summary for this movie. " + \
            "Maybe it's too new."
    generic_plot = [
        "I have no idea what happens in this movie.",
        "I haven't seen this movie; I don't know anything else about it.",
        "This is one of those movies where there's nothing helpful " +
        "printed on the back of the box.",
    ]
    bad_plot = [
        "It looks bad to me, but what do I know: I'm just a bot.",
        "Plot? I'm not sure this movie has a plot.",
        random.choice(generic_plot) + " But it looks bad."
    ]
    good_plot = [
        "People seem to like this movie. But writing plot summaries, " +
        "apparently, not so much.",
        "I don't know if there's a plot, but I hear it's not a bad movie.",
        random.choice(generic_plot) + " But it looks good."
    ]
    if len(movie['cast']) > 8:
        temp = random.choice(movie['cast'][6:])
        if temp[0] and temp[1] and random.random() < 0.25:
            temp = ("Well, I know %s plays %s in it. " +
                    "I don't know anything else about it.") % \
                (temp[0], temp[1])
        elif temp[0]:
            temp = "Hmm. Well, it has %s in it." % temp[0]
        else:
            temp = None
        if temp:
            generic_plot.append(temp)
            good_plot.append(temp + " Maybe it's good.")
    if len(movie['directors']) == 1 and movie['directors'][0][0]:
        temp = 'Directed by %s.' % movie['directors'][0][0]
        if 'M. Night Shyamalan' not in temp:
            temp += ' Who is not M. Night Shyamalan.'
        generic_plot.append(temp)
        bad_plot.append(temp + " Maybe that's a bad sign?")
    genre_plots = (
        (('Action', 'Adventure'), 'Action! Adventure! Really wild things! ' +
         'I just wish I knew what those things were....'),
        (('Mystery',), "The plot shall remain a mystery."),
        (('Romance',), 'Boy meets girl; boy loses girl; boy finds girl again.'
         + " It's a romance; they're all like that."),
        (('Documentary',), "It's a documentary. Maybe it's about movies " +
         'without plot summaries, or something like that.'),
        (('Biography',), "It's a biography. Maybe it's about someone who " +
         "writes plot summaries. Or, more appropriately, someone who doesn't."),
        (('Short',), "A short film. Maybe it's so short it has no plot."),
        (('Short',), "What is this? A film for ants?"),
        #(('Thriller',), "'Cause this is thriller, thriller night."),
        (('Experimental',), "'Experimental'? What does that even mean?"),
        (('Lifestyle',), "'Lifestyle'? Is that a real genre? " +
         "What does that even mean?"),
        )
    for genres, text in genre_plots:
        for genre in genres:
            if genre in movie['genres']:
                generic_plot.append(text)
                break
    generic_plot += [
        "In a world where there is no plot summary...",
        "This space intentionally left blank."
    ]
    rating = float(movie["rating"][2])
    if movie['certificates'] and 'X' in movie['certificates'][0]:
        return "Plot? It's X-rated, it doesn't need a plot."
    if rating > 0.1 and rating < 3:
        return random.choice(bad_plot)
    if rating > 8:
        return random.choice(good_plot)
    return random.choice(generic_plot)

def munge_name(name):
    """Escape markdown in (and possibly munge) names."""
    name = escape_markdown(name)
    if name == 'Nicolas Cage':
        return '[%s](/r/OneTrueGod)' % name
    return name

def write_imdb_vitals(movie):
    """Assemble summary information (title, genres, cast, ...) for a movie."""

    temp_list = []
    # Compute certificate (film classification)
    if movie['certificates'] and movie['certificates'][1] in CERTIFICATE_FUNCS:
        certificate_transform = CERTIFICATE_FUNCS[movie['certificates'][1]]
        temp_list.append(certificate_transform(movie['certificates'][0]))
    # Compute color info
    # if movie['color_info']:
    #    temp_list.append(movie['color_info'])

    # Compute running time
    if movie['running_time']:
        (hrs, mins) = (int(movie['running_time']/60), movie['running_time']%60)
        if hrs <= 0:
            temp_list.append("%d min" % (mins,))
        else:
            temp_list.append("%d h %d min" % (hrs, mins,))

    # FIRST LINE: title, IMDb link
    extra_info = ', '.join(temp_list)
    if extra_info:
        extra_info = '['+extra_info+']'
    url = imdb_url(movie)
    review = '### **[%s](%s)**\n\n' % (escape_markdown(movie['title']), url)
    # OPTIONAL: actual title, if not original title, that was the best match
    if 'aka' in movie and movie['aka']:
        review += '&nbsp;&nbsp;&nbsp; a.k.a. **%s**\n\n' % \
            (escape_markdown(movie['aka']),)

    # SECOND LINE: genres and extra info (certificate, running time)
    if movie['genres']:
        review += ', '.join(escape_markdown(g) for g in movie['genres'])
    else:
        review += 'Unclassified'
    review += ' %s\n\n' % (extra_info,)

    # THIRD LINE: Cast, directors, writers.
    names_strs = [', '.join(munge_name(i[0]) for i in movie[field][:4])
        for field in 'cast', 'directors', 'writers']
    if movie['cast']:
        review += names_strs[0] + "  \n" # Cast
    if movie['directors']:
        plural = 'Director' if len(movie['directors']) == 1 else 'Directors'
        review += "%s: %s" % (plural, names_strs[1])
    if movie['writers']:
        if movie['directors']:
            review += '  \n'
        plural = 'Writer' if len(movie['writers']) == 1 else 'Writers'
        review += "%s: %s" % (plural, names_strs[2])

    return { 'vitals': review, 'IMDb_url': url }

def write_imdb_plot(movie):
    """Assemble IMDb rating and plot summary for a movie."""

    review = {}

    # Compute star rating
    rating_int = int(round(float(movie["rating"][2])))
    if rating_int > 0:
        rating_str = "[](#movieguide_stars)**" + \
            "&#9733;" * rating_int + "&#9734;" * (10 - rating_int) \
            + "** **%s**/10 (%s votes)" % \
            (movie["rating"][2], grouped_num(movie["rating"][1]))
    else:
        rating_str = "Unknown; awaiting five votes"
    review['rating'] = "**IMDb rating:** %s" % (rating_str,)

    # Plot summary
    if movie['plot'] and movie['plot'][0]:
        review['plot'] = '> ' + escape_markdown(strip_qv(movie['plot'][0])) + \
            "\n(*%sIMDb*)" % (movie['plot'][1]+"/" if movie['plot'][1]
                              else '',)
    else:
        # Can't find a plot; let's just make something up.
        review['invented_plot'] = "> *%s*" % invent_plot(movie)

    return review

# Award canonicalization
CANONICAL_AWARD = {
    'Razzie Award': 'Golden Raspberry Award',
}
MAJOR_AWARDS = ('Academy Award', 'Golden Globe Award',
                'BAFTA Award', 'Golden Raspberry Award',
                # FIXME: There's probably a few other awards that
                # deserve special attention.
                )

def write_freebase_awards(fbdata):
    """Assemble award summary returned from Freebase."""

    def summarize_counts(counts):
        """Display [3,2] as '3 wins, 2 nominations' (skipping wins if none)"""
        return ("%(1)d wins and %(0)d nominations" if counts[1] else
                "%(0)d nominations") % \
                {'0': counts[0], '1': counts[1]}
    review = ""
    # Summarize awards/award nominations
    awards = {}
    awardval = 0
    counts = [0, 0]
    for award in fbdata['/award/award_nominated_work/award_nominations'] + \
            [None,] + fbdata['/award/award_winning_work/awards_won']:
        if not award:
            awardval = 1
            continue
        awardname = award['award'] if award['award'] else 'Untitled Award'
        awardcat = ''
        if ' for ' in awardname:
            awardname, awardcat = awardname.split(' for ', 1)
        if awardname in CANONICAL_AWARD:
            awardname = CANONICAL_AWARD[awardname]
        if awardname in MAJOR_AWARDS:
            awardname = '%s %s' % (award['year'], awardname)
            if awardname not in awards:
                awards[awardname] = {}
            awards[awardname][awardcat] = awardval
        else:
            counts[awardval] += 1
    # Display awards info
    if awards:
        review += "**Awards:**\n\n"
        for award in sorted(awards.keys()):
            review += "* **%s** " % (escape_markdown(award),)
            if '' not in awards[award] or len(awards[award]) > 1:
                review += 'for '
            cats = [('%s' if awards[award][k] else '*%s (nominated)*') % \
                        (escape_markdown(k.strip()),) \
                        for k in sorted(awards[award].keys())]
            review += '; '.join(cats)
            review += "\n"
        if counts[0]:
            review += "* Another %s\n" % summarize_counts(counts)
    elif counts[0]:
        review += "**Awards:** %s\n" % summarize_counts(counts)
    return { 'awards': review.strip() }

def write_freebase_xrefs(fbdata):
    """Assemble cross-references from Freebase data."""
    urls = {}
    for key, name, template in (("id", "Freebase",
                                 "http://www.freebase.com%s"),
                                ("/film/film/netflix_id", "Netflix",
                                 "http://movies.netflix.com/WiMovie/%s")):
        if key in fbdata and fbdata[key] and len(fbdata[key]):
            urls[name + "_url"] = template % (escape_markdown(fbdata[key][0]),)
    return urls

def write_wikipedia(fbdata, wpobj):
    """Assemble critical reception excerpt from Wikipedia article."""
    enwiki = fbdata['wiki_en:key']
    if not enwiki or 'value' not in enwiki or not enwiki['value']:
        return {}
    wikidata = wpobj.by_curid(enwiki['value'])
    review = {}

    if 'critical' in wikidata and wikidata['critical']:
        review['critical'] = "**Critical reception:**\n\n" + \
            "> %s\n(*Wikipedia*)" % (escape_markdown(wikidata['critical']),)

    if 'summary' in wikidata and wikidata['summary']:
        review['summary'] = "> %s\n(*Wikipedia*)" % \
            (escape_markdown(wikidata['summary']),)

    if 'url' in wikidata:
        review['Wikipedia_url'] = wikidata['url']
    for key in wikidata:
        if key.endswith('_url'):
            review[key] = wikidata[key]

    return review

REVIEW_SECTIONS = ('vitals+rating', 'plot|summary|invented_plot',
                   'critical+awards', 'links')
CROSSREF_URLS = ('IMDb', 'Freebase', 'Wikipedia', 'Rotten Tomatoes',
                 'Metacritic', 'Netflix')

class Author(object):
    """Class for holding state variables relating to writing reviews."""

    def __init__(self, imdburl='http://localhost:8051/imdb'):
        self.imdb = jsonapi.IMDbAPI(imdburl)
        self.freebaseapi = freebaseapi.FreebaseAPI()
        self.wikipedia = wikipedia.Wikipedia()

    def process_item(self, title, year):
        """Look up an item by title and year and write a review."""
        review = {}
        try:
            # Look up the record for this movie using the IMDb API.
            movie = self.imdb.search(title, year=year)
            review.update(write_imdb_vitals(movie))
            review.update(write_imdb_plot(movie))
        except jsonapi.IMDbError:
            # Wow; this movie doesn't exist at all.
            return (None, None)
        # Check IMDb ID for cross-referencing
        if 'imdbid' in movie:
            # We have an IMDb ID, cross-reference to Freebase
            fbdata = self.freebaseapi.by_imdbid(movie['imdbid'])
            if fbdata:
                review.update(write_freebase_awards(fbdata))
                review.update(write_freebase_xrefs(fbdata))
                review.update(write_wikipedia(fbdata, self.wikipedia))
        # A list of links to sources, etc.
        review['links'] = 'More info at ' + \
            ', '.join("[%s](%s)" % (i, review[i+'_url']) for i in CROSSREF_URLS
                      if i+'_url' in review and review[i+'_url']) + '.'
        if review:
            buf = []
            for i in REVIEW_SECTIONS:
                sect = []
                for j in i.split('+'):
                    for k in j.split('|'):
                        if k in review and review[k]:
                            sect.append(review[k].strip())
                            break
                sect = '\n\n'.join(i for i in sect if i).strip()
                if sect:
                    buf.append(sect)
            return (movie, "\n\n---\n\n".join(buf) + '  \n')
        return (movie, None)

def _main(title):
    """Utility function for command-line testing."""
    movie, comment = Author().process_item(title, None)
    print '[', invent_plot(movie), ']'
    print
    print comment

if __name__ == '__main__':
    import sys
    _main(sys.argv[1])
