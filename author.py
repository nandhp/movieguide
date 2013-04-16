"""
Review-writing module for MovieGuide
"""

import urllib

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
    return '[USA:%s](https://en.wikipedia.org/wiki/%s)' % (text, url)

certificate_funcs = {
    'USA': certificate_usa,
}

def write_review(movie):
    """We found the movie. Write a review."""

    temp_list = []
    # Compute certificate (film classification)
    if movie['certificates'] and movie['certificates'][1] in certificate_funcs:
        certificate_transform = certificate_funcs[movie['certificates'][1]]
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
    review = '**[%s](%s)** %s    \n' % (movie['title'],
        imdb_url(movie), extra_info)
    # OPTIONAL LINE: actual title, if not original title, that was best match 
    if 'aka' in movie and movie['aka']:
        review += '&nbsp;&nbsp;&nbsp; a.k.a. **%s**    \n' % (movie['aka'],)

    # SECOND LINE: genres
    if movie['genres']:
        review += ', '.join(movie['genres']) + "\n\n"
    else:
        review += 'Unclassified\n\n'

    # THIRD LINE: Cast, directors, writers.
    names_strs = [', '.join(i[0] for i in movie[field][:4])
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
        plot_str = '> ' + movie['plot'][0]
        if movie['plot'][1]:
            plot_str += ' *[by %s]*' % movie['plot'][1]
    else:
        plot_str = "> *I have no idea what happens in this movie.*"

    review += "----\n\n**IMDb user rating:** %s\n%s\n\n----\n\n" % \
        (rating_str, plot_str)

    return review

