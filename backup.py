#!/usr/bin/env python

"""Back up the database (using HTTP POST)."""

from subprocess import Popen, PIPE
from cStringIO import StringIO
from gzip import GzipFile
import re, os, shutil, difflib, time, urllib2, urlparse, hashlib

def dump(filename):
    """Dump an sqlite3 database."""
    obj = Popen(['sqlite3', filename, '.dump'], stdout=PIPE)
    for i in obj.stdout:
        yield i.strip()
    obj.wait()
    assert obj.returncode == 0

def gzip(data):
    """Compress a string with gzip."""
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

def gunzip_file(pathname, checksum=None):
    """Decompress a file with gzip."""
    infh = GzipFile(pathname, mode='r')
    data = infh.read()
    infh.close()
    if checksum:
        assert hashlib.sha1(data).hexdigest() == checksum
    return data

def http_request(method, url, data, auth=(),
                 mimetype='application/octet-stream'):
    """Implementation of HTTP/WebDAV methods, including PUT and PROPFIND."""
    class MyRequest(urllib2.Request):
        """Request object for arbitrary HTTP/WebDAV methods. (PUT,
        PROPFIND, etc.)"""
        def get_method(self):
            return method

    password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
    if auth:
        password_mgr.add_password(None, url, auth[0], auth[1])
    opener = urllib2.build_opener(urllib2.HTTPBasicAuthHandler(password_mgr),
                                  urllib2.HTTPHandler)
    if method in ('PUT', 'POST'):
        assert data is not None
        request = MyRequest(url, data, headers={'Content-Type': mimetype})
    else:                       # A GET or PROPFIND request or something
        assert data is None
        request = MyRequest(url)
    obj = opener.open(request, timeout=2*60)
    code = obj.getcode()
    if method == 'GET':
        assert code == 200
    else:
        assert code >= 200 and code < 300
    return obj.read()

def run_backup(database_file, remote, auth=(), full_backup=False, min_size=0):
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
    if remote[-1] != '/':
        remote += '/'  # Always treat the URL as being to a directory
    filename = urlparse.urljoin(remote, filename)
    #print filename

    # Send message
    if True:
        print "  Sending %d bytes..." % len(message)
        http_request('PUT', filename, message, auth)
        print "  Backup complete."
    else:
        print message.as_string()

    # Save new incremental file
    shutil.move(temp_file, incr_file)
    return True

FILENAME_RE = re.compile(r'^([0-9TZ]+)-([A-Z])-([0-9a-f]+)\.gz$', flags=re.I)
def parse_filename(filename):
    """Parse data (time, type, checksum) from a backup filename."""
    match = FILENAME_RE.search(os.path.basename(filename))
    if not match:
        return None
    return match.group(1).upper(), match.group(2).upper(), \
        match.group(3).lower()

def parse_propfind(xml):
    """Parse the XML result of a PROPFIND request."""
    def _text(node):
        """Return concatenation of child nodes (textNodes assumed)."""
        return ''.join(item.data for item in node.childNodes)

    from xml.dom.minidom import parseString
    propfind = parseString(xml)

    for item in propfind.documentElement.getElementsByTagName('d:response'):
        path = _text(item.getElementsByTagName('d:href')[0])
        size = int(_text(item.getElementsByTagName('d:getcontentlength')[0]))
        if path[-1] == '/' or item.getElementsByTagName('d:collection'):
            size = -1

        # Determine local filename and remote URL
        filename = path.rstrip('/').split('/')[-1]
        yield(filename, path, size)

def fetch_backup(localdir, remote, auth=(), keep_only=None):
    """Download updates to a backup directory from a WebDAV server."""
    if remote[-1] != '/':
        remote += '/'  # Always treat the URL as being to a directory

    # Do PROPFIND on the remote directory and parse the XML
    filenames = list(parse_propfind(http_request('PROPFIND', remote,
                                                 None, auth)))

    # Enumerate the items in the directory and download missing items
    fullbackups = []
    for filename, path, size in filenames:
        if size < 0:
            # Skip subdirectories (collections)
            print "%s seems to be a collection, skipping" % path
            continue

        # Determine local filename and remote URL
        filepath = os.path.join(localdir, filename)
        fileurl = urlparse.urljoin(remote, path)
        #filenames.append(fileurl)
        fndata = parse_filename(filename)
        print filename

        # Track full backups for use in expiration
        assert fndata[1] in 'FI'
        if fndata[1] == 'F' and keep_only:
            fullbackups.append(filename)
        # Check if the file is already downloaded
        if os.path.exists(filepath):
            if os.path.getsize(filepath) == size:
                print "  (Hit)"
                continue
            print "  (Invalid)"

        # FIXME: Check if file is expired, don't download

        print "  (Downloading...)"
        outfh = open(filepath, 'wb')
        outfh.write(http_request('GET', fileurl, None, auth))
        outfh.close()
        assert os.path.getsize(filepath) == size
        # Verify checksum (fndata[2] = checksum)
        gunzip_file(filepath, fndata[2])
        print "  (OK)"

    # Delete expired files
    if keep_only and len(fullbackups) > keep_only:
        fullbackups.sort()
        threshold = fullbackups[-keep_only]
        for filename, path, size in filenames:
            if size < 0 or filename >= threshold:
                continue
            # Determine local filename and remote URL
            filepath = os.path.join(localdir, filename)
            fileurl = urlparse.urljoin(remote, path)
            # Delete the URL and the file
            print "Deleting %s" % filename
            http_request('DELETE', fileurl, None, auth)
            if os.path.exists(filepath):
                os.remove(filepath)

