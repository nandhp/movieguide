#!/usr/bin/env python

"""Back up the database (using HTTP POST)."""

from subprocess import Popen, PIPE
from cStringIO import StringIO
from gzip import GzipFile
import os.path, shutil, difflib, time, urllib2, urlparse, hashlib

def dump(filename):
    """Dump an sqlite3 database."""
    obj = Popen(['sqlite3', filename, '.dump'], stdout=PIPE)
    for i in obj.stdout:
        yield i.strip()
    obj.wait()
    assert(obj.returncode == 0)

def gzip(data):
    """Compress a string with gzip"""
    hasher = hashlib.sha1()
    compressed_data = StringIO()
    gzfh = GzipFile(mode='w', fileobj=compressed_data)
    for i in data:
        gzfh.write(i + '\n')
        hasher.update(i + '\n')
    gzfh.close()
    buf = compressed_data.getvalue()
    compressed_data.close()
    return hasher.hexdigest(), buf

def gunzip(data):
    """Uncompress a string with gzip"""
    compressed_data = StringIO(data)
    gzfh = GzipFile(mode='r', fileobj=compressed_data)
    buf = gzfh.read()
    gzfh.close()
    compressed_data.close()
    return hashlib.sha1(buf).hexdigest(), buf

def http_put(url, data, auth=(), mimetype='application/octet-stream'):
    class PutRequest(urllib2.Request):
        def get_method(self):
            return 'PUT'

    password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    if auth:
        password_mgr.add_password(None, url, auth[0], auth[1])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(password_mgr),
                                  urllib2.HTTPHandler)
    request = PutRequest(url, data, headers={'Content-Type': mimetype})
    obj = opener.open(request, timeout=2*60)
    code = obj.getcode()
    assert(code >= 200 and code < 300)

def run_backup(database_file, put_dir, auth=(), full_backup=False, min_size=0):
    """Back up the database."""

    # Filenames
    incr_file = database_file + '.incr'
    temp_file = incr_file + '.tmp'

    # Copy database
    shutil.copy(database_file, temp_file)

    # Load new data
    data = tuple(dump(temp_file))

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

    if min_size and len(data) < min_size: # Measured in lines, not bytes
        print "  Not enough changes. (%d < %d lines)" % (len(data), min_size)
        return False

    # Encode message
    checksum, message = gzip(data)

    # Generate output filename
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    typecode = 'F' if full_backup else 'I'
    filename = "%s-%s-%s.gz" % (now, typecode, checksum)
    if put_dir[-1] != '/':
        put_dir += '/'  # Always treat the URL as being to a directory
    filename = urlparse.urljoin(put_dir, filename)
    #print filename

    # Send message
    if True:
        print "  Sending %d bytes..." % len(message)
        http_put(filename, message, auth)
        print "  Backup complete."
    else:
        print message.as_string()

    # Save new incremental file
    shutil.move(temp_file, incr_file)
    return True

def restore_backup(filename, outdir):
    """Restore a database backup from a CSV file. (Currently obsolete.)"""
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
        assert(False) # gunzip changed to return checksum
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
        run_backup('movieguide.db',
                   'http://www.myserver.example/dav/backup',
                   ('MovieGuide', 'secret'))
    elif sys.argv[1] == 'restore':
        restore_backup(sys.argv[2], 'restored-backup')
    else:
        print "Usage: %s {backup|restore}" % (sys.argv[0],)
