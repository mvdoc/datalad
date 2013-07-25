#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""Interfaces to git and git-annex

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

from urlparse import urlparse

from .repos import *
from .db import load_db, save_db
from .network import fetch_page, parse_urls, filter_urls, \
      urljoin, download_url


def pprint_indent(l, indent="", fmt='%s'):
    return indent + ('\n%s' % indent).join([fmt % x for x in l])

# TODO: here figure it out either it will be a
# directory or not and either it needs to be extracted,
# and what will be the extracted directory name
def strippath(f, p):
    """Helper to deal with our mess -- strip path from front of filename f"""
    assert(f.startswith(p))
    f = f[len(p):]
    if f.startswith(os.path.sep):
        f = f[1:]
    return f

# TODO : add "memo" to avoid possible circular websites
def collect_urls(url, recurse=None, pages_cache=None, cache=False, memo=None):
    """Collects urls starting from url
    """
    page = (pages_cache and pages_cache.get(url, None)) or fetch_page(url, cache=cache)
    if pages_cache is not None:
        pages_cache[url] = page

    if recurse:
        if memo is None:
            memo = set()
        if url in memo:
            lgr.debug("Not considering %s since was analyzed before", url)
            return []
        memo.add(url)

    url_rec = urlparse(url)
    #
    # Parse out all URLs, as a tuple (url, a(text))
    urls_all = parse_urls(page, cache=cache)

    # Now we need to dump or recurse into some of them, e.g. for
    # directories etc
    urls = []
    if recurse:
        recurse_re = re.compile(recurse)

    lgr.debug("Got %d urls from %s", len(urls_all), url)

    for iurl, url_ in enumerate(urls_all):
        lgr.log(3, "#%d url=%s", iurl+1, url_)

        # separate tuple out
        u, a = url_
        recurse_match = recurse and recurse_re.search(u)
        if u.endswith('/') or recurse_match:     # must be a directory or smth we were told to recurse into
            if u in ('../', './'):
                lgr.log(8, "Skipping %s -- we are not going to parents" % u)
                continue
            if not recurse:
                lgr.log(8, "Skipping %s since no recursion" % u)
                continue
            if recurse_match:
                # then we should fetch the one as well
                u_rec = urlparse(u)
                u_full = urljoin(url, u)
                if u_rec.scheme:
                    if not (url_rec.netloc == u_rec.netloc and u_rec.path.startswith(rl_rec.path)):
                        # so we are going to a new page?
                        lgr.log(9, "Skipping %s since it jumps to another site from original %s" % (u, url))
                        #raise NotImplementedError("Cannot jump to other websites yet")
                        continue
                    # so we are staying on current website -- let it go
                lgr.debug("Recursing into %s, full: %s" % (u, u_full))
                new_urls = collect_urls(
                    u_full, recurse=recurse, pages_cache=pages_cache, cache=cache,
                    memo=memo)
                # and add to their "hrefs" appropriate prefix
                urls.extend([(os.path.join(u, url__[0]),) + url__[1:]
                             for url__ in new_urls])
            else:
                lgr.log(8, "Skipping %s since doesn't match recurse" % u)
        else:
            lgr.log(4, "Adding %s", url_)
            urls.append(url_)

    lgr.debug("Considering %d out of %d urls from %s"
              % (len(urls), len(urls_all), url))

    return urls