def restore_backup(localdir, outname):
    """Restore a database backup from a local backup directory."""

    # Enumerate data files and find most recent set of full +
    # incremental backups
    files = []
    for filename in sorted(os.listdir(localdir)):
        pathname = os.path.join(localdir, filename)
        if os.path.isdir(pathname):
            print "%s is a directory: skipping." % filename
            continue
        fndata = parse_filename(filename)
        if not fndata:
            print "%s has invalid filename: skipping." % filename
            continue
        datatype = fndata[1]

        if datatype == 'F':
            # A newer full backup; clear the list of files
            files = []
        if datatype in 'FI':
            files.append((filename, pathname, fndata))
        else:
            print "%s has invalid datatype '%s'" % (filename, datatype)

    # Process the selected batch of files
    for i, (filename, pathname, fndata) in enumerate(files):
        print filename

        # Decompress the backup file
        data = gunzip_file(pathname, fndata[2]) # fndata[2] = checksum

        # The first file should always be the full backup
        if i == 0:
            outfh = open(outname, 'w')
            outfh.write(data)
            outfh.close()
        else:
            obj = Popen(['patch', outname], stdin=PIPE)
            obj.stdin.write(data)
            obj.stdin.close()
            obj.wait()
            assert obj.returncode == 0
    print "Done"

def _main(argv):
    """Main entry point for command-line usage"""
    def _parse_userandpass(data):
        """Parse USERNAME:PASSWORD argument to --auth."""
        authdata = tuple(data.split(':', 1))
        assert len(authdata) == 2
        return authdata
    parser = ArgumentParser()
    parser.add_argument('--remote', metavar='URL', type=str,
                        default='http://www.myserver.example/dav/backup',
                        help='URL of remote directory')
    parser.add_argument('--auth', metavar='USERNAME:PASSWORD',
                        type=_parse_userandpass,
                        help='Username and password for remote directory')
    subparsers = parser.add_subparsers()
    backup = subparsers.add_parser('backup',
                                   help='Perform a manual backup')
    backup.add_argument('dbfile', metavar='DBFILE', type=str, nargs='?',
                        default='movieguide.db',
                        help='Database file to back up')
    backup.add_argument('--full', action='store_true', default=False,
                        help='Perform full backup instead of incremental')
    fetch = subparsers.add_parser('fetch',
                                  help='Fetch data from the remote backup')
    fetch.add_argument('--keep-only', metavar='NUMBER', type=int, default=None,
                       help='Number of full backups to keep')
    fetch.add_argument('localdir', metavar='DIRECTORY',
                       help='Location of local backup')
    restore = subparsers.add_parser('restore',
                                    help='Restore from backup to STDOUT')
    restore.add_argument('localdir', metavar='DIRECTORY',
                         help='Location of local backup')
    restore.add_argument('outfile', metavar='FILE',
                         help='Location of output file')
    backup.set_defaults(mode='backup')
    fetch.set_defaults(mode='fetch')
    restore.set_defaults(mode='restore')

    args = parser.parse_args(argv)
    if args.mode == 'backup':
        run_backup(args.dbfile, args.remote, args.auth, full_backup=args.full)
    elif args.mode == 'fetch':
        assert args.keep_only is None or args.keep_only > 0
        fetch_backup(args.localdir, args.remote,
                     args.auth, keep_only=args.keep_only)
    elif args.mode == 'restore':
        restore_backup(args.localdir, args.outfile)
    else:
        raise NotImplementedError('Unknown mode: %s' % args.mode)

if __name__ == '__main__':
    from argparse import ArgumentParser
    import sys
    _main(sys.argv[1:])
