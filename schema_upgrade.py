#!/usr/bin/env python
import sqlite3
import sys
import os.path
from movieguide import IDMap

def convert(odb, ndb):          # old_db, new_db
    idmap = IDMap(ndb)          # movieguide.
    ocur = odb.cursor()
    ocur.execute('select * from history')
    rows = ocur.fetchall()
    ncur = ndb.cursor()
    with open(os.path.join(os.path.dirname(__file__), 'schema.txt')) as f:
        for l in f:
            ncur.execute(l)
    for i, row in enumerate(rows):
        row = dict(zip([x[0] for x in ocur.description], row))
        sys.stdout.write("\r%3d%% %-10s" % (i*100/len(rows), row['postid']))
        subreddit_id = idmap.lookup('subreddit', row['subreddit'])
        title_id = idmap.lookup('title', row['title'])
        assert (subreddit_id is None) == (row['subreddit'] is None)
        assert (title_id is None) == (row['title'] is None)
        ncur.execute("INSERT INTO history (postid, status, subreddit_id, " +
                     "posttitle, commentid, title_id) VALUES " +
                     "(?, ?, ?, ?, ?, ?)",
                     [row['postid'], row['status'], subreddit_id,
                      row['posttitle'], row['commentid'], title_id])
    ndb.commit()
    sys.stdout.write("\n");

def _main(argv):
    if len(argv) != 2:
        sys.stderr.write('Usage: %s <old_db> <new_db>\n')
        sys.exit(1)
    convert(sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2]))
if __name__ == '__main__':
    _main(sys.argv[1:])