#
# Main loop
#
# TODO: formalize existing argument into option (+cmdline option?)
def rock_and_roll(cfg, existing='check',
                  dry_run=False, cache=False, db_name = '.page2annex'):
    """Given a configuration fetch/update git-annex "clone"
    """

    # Let's output summary stats at the end
    stats = dict([(k, 0) for k in
                  ['sections', 'urls', 'allurls', 'downloads',
                   'incoming_annex_updates', 'public_annex_updates', 'downloaded']])
    pages_cache = {}

    runner = Runner(dry=dry_run)
    # convenience shortcuts
    _call = runner.drycall

    dry_str = "DRY: " if dry_run else ""

    incoming = cfg.get('DEFAULT', 'incoming')
    public = cfg.get('DEFAULT', 'public')

    #
    # Initializing file structure
    #
    if not (os.path.exists(incoming) and os.path.exists(public)):
        lgr.debug("Creating directories for incoming (%s) and public (%s) annexes"
                  % (incoming, public))

        if not os.path.exists(incoming):
            _call(os.makedirs, incoming)
        if not os.path.exists(public):
            _call(os.makedirs, public)           #TODO might be the same

    description = cfg.get('DEFAULT', 'description')
    public_annex = AnnexRepo(public, runner=runner, description=description)

    if public != incoming:
        incoming_annex = AnnexRepo(incoming, runner=runner,
                                   description=description + ' (incoming)')
        # TODO: git remote add public to incoming, so we could
        # copy/get some objects between the two
    else:
        incoming_annex = public_annex

    # TODO: provide AnnexRepo's with the "runner"

    # TODO: load previous status info
    """We need

    incoming -- to track their mtime/size and urls.
      URLs might or might not provide Last-Modified,
      so if not provided, would correspond to None and only look by url change pretty much
      keeping urls would allow for a 'quick' check mode where we would only check
      if file is known

    public_incoming -- to have clear correspondence between public_filename and incoming (which in turn with url).
                   public_filename might correspond to a directory where we would
                   extract things, so we can't just geturl on it
    """

    db_path = os.path.join(incoming, db_name)
    if os.path.exists(db_path):
        db = load_db(db_path)
    else:
        # create fresh
        db = dict(incoming={},   # incoming_filename -> (url, mtime, size (AKA Content-Length, os.stat().st_size ))
                  public_incoming={}) # public_filename -> incoming_filename

    db_incoming = db['incoming']
    # reverse map: url -> incoming
    db_incoming_urls = dict([(v['url'], i) for i,v in db_incoming.iteritems()])
    db_public_incoming = db['public_incoming']

    # TODO: look what is in incoming for this "repository", so if
    # some urls are gone or changed so previous file is not there
    # we would clean-up upon exit

    # each section defines a separate download setup
    for section in cfg.sections():
        lgr.info("Section: %s" % section)
        stats['sections'] += 1

        # some checks
        add_mode = cfg.get(section, 'mode')
        assert(add_mode in ['download', 'fast', 'relaxed'])
        fast_mode = add_mode in ['fast', 'relaxed']

        repo_sectiondir = cfg.get(section, 'directory')

        full_incoming_sectiondir = os.path.join(incoming, repo_sectiondir)
        full_public_sectiondir = os.path.join(public, repo_sectiondir)

        if not (os.path.exists(incoming) and os.path.exists(public)):
            lgr.debug("Creating directories for section's incoming (%s) and public (%s) annexes"
                      % (full_incoming_sectiondir, full_public_sectiondir))
            _call(os.makedirs, full_incoming_sectiondir)
            _call(os.makedirs, full_public_sectiondir)           #TODO might be the same

        scfg = dict(cfg.items(section))

        incoming_destiny = scfg.get('incoming_destiny')
        # Fetching the page (possibly again! thus a dummy pages_cache)
        top_url = scfg['url'].replace('/./', '/')
        if '..' in top_url:
            raise ValueError("Some logic would fail with relative paths in urls, "
                             "please adjust %s" % scfg['url'])
        urls_all = collect_urls(top_url, recurse=scfg['recurse'], pages_cache=pages_cache, cache=cache)


        #lgr.debug("%d urls:\n%s" % (len(urls_all), pprint_indent(urls_all, "    ", "[%s](%s)")))

        # Filter them out
        urls = filter_urls(urls_all, **dict(
            [(k,scfg[k]) for k in
             ('include_href', 'exclude_href',
              'include_href_a', 'exclude_href_a')]))
        lgr.debug("%d out of %d urls survived filtering"
                 % (len(urls), len(urls_all)))
        if len(set(urls)) < len(urls):
            urls = sorted(set(urls))
            lgr.info("%d unique urls" % (len(urls),))
        lgr.debug("%d urls:\n%s"
                  % (len(urls), pprint_indent(urls, "    ", "[%s](%s)")))
        if scfg.get('check_url_limit', None):
            limit = int(scfg['check_url_limit'])
            if limit and len(urls) > limit:
                raise RuntimeError(
                    "Cannot process section since we expected only %d urls"
                    % limit)

        #
        # Process urls
        stats['allurls'] += len(urls)
        for href, href_a in urls:
            # bring them into the full urls, href might have been a full url on its own
            href_full = urljoin(top_url, href)
            lgr.debug("Working on [%s](%s)" % (href_full, href_a))

            incoming_updated = False
            incoming_downloaded = False

            # We need to decide either some portion of href path
            # should be "maintained", e.g. in cases where we recurse
            # TODO: make stripping/directories optional/configurable
            # so we are simply deeper on the same site
            href_dir = os.path.dirname(href_full[len(top_url):].lstrip(os.path.sep)) \
                if href_full.startswith(top_url) else ''

            # Download incoming and possibly get alternative filename from Deposit
            # It will adjust db_incoming in-place
            if (href_full in db_incoming_urls
                and (existing and existing == 'skip')):
                lgr.debug("Skipping attempt to download since %s known to db "
                          "already and existing='skip'" % href_full)
                incoming_filename = db_incoming_urls[href_full]
            else:
                incoming_filename, incoming_downloaded, incoming_updated, downloaded_size = \
                  download_url(href_full, incoming,
                               os.path.join(repo_sectiondir, href_dir),
                               db_incoming=db_incoming, dry_run=runner.dry, # TODO -- use runner?
                               fast_mode=fast_mode)
                stats['downloaded'] += downloaded_size

            full_incoming_filename = os.path.join(incoming, incoming_filename)

            try:
                public_filename = eval(scfg['filename'], {}, dict(filename=incoming_filename))
            except:
                raise ValueError("Failed to evaluate %r" % scfg['filename'])

            # Incoming might be an archive -- check and adjust public filename accordingly
            is_archive, public_filename = pretreat_archive(
                public_filename, archives_re=scfg.get('archives_re'))

            if incoming_updated and is_archive and fast_mode :
                # there is no sense unless we download the beast
                # thus redo now forcing the download
                lgr.info("(Re)downloading %(href_full)s since points to an archive, thus "
                         "pure fast mode doesn't make sense" % locals())
                incoming_filename_, incoming_downloaded, incoming_updated_, downloaded_size = \
                  download_url(href_full, incoming,
                               os.path.join(repo_sectiondir, href_dir),
                               db_incoming=db_incoming, dry_run=runner.dry,
                               fast_mode=False, force_download=True)
                assert(incoming_filename == incoming_filename_)
                stats['downloaded'] += downloaded_size
                incoming_updated = incoming_updated_ or incoming_updated

            stats['downloads'] += int(incoming_downloaded)
            if incoming_updated:
                if not dry_run:
                    _call(save_db, db, db_path)   # must go to 'finally'

            annex_updated = False
            # TODO: may be these checks are not needed and we should follow the logic all the time?
            if incoming_updated \
              or (not public_filename in db_public_incoming) \
              or (not lexists(join(public_annex.path, public_filename))):
                # Place the files under git-annex, if they do not exist already
                #if href.endswith('gz'):
                #    import pydb; pydb.debugger()

                # TODO: we might want to get matching to db_incoming stamping into db_public,
                #       so we could avoid relying on incoming_updated but rather comparison of the records
                #  argument #2 -- now if incoming_updated, but upon initial run annex_file fails
                #  for some reason -- we might be left in a state where "public_annex" is broken
                #  upon subsequent run where incoming_updated would be False.  So we really should keep
                #  stamps for both incoming and public to robustify tracking/updates
                incoming_annex_updated, public_annex_updated = \
                  annex_file(
                    href_full,
                    incoming_filename=incoming_filename,
                    incoming_annex=incoming_annex,
                    incoming_updated=incoming_updated,
                    is_archive=is_archive,
                    public_filename=public_filename,
                    public_annex=public_annex,
                    incoming_destiny=incoming_destiny,
                    add_mode=add_mode,
                    addurl_opts=scfg.get('addurl_opts', None),
                    runner=runner,
                    )

                db_public_incoming[public_filename] = incoming_filename
                annex_updated = incoming_annex_updated or public_annex_updated
                stats['incoming_annex_updates'] += int(incoming_annex_updated)
                stats['public_annex_updates'] += int(public_annex_updated)
            else:
                # TODO: shouldn't we actually check???
                lgr.debug("Skipping annexing %s since it must be there already and "
                          "incoming was not updated" % public_filename)

            # TODO: make save_db a handler upon exit of the loop one way or another
            if not dry_run and (annex_updated or incoming_updated):
                _call(save_db, db, db_path)

            stats['urls'] += 1

    stats_str = "Processed %(sections)d sections, %(urls)d (out of %(allurls)d) urls, " \
                "%(downloads)d downloads with %(downloaded)d bytes. " \
                "Made %(incoming_annex_updates)s incoming and %(public_annex_updates)s " \
                "public git/annex additions/updates" % stats

    _call(git_commit,
          incoming, files=[db_name] if os.path.exists(db_path) else [],
          msg="page2annex(incoming): " + stats_str)
    if incoming != public:
        _call(git_commit, public, msg="page2annex(public): " + stats_str)

    lgr.info(stats_str)

    if dry_run:
        # print all accumulated commands
        ## for cmd in runner.commands:
        ##     lgr.info("DRY: %s" % cmd)
        pass
    else:
        # Once again save the DB -- db might have been changed anyways
        save_db(db, db_path)

    return stats
