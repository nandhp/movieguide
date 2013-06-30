"""
Review-writing module for MovieGuide
"""

import re, urllib, random

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

# From snudown, &().- removed
MARKDOWN_SPECIAL_RE = re.compile(r'[\\`*_{}\[\]#+!:|<>/^~]', flags=re.UNICODE)
def escape_markdown(data):
    """Escape characters with special meaning in Markdown."""
    def _replacement(match):
        """Backslash-escape all characters matching MARKDOWN_SPECIAL_RE."""
        return '\\' + match.group(0)
    return MARKDOWN_SPECIAL_RE.sub(_replacement, data)

QV_RE = re.compile(r"(?:'(.+?)(?: \([A-Z]+\))?'|_(.+?)_) ?\(qv\)",
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

# Invent plots
def invent_plot(movie):
    """Invent a plot summary if IMDb doesn't provide one."""
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
    generic_plot += [
        "In a world where there is no plot summary...",
        "This space intentionally left blank."
    ]
    rating = float(movie["rating"][2])
    if movie['certificates'] and 'X' in movie['certificates'][0]:
        return "Plot? It's X-rated, it doesn't need a plot."
    if 'Documentary' in movie['genres'] and random.random() < 0.8:
        return "It's a documentary. I'm guessing the plot is thin."
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

def write_review(movie):
    """We found the movie. Write a review."""

    temp_list = []
    # Compute certificate (film classification)
    if movie['certificates'] and movie['certificates'][1] in CERTIFICATE_FUNCS:
        certificate_transform = CERTIFICATE_FUNCS[movie['certificates'][1]]
        temp_list.append(certificate_transform(movie['certificates'][0]))
    # Compute color info
    if movie['color_info']:
        temp_list.append(movie['color_info'])

    # Compute running time
    if movie['running_time']:
        (hrs, mins) = (int(movie['running_time']/60), movie['running_time']%60)
        if hrs <= 0:
            temp_list.append("%d min" % (mins,))
        else:
            temp_list.append("%d h %d min" % (hrs, mins,))

    # FIRST LINE: title, IMDb link, certificate, color info, running time
    extra_info = ', '.join(temp_list)
    if extra_info:
        extra_info = '['+extra_info+']'
    review = '**[%s](%s)** %s    \n' % (escape_markdown(movie['title']),
        imdb_url(movie), extra_info)
    # OPTIONAL LINE: actual title, if not original title, that was best match 
    if 'aka' in movie and movie['aka']:
        review += '&nbsp;&nbsp;&nbsp; a.k.a. **%s**    \n' % \
                  (escape_markdown(movie['aka']),)

    # SECOND LINE: genres
    if movie['genres']:
        review += ', '.join(escape_markdown(g) for g in movie['genres'])
    else:
        review += 'Unclassified'
    review += "\n\n"

    # THIRD LINE: Cast, directors, writers.
    names_strs = [', '.join(munge_name(i[0]) for i in movie[field][:4])
        for field in 'cast', 'directors', 'writers']
    if movie['cast']:
        review += names_strs[0] + "    \n" # Cast
    if movie['directors']:
        plural = 'Director' if len(movie['directors']) == 1 else 'Directors'
        review += "%s: %s" % (plural, names_strs[1])
    if movie['writers']:
        if movie['directors']:
            review += '; '
        plural = 'Writer' if len(movie['writers']) == 1 else 'Writers'
        review += "%s: %s\n\n" % (plural, names_strs[2])
    elif movie['directors']:
        review += "\n\n"
    elif movie['cast']:
        review += "\n"

    # Compute star rating
    rating_int = int(round(float(movie["rating"][2])))
    if rating_int > 0:
        rating_str = "&#9733;" * rating_int + "&#9734;" * (10 - rating_int) \
            + " %s/10 (%s votes)" % \
            (movie["rating"][2], grouped_num(movie["rating"][1]))
    else:
        rating_str = "Unknown; awaiting five votes"
    # Plot summary
    if movie['plot'] and movie['plot'][0]:
        plot_str = '> ' + escape_markdown(strip_qv(movie['plot'][0]))
        if movie['plot'][1]:
            plot_str += ' *[by %s]*' % movie['plot'][1]
    else:
        # Can't find a plot; let's just make something up.
        plot_str = "> *%s*" % invent_plot(movie)

    review += "----\n\n**IMDb user rating:** %s\n%s\n\n----\n\n" % \
        (rating_str, plot_str)

    return review

def _main(title):
    """Utility function for command-line testing."""
    movie = jsonapi.IMDbAPI('http://localhost:8051/imdb').search(title)
    print invent_plot(movie)
    print
    print write_review(movie)

if __name__ == '__main__':
    import sys, jsonapi
    _main(sys.argv[1])
