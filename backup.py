#!/usr/bin/env python

"""Back up the database (using HTTP POST)."""

from subprocess import Popen, PIPE
from cStringIO import StringIO
from gzip import GzipFile
from base64 import urlsafe_b64encode, urlsafe_b64decode
import os.path, shutil, difflib, urllib2, hashlib

def dump(filename):
    """Dump an sqlite3 database."""
    obj = Popen(['sqlite3', filename, '.dump'], stdout=PIPE)
    for i in obj.stdout:
        yield i.strip()
    obj.wait()
    assert(obj.returncode == 0)

def gzip(data):
    """Compress a string with gzip"""
    compressed_data = StringIO()
    gzfh = GzipFile(mode='w', fileobj=compressed_data)
    for i in data:
        gzfh.write(i + '\n')
    gzfh.close()
    buf = compressed_data.getvalue()
    compressed_data.close()
    return buf

def gunzip(data):
    """Uncompress a string with gzip"""
    compressed_data = StringIO(data)
    gzfh = GzipFile(mode='r', fileobj=compressed_data)
    buf = gzfh.read()
    gzfh.close()
    compressed_data.close()
    return buf

def run_backup(database_file, post_url, post_data,
               full_backup=False, min_size=0):
    """Back up the database."""

    # Filenames
    incr_file = database_file + '.incr'
    temp_file = incr_file + '.tmp'

    # Copy database
    shutil.copy(database_file, temp_file)

    # Load new data
    data = dump(temp_file)

    if not full_backup and os.path.exists(incr_file):
        # Load old data and perform incremental backup
        print "Performing incremental database backup:"
        old_data = dump(incr_file)
        data = tuple(difflib.unified_diff(tuple(old_data), tuple(data),
                                          lineterm=''))
    else:
        print "Performing full database backup:"
        full_backup = True

    if not data:
        print "  No changes."
        return True

    if min_size and len(data) < min_size: # Measured in lines
        print "  Not enough changes. (%d < %d lines)" % (len(data), min_size)
        return False

    # Encode message
    message = urlsafe_b64encode(gzip(data))
    postdata = post_data % {'type': 'F' if full_backup else 'I',
                            'data': message,
                            'checksum': hashlib.sha1(message).hexdigest()}

    # Send message
    if True:
        print "  Sending %d bytes..." % len(message)
        obj = urllib2.urlopen(post_url, postdata, timeout=2*60)
        assert(obj.getcode() == 200)
        print "  Backup complete."
    else:
        print message.as_string()

    # Save new incremental file
    shutil.move(temp_file, incr_file)
    return True

def restore_backup(filename, outdir):
    infh = open(filename, 'r')
    fnstr = '%05d%s.txt'
    lastfull = 0
    lastline = 0
    # Unpack all rows into data files
    for lineno, line in enumerate(infh):
        timestamp, data, datatype, checksum = line.strip().split(',')
        if datatype not in 'FI':
            print "Data at timestamp '%s' has invalid datatype '%s'" % \
                (timestamp, datatype)
            continue
        assert(lineno > 0)
        assert(hashlib.sha1(data).hexdigest() == checksum)
        outfn = os.path.join(outdir, fnstr % (lineno, datatype))
        outfh = open(outfn, 'wb')
        outfh.write(gunzip(urlsafe_b64decode(data)))
        outfh.close()
        if datatype == 'F':
            lastfull = lineno
        lastline = lineno
    # Apply patches starting from last full backup
    outfn = os.path.join(outdir, 'dump.txt')
    shutil.copy(os.path.join(outdir, fnstr % (lastfull, 'F')), outfn)
    for lineno in range(lastfull+1, lastline+1):
        infn = os.path.join(outdir, fnstr % (lineno, 'I'))
        obj = Popen(['patch', outfn, infn])
        obj.wait()
        assert(obj.returncode == 0)
    print "Restore completed in %s" % outfn

if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'backup':
        POST_URL = 'http://www.myserver.example/backup'
        POST_DATA = 'd=%(data)s&t=%(type)s&sha1=%(checksum)s'
        run_backup('movieguide.db', POST_URL, POST_DATA)
    elif sys.argv[1] == 'restore':
        restore_backup(sys.argv[2], 'restored-backup')
    else:
        print "Usage: %s {backup|restore}" % (sys.argv[0],)
