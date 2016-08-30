#!/usr/bin/env python3
# -*- coding: utf-8 -*-

## Copyright (C) 2016 Bitergia
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
##
## Authors:
##   Jesus M. Gonzalez-Barahona <jgb@bitergia.com>
##

import filecmp
import difflib
import os
import os.path
import shutil
import gzip
import urllib.request
import json
import perceval.backends
import subprocess
import logging
import io
import datetime
import shutil
import shelve
import shlex
import tempfile

"""This module provides classes for estimating the more likely checkout
in a git repository, when comparing to a certain directory. The directory
usually corresponds to a snapshot of the git repository, like a downloadable
tarball, or a Debian/Ubuntu package. Although it is derived from the
upstream repository, usually it is not exactly equal to any checkout
(commit) from it. Therefore, we use several metrics to estimate how
close any checkout from the upstream repo is to the directory.

"""


def get_dpkg_data (file_name, pkg_name):
    """Get the urls of the components of a source package in aSources.gz file.

    Parse the Sources.gz file given as parameter, finding the urls for
    the componnents (.dsc, .tar.gz) for the given package name. Returns
    a directory with an element 'directory' (directory in the remote
    repository, as it appears in Sources.gz), an element 'dsc' (with the
    name of the .dsc file, as it appears in the Sources.gz file), and an
    element 'components' (list with the names of file components, including
    .dsc, as they appear in Sources.gz)

    :param filename: path of the Sources.gz file to parse
    :param pkg_name: name of the package to find in the Sources.gz file
    :returns: remote directory and list of urls of the components

    """

    data = {'components': []}
    with gzip.open(file_name, 'rt') as sources:
        name_found = False
        files_found = False
        to_download = []
        for line in sources:
            if files_found:
                if line.startswith(' '):
                    component = line.split()[2]
                    data['components'].append(component)
                    if component.endswith('.dsc'):
                        data['dsc'] = component
                else:
                    files_found = False
            if line.startswith('Package:'):
                if name_found:
                    name_found = False
                    break
                read_name = line.split()[1]
                if read_name == pkg_name:
                    name_found = True
            elif name_found and line.startswith('Files:'):
                files_found = True
            elif name_found and line.startswith('Directory:'):
                data['directory'] = line.split()[1]
    return(data)

def get_dpkg(name, release, dir):
    """Get a debian source package, given its name and the release.

    Gets the components of the source code package from the corresponding Debian
    repository, and stores them in dir. To do that, it first gets the
    Sources.gz file  for the corresponding distribution (eg: testing/main),
    looks in it for the components of the package, and downloads them.

    :param    name: name of the Debian package
    :param release: Debian release
    :param     dir: name (path) of the directory to download the components
    :returns: path of the downloaded dsc file for the package

    """

    debian_repo = 'http://ftp.es.debian.org/debian/'
    sources_url = debian_repo + 'dists/' + release + '/source/Sources.gz'
    sources_file = os.path.join(dir, 'Sources.gz')
    logging.info ("Downloading {} to {}".format(sources_url, sources_file))
    urllib.request.urlretrieve(sources_url, sources_file)

    pkg_data = get_dpkg_data(sources_file, name)
    for file in pkg_data['components']:
        file_url = debian_repo + pkg_data['directory'] + "/" + file
        file_path = os.path.join(dir, file)
        logging.info ("Downloading {} from {}".format(file, file_url))
        urllib.request.urlretrieve(file_url, file_path)
    return os.path.join(dir, pkg_data['dsc'])

def extract_dpkg(dpkg, remove=False):
    """Extract Debian package.

    Extracts a Debian package, give its dsc file. The other components (the
    original file and the diff file should be in the same directory). This
    function assumes that dpkg-source is already installed and ready to run.

    :param   dpkg: dsc file for a Debian package
    :param remove; remove the directory if already present
    :returns: name of directory where the package was extracted

    """

    dir = os.path.splitext(dpkg)[0]
    if remove and os.path.exists(dir):
        logging.info('Removing old directory before extracting: ' + dir)
        shutil.rmtree(dir)
    logging.info("Extracting Debian pkg in dir: " + dir)
    result = subprocess.call(["dpkg-source", "--extract", dpkg, dir],
                    stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
    if result != 0:
        logging.info('Error while extracting package for {}'.format(dpkg))
        raise ChildProcessError('Error extracting package', dpkg)
    return dir

def get_json(url):

    logging.debug("get_json: " + url)
    try:
        response = urllib.request.urlopen(url).read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        else:
            raise
    data = json.loads(response.decode('utf-8'))
    return data['result']

def get_dpkg_snapshot(name, version, dir):
    """Get a debian source package from Debian Snapshot, given its name and version.

    Gets the components of the source code package from the corresponding Debian
    repository, and stores them in dir. To do that, it first gets the
    Sources.gz file  for the corresponding distribution (eg: testing/main),
    looks in it for the components of the package, and downloads them.

    :param    name: name of the Debian package
    :param version: Debian version
    :param     dir: name (path) of the directory to download the components
    :returns: path of the downloaded dsc file for the package

    """

    # Get the url describing the files for the source package
    files_url = 'http://snapshot.debian.org/mr/package/' + name + '/' \
        + version + '/srcfiles'
    files = get_json(files_url)
    if files is None:
        logging.info("Ignoring version (because no src files): " + version)
        raise ValueError("No src files found in description for package", version)
    for file in files:
        # Get the url describing a file
        file_url = 'http://snapshot.debian.org/mr/file/' \
            + file['hash'] + '/info'
        logging.info("File: " + file_url)
        info = get_json(file_url)[0]
        download_url = 'http://snapshot.debian.org/archive/' \
            + info['archive_name'] + '/' + info['first_seen'] \
            + info['path'] + '/' + info['name']
        file_name = os.path.join(dir, info['name'])
        if os.path.isfile(file_name):
            logging.info('Already present, not downloading: ' + download_url)
        else:
            logging.info('To download: ' + download_url)
            (name, headers) = urllib.request.urlretrieve(url=download_url,
                filename=file_name)
            logging.info('Downloaded: ' + name)
        if os.path.splitext(file_name)[1] == '.dsc':
            dsc = file_name
            date = info['first_seen']
    return (dsc, date)


class Repo:
    """Metainformation about a git repository.

    This class abstracts a git upstream reposory, by using Perceval.

    Upon instantiation of and object in this class, the specified
    upstream repository is cloned in the specified local directory.
    Then, Perceval is used again to obtain the list of
    its commits. The object offers a method for checking out any of
    those commits as well, and copying the resulting checkout to
    a certain 'storage'directory.

    Only commits authored since a certain date will be considered,
    by specifying the after parameter when instantiating. By default (None),
    all commits are considered.

    By default, only commits from master branch are considered, but
    a list of branches to consider can be provided when instantiating.

    Objects in this class may maintain as well a file cache, using Shelve,
    with the list of commits, so that there is no need to recompute them if
    the cache can be read. This is only done if the cache argument is
    provided when instantiating an object. The cache is maintained so that
    either the complete list of commits is in it, or no commit is available
    at all. This is so because it only makes sense to maintain the cache
    if there is no need to parse git log again.

    Each object maintains the list of commits for its repository. For
    each commit, a list [hash, commit_date] is maintanined. The order is
    the one provided by Perceval, which corresponds to the order by
    git log, in reverse order.

    :param url:      url of upstream git repository
    :type url:       string
    :param dir:      path of local directory for cloning the git repository
    :type dir:       string
    :param after:    consider only commits after this date
    :type after:     datetime.datetime
    :param branches: branches to consider (default None, means "all branches")
    :type branches:  list of str
    :param cache:    path for the cache for storing commits
    :type cache:     str

    """

    def __init__(self, url, dir, after=None, branches=["master"], cache=None):

        self.url = url
        self.dir = dir
        if after is None:
            self.after = datetime.datetime(1970, 1, 1, 0, 0)
        else:
            self.after = after
        self.branches = branches

        # Get the git repository always, to be able of checking out later,
        # if needed
        parser = perceval.backends.git.Git(uri=self.url, gitpath=self.dir)

        # The cache is ok if the calue for 'done' is True
        cache_ok = False
        if cache is not None:
            cache_data = shelve.open(cache)
            if 'done' in cache_data and cache_data['done']:
                cache_ok = True

        # Get commits from the cache (if ok) or from the repo (via Perceval)
        if cache_ok:
            self.commits = cache_data['commits']
        else:
            self.commits = []
            commits_fetcher = parser.fetch(from_date = self.after,
                                            branches=self.branches)
            for item in commits_fetcher:
                self.commits.append([item['data']['commit'],
                                    item['data']['CommitDate']])

        # Store data in the cache, if needed
        if cache is not None:
            if not cache_ok:
                cache_data['commits'] = self.commits
                cache_data['done'] = True
            cache_data.close()


    def get_commits (self):
        """Get list of commits.

        Get the list of commits managed by objects in this class.

        :returns:         list of commits (each commit is a list [hash, date])

        """

        return self.commits

    def last_commit (self):
        """Get last commit number.

        Get the last commit in the list maintained by objects in this class.
        This sould correspond to the last commit produced by git log, in
        reverse orther (that is, the first commit produced by git log).

        """

        return len(self.commits) - 1

    def checkout(self, commit_no, copy=None):
        """Checkout the version of the repository corresponding to commit_no.

        If copy is None, just checkout the commit in the repo itself,
        but don't copy it to a directory.

        If copy is not None, it will be the directory for storage,
        where a copy of the checkout will be produced (excluding the
        .git subdirectory). If the directory does already exist,
        no checkout will be done: its contents will be assumed to
        be that checkout. If the directory does not exist, it will be
        created, and git archive will be used, which means that the
        repository will not be really checked out (it will remain in
        the same commit as it was before calling this function).

        :param commit_no: commit number to check out
        :param copy:      directory to copy the checkout to (default: None)
        :returns:         path of directory with the checkout, or None if none

        """

        hash = self.commits[commit_no][0]
        if copy is None:
            subprocess.call(["git", "-C", self.dir, "checkout", hash],
                        stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
            return None
        elif not os.path.isdir(copy):
            os.makedirs(copy)
            subprocess.check_call("git -C " + shlex.quote(self.dir) \
                                + " archive --format tar " + hash \
                                + " | tar -x -C " + shlex.quote(copy),
                                shell=True)
        return copy


class BaseDir():
    """Base directory to compare with others.

    Objects in this class are designed to easy the comparison of a directory
    with several checkouts of a git repository. It provides functions to
    compute several metrics that can be used to estimate how similar
    (or how different) the directory is from a given checkout. Since the
    directory is always the same in the different comparisons, some
    data can be cached between comparisons (for example, the number of lines
    of files in the directory, see explanation on cache, below).

    The 'metrics' instantiation parameter controls which kind of metrics
    will be produced when comparing this directory. This is a list with all
    the kinds of metrics to be produced. Currently, the following kinds
    of metrics can be speficied: 'diff', and 'same'. For more details on
    the metrics computed, read comments for the compare function. By default,
    metrics of kind 'diff' will be produced.

    Objects in this class maintain a in-memory cache of the number of lines
    of each file in dir which is computed. Usually, those files are computed
    when they are found to be exactly equal to the version in the directory
    being compared (to increment the number of equal lines), or when it is
    found to be only inn dir (to increment the number of different lines).

    :param name: name (full path) of directory to compare
    :param metrics: metrics to produce when comparing (list)

    """

    def __init__(self, name, metrics=['diff']):
        for metric in metrics:
            assert metric in ['diff', 'same']
        self.dir = name
        self.metrics = metrics
        # Cache for metrics of unique files in self.dir
        self.lines = {}

    def count_files(self, dir, files, use_cache=False):
        """Count some files in a directory, and their number of lines

        Given a list of files in a directory, count them (number of
        elements in the list) and count the lines in all of them.

        If use_cache is True, use an in-memory cache to store the
        result for each file computed. Please note that this only make
        sense if the directory in which those files are is always the
        same. Therefore it is used usually only with files corresp0nding
        to the directory managed by the object. Usually it is an error
        to have use_cache True for a directory which is not the managed
        directory.

        :param files:     files to compute
        :param dir:       directory with files (default, None)
        :param use_cache: use cache for files computed (default False)
        :returns:         tuple [number of files, total lines in those files]

        """

        num_files = len(files)
        num_lines = 0
        for file in files:
            name = os.path.join(dir, file)
            if os.path.isfile(name):
                if use_cache and (name in self.lines):
                    # Get result from cache
                    file_lines = self.lines[name]
                    logging.debug("Computed file from cache: %s (lines: %d)" %
                                (name, file_lines))
                else:
                    with open(name, encoding="ascii", errors="surrogateescape") as f:
                        file_lines = sum(1 for line in f)
                    logging.debug("Counted file: %s (lines: %d)" % (name, file_lines))
                    if use_cache:
                        logging.debug("Counted file to cache: %s (lines: %d)" %
                                        (name, file_lines))
                        self.lines[name] = file_lines
                num_lines += file_lines
        logging.debug ("Counted files in dir %s: files: %d, lines: %d"
            % (dir, num_files, num_lines))
        return (num_files, num_lines)

    @staticmethod
    def compare_files(file_left, file_right):
        """Compare two files.

        Compares two files, given their paths. Checks if they are equal
        or different, and the number of lines added, removed
        and equal from file_left to file__right. Returns the information as
        a tuple, with the first element being 1 (if different) or 0 (if equal),
        and then the number of lines added, lines removed, and lines equal.

        Uses a difflib Differ to do the job.

        :param file_left: left file to compare
        :param file_right: left file to compare
        :returns: tuple [equality_check, added, removed, equal]

        """

        added = 0
        removed = 0
        equal = 0
        with open(file_left,'r', encoding="ascii", errors="surrogateescape") as left, \
            open(file_right,'r', encoding="ascii", errors="surrogateescape") as right:
            differ = difflib.Differ()
            diff = differ.compare(left.readlines(), right.readlines())

            for line in diff:
                if line.startswith('+'):
                    added += 1
                elif line.startswith('-'):
                    removed += 1
                elif line.startswith(' '):
                    equal += 1
        if (added + removed) > 0:
            different = 1
        else:
            different = 0
        return (different, added, removed, equal)

    @classmethod
    def count_diff(cls, dir_left, dir_right, files):
        """Count differences in files present in two directories.

        Given a list of files supposed to be present in two directories,
        compute their differences. All files are supposed to exist in
        both directories.

        Returns a tuple with the number of different files, and the total
        number of lines added, removed and equal from the files in the
        left directory to the files in the right directory.

        :param dir_left:  left directory to consider
        :param dir_right: right directory to consider
        :param files:     files to compute, supposed to be in both directories
        :returns:         tuple [diff_files, added, removed, changed]
        """

        added = 0
        removed = 0
        equal = 0
        diff_files = 0
        for file in files:
            name_left = os.path.join(dir_left, file)
            name_right = os.path.join(dir_right, file)
            (diff, added_l, removed_l, equal_l) = \
                cls.compare_files(name_left, name_right)
            diff_files += diff
            added += added_l
            removed += removed_l
            equal += equal_l
        return (diff_files, added, removed, equal)

    def _compare_dirs(self, dcmp):
        """Compare two directories given their filecmp.dircmp object.

        This function is needed to search recursively, using dcmp objects,
        all the subdirs common in both of the directories being commpared.

        Produces as a result a dictionary with metrics about the comparison
        (see compare function for details), aggregated for the directory
        corresponding to dcmp, and all the common subdirectories.

        When this function is called by compare, as usual, the file on
        the left is self.dir.

        :param dcmp: filecmp.dircmp object for directories to compare
        :returns:    dictionary with comparison metrics

        """

        logging.debug('Comparing dirs: ' + dcmp.left + ', ' + dcmp.right)
        m = {}
        if 'diff' in self.metrics:
            (m["left_files"], m["left_lines"]) \
                = self.count_files(dir = dcmp.left, files = dcmp.left_only,
                                    use_cache=True)
            (m["right_files"], m["right_lines"]) \
                = self.count_files(dir = dcmp.right, files = dcmp.right_only)
        if 'same' in self.metrics:
            (m["same_files"], m["same_lines"]) \
                = self.count_files(dir = dcmp.left, files = dcmp.same_files,
                                    use_cache=True)
        (m['diff_files'], m['added_lines'], m['removed_lines'], m['equal_lines']) \
            = self.count_diff(dcmp.left, dcmp.right, dcmp.diff_files)
        for sub_dcmp in dcmp.subdirs.values():
            m_subdir = self._compare_dirs(sub_dcmp)
            for metric, value in m_subdir.items():
                m[metric] += value
        return m

    def compare(self, dir):
        """Compare the base directory with name directory

        Depending on the values in the metrics parameter (provided when
        instantiating the class), several metrics are produced:

        * "diff":
            * left_files: number of files unique in left directory
            * right_files: number of files unique in right directory
            * left_lines: number of lines for files unique in left directory
            * right_lines: number of lines for files unique in left directory
            * different_files: summary metric, (left+right)/2+diff
            * different_lines: summary metric, (left+right+added+removed)/2
        * "same":
            * same_files: number of files common (equal) in both directories
            * same_lines: number of lines common in files present in both directories
            * common_files: summary metric, (same_files)
            * common_lines: summary_metric, (same_lines+equal_lines)
        * Always:
            * diff_files: number of files present in both directories, but different
            * added_lines: number of lines added in files different in both directories
            * removed_lines: number of lines removed in files different in both directories
            * equal_lines: number of lines equal in files different in both directories

        added_lines, removed_lines, equal_lines refer only to files counted as diff_files
        same_lines refer to common_files

        Theh results produced by the function is a dictionary with the metrics
        corresponding to the metrics_kinds specified when instantiating the object.

        :param dir: name (full path) of directory to compare
        :returns:   dictionary with comparison metrics

        """

        dcmp = filecmp.dircmp(self.dir, dir)
        m = self._compare_dirs(dcmp)
        if 'diff' in self.metrics:
            m["different_files"] = (m["left_files"] + m["right_files"]) // 2 \
                    + m["diff_files"]
            m["different_lines"] = (m["left_lines"] + m["right_lines"] \
            + m["added_lines"] + m["removed_lines"]) // 2
        if 'same' in self.metrics:
            m['common_files'] = m['same_files']
            m['common_lines'] = m['same_lines'] + m['equal_lines']
        logging.debug("BaseDir.compare(): " + str(m))
        return m

class Metrics:
    """Class for computing metrics comparing a git repository with a directory.

    metrics_kinds are the kind of metrics that will be computed to compare
    each commit with the directory. They may be any list from ['same', 'diff'].
    See BaseDir class to learn more about the metrics computed in each case.

    If provided and not None, store will be used as a directory for
    intermediate storage. If provided, the directory should exist.

    :param repo:          Repo object (git repository)
    :param dir:           directory to compare with the git repository
    :param metrics_kinds: kinds of metrics to analyze each commit
    :param store:         directory for intermediate storage

    """

    def __init__(self, repo, dir, metrics_kinds=['diff'], store=None):

        self.repo = repo
        self.dir = dir
        for metric in metrics_kinds:
            assert metric in ['diff', 'same']
        self.metrics_kinds = metrics_kinds

        self.basedir = BaseDir(self.dir, metrics=self.metrics_kinds)
        # List of commit hashes, ordered as returned by git log (reverse)
        self.commits = self.repo.get_commits()
        logging.info("Metrics: %d commits parsed." % len(self.commits))
        # Dictionary with metrics, key is the commit number (order in commits)
        self.metrics = {}
        if store is not None:
            assert os.path.isdir(store)
        self.store = store

    def _get_store_dir (self):
        """Get a directory suitable for intermediate storage.

        If the directory does not exist, it is created.

        """

        if self.store is None:
            self.store = tempfile.mkdtemp(prefix='gitlag_')
        return self.store

    def last_commit_no(self):
        """ Returns the latest commit number.

        """

        return self.repo.last_commit()

    def commit_metrics(self, commit_no):
        """Compute comparison metrics for a given commit.

        Check out the corresponding commit in the git repository, and
        compute the metrics for commparing it with the base directory.

        The returned metrics are those produced by BaseDir.compare plus:
         * commit: hash for the commit
         * date: commit date for the commit (as a string)

        For an explanation of the metrics instantiation parameter, read
        the comments for the BaseDir.compare function.

        commit_no is as provided by the Repo class, which in turn
        is provided by Perceval. This is the order as by git log,
        reversed.

        :param commit_no: commit number (starting in 0)
        :returns:         dictionary with metrics for comparison

        """

        commit = self.commits[commit_no]
        subprocess.call(["git", "-C", self.repo.dir, "checkout", commit[0]],
                        stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
        m = self.basedir.compare(self.repo.dir)
        m["commit_no"] = commit_no
        m["commit"] = commit[0]
        m["date"] = commit[1]
        logging.debug ("Commit %s. Metrics: %s" % (str(commit), str(m)))
        return m

    def range_metrics (self, first, last, step):
        """Compute metrics for a range of commits.

        Compute metrics for a range of commits, but only for those in the
        appropriate steps.

        This function computes the comaprison metrics for some
        commits in the given range. Every step commit out of the
        range will ve computed. The metris for computed commits will be
        stored in the internal data structure maintained by the object.
        If metrics for a commmit had been computed previously, they
        are already stored in that data structure, and won't be
        computed again.

        For example, if range is 1:40, and steps is 10, the computed
        commits will be 1, 11, 21, 31 and 40.

        :param first: first commit to consider
        :param last:  last commit to consider
        :param step:  only compute commits coincident with step

        """

        logging.info("Computing metrics for range: %d - %d, step %d" %
                    (first, last, step))
        for seq_no in list(range(first, last, step)) + [last]:
            if seq_no not in self.metrics:
                logging.info("Computing metrics for %d." % seq_no)
                m = self.commit_metrics(seq_no)
                self.metrics[seq_no] = m

    def closest_range (self, length, metric='diff_files',closest_fn=min):
        """Find range of minimum values.

        Find out, for the commits we have already computed, the range
        with closer values (lower or higher, depending on closest_fn).
        The range will be of size lenght, plus one more element in both
        sides, if that's possible (the range does not not include the
        first or last computed commits). The extra elements are included
        just in case the real closest commit is one of the still
        uncomputed commits, just left or right of the computed range.

        The comparison for deciding is a value is closer or not, is
        based only on metric.

        Returns a tuple with the lowest and highest commit number in the
        range, the commit number for the closest value, and the closest value.

        :param length:     length (number of values) of the range
        :param metric:     name of the metric to consider for comparison
        :param closest_fn: function to use to find the closest value (min, max)
        :returns:          tuple (min, max, closest_index, closest_value)

        """

        assert closest_fn in [min, max]
        if closest_fn is min:
            farthest_fn = max
        else:
            farthest_fn = min
        values = []
        indexes = []
        seq_commits = sorted(self.metrics)
        for commit_no in seq_commits:
            value = self.metrics[commit_no][metric]
            if len(values) <= length:
                # Still room, just add to lists
                values.append(value)
                indexes.append(commit_no)
            else:
                # Only worry if valus is closer than the farthest we have
                farthest = farthest_fn(values)
                if closest_fn([value, farthest]) == value:
                    # Value is closer than furthest. Remove it from lists
                    farthest_index = values.index(farthest)
                    values.pop(farthest_index)
                    indexes.pop(farthest_index)
                    # And now add value to the right
                    values.append(value)
                    indexes.append(commit_no)
            logging.debug("values: " + str(values))
            logging.debug("indexes " + str(indexes))
        # Add next computed checkout on the left and on the right,
        # just in case we're on the edge of the checkouts we have computed
        if indexes[0] > seq_commits[0]:
            left_seq = seq_commits[seq_commits.index(indexes[0])-1]
            indexes.insert(0, left_seq)
            values.insert(0, self.metrics[left_seq][metric])
        if indexes[-1] < seq_commits[-1]:
            right_seq = seq_commits[seq_commits.index(indexes[-1])+1]
            indexes.append(right_seq)
            values.append(self.metrics[right_seq][metric])
        closest_value = closest_fn(values)
        closest_index = indexes[values.index(closest_value)]
        logging.info("Closest values: " + str(values))
        logging.info("Closest indexes " + str(indexes))
        return (indexes[0], indexes[-1], closest_index, closest_value)

    def metrics_items (self):
        """Iterator returning metrics for all computed commits.

        """

        return [self.metrics[commit_no] for commit_no in sorted(self.metrics)]


    def dump_csv (self, name):
        """Dump computed metrics in CSV format, using logging.info

        """

        csv_header = "CSV,name                ,commit_no,   hash,       date,"
        csv_string = "CSV,{name:20s},{commit_no:7d},{hash:7s},{date:20s},"
        if 'same' in self.metrics_kinds:
            csv_header += 'common_files, common_lines, same_files, same_lines'
            csv_string += '{common_files:6d}, {common_lines:9d}, ' \
                + '{same_files:6d}, {same_lines:9d}'
        if 'diff' in self.metrics_kinds:
            csv_header += 'different_files, different_lines, ' \
                + 'left_files, left_lines, right_files, right_lines'
            csv_string += '{different_files:6d}, {different_lines:9d}, ' \
                + '{left_files:6d}, {left_lines:9d}, ' \
                + '{right_files:6d}, {right_lines:9d}'
        csv_header += 'diff_files, added_lines, removed_lines, equal_lines'
        csv_string += '{diff_files:6d}, ' \
            + '{added_lines:9d}, {removed_lines:9d}, {equal_lines:9d}'

        logging.info(csv_header.format(name=name))
        for m in self.metrics_items():
            m['hash']=m['commit'][0:7]
            logging.info(csv_string.format(name=name, **m))

    def closest_commit (self, ratio=10, range=3, name=None,
                        closest_fn=min, metric='diff_files'):
        """Find the closest commit, for the given function and metric.

        Compares the base directory with the checkouts from a
        git repo, with the intention of finding the closest checkout.

        closest_fn and metric usually work together. metric is the metric that
        will be used to decide if a commit is closer to the directory than other.
        Depending on the metric, we want to maximize (for similarity metrics)
        or minimize it (for difference metrics).

        Instead of checking all checkouts, which may be very time consuming,
        we will follow an interative strategy:

        * We compute an initial step by using ratio, just dividing the
        number of commits by the ratio.
        * Then, we compute the comparison metrics for the first and
        last commits, and for one commit out of every step.
        * After that, we identify the range of closest commits
        (largest or smallest), by using a list of some commmits with the
        closest metrics. The range will be from the first to the last
        commits in that list, plus one more computed commit on the left,
        and another one on the right.
        * For this new range, we compute again the step, using the ration
        by dividing the number of commits in the range by it.
        * We compute the comparison metric for the step-commits again
        * We identify the new range of closest commits.
        * We compute again the step...

        This process is followed until until metrics are computed for a
        range with step 1.

        Therefore, ratio controls how much commmits will be computed during each iteration (the larger the ratio, the larger the number of commits during each iteration). range is the length of the list of closest commits
        during each iteration. The larger the range, the less likely to
        find a local minimum (or maximum) instead of the true closest value.

        If name parameter is None, or is not present, name will be
        the last component of the base directory.

        :param ratio:       ratio to calcuate steps each iteration (Default: 10)
        :param range:       length of the range for each iteration (Default: 3)
        :param name:        name of package being computed
        :type name:         string
        :param closest_fn:  function to evaluate the closest commit (min or max)
        :param metric:      metric to decide if a commit is closer or not
        :returns:           dictionary with infom about most similar commit

        """

        if name is None:
            name = os.path.basename(self.dir)

        left = 0
        right = len(self.commits) - 1
        # Next calculates the ceiling integer division
        # Needed because we want eg. 1/3 to be 1
        step = -( -len(self.commits) // ratio)
        while step >= 1:
            self.range_metrics (left, right, step)
            closest = self.closest_range(length=range, metric=metric,
                                        closest_fn=closest_fn)
            (left, right, closest_seq, closest_value) = closest
            logging.info("Step: %d, left: %d, right: %d, closest seq: %d, closest value: %d."
                    % (step, left, right, closest_seq, closest_value))
            if step == 1:
                step = 0
            else:
                candidate_step = -( -(right-left+1) // ratio)
                if (candidate_step >= step // 2) and (step // 2 >= 1):
                    step = step // 2
                else:
                    step = candidate_step
        closest_commit = self.commits[closest_seq]
        most_similar = {
            'sequence': closest_seq,
            'diff': closest_value,
            'hash': closest_commit[0],
            'date': closest_commit[1]
            }

        self.dump_csv(name=name)
        return (most_similar)

    def compare_checkouts (self, left_commit, right_commit, metrics_kinds=None):
        """Compare two checkouts of the git repository

        As a side effect, the left commit is checked out in a directory
        under the store for this Metrics object. That means that as long as
        that store remains, the checkout won't be done again, and the
        contents of that directory are assumed to correspond to the checkout.

        :param left_commit:   commit number to be considered as left checkout
        :param right_commit:  commit number to be considered as right checkout
        :param metrics_kinds: kinds of metrics to analyze each commit

        """

        if metrics_kinds is None:
             metrics_kinds = self.metrics_kinds
        # Checkout left_commit to a new directory
        store = self._get_store_dir()
        left_dir = os.path.join(store, self.commits[left_commit][0])
        self.repo.checkout (commit_no=left_commit, copy=left_dir)
        # Create a BaseDir with left commit for comparing
        left_dir = BaseDir (name=left_dir, metrics=metrics_kinds)
        # Checkout right_commit
        self.repo.checkout (commit_no=right_commit, copy=None)
        # Compare
        m = left_dir.compare (self.repo.dir)
        return m

def lag (name, upstream, dir, after, store, ratio=10, range=3):
    """Compute technical lag for directory with respect to upstream repository.

    This is a part of the high level interface of this module.

    :param name:      name of package being computed
    :type name:       string
    :param upstream: upstream git repository Metainformation
    :type upstream:   techlag.gitlago.Repo
    :param dir:      path to directory (source code derived from upstream repo)
    :param after:    check only commits after this date, format: %Y-%m-%d
    :type after:      datetime.datetime
    :param ratio:     do approximation according to this ratio
    :param range:     do approximation according to this range
    :param store:    directory to store checkouts

    """

    # Create a Metrics object and compute the closest commit
    metrics = Metrics(repo=upstream, dir=dir,
                                    metrics_kinds=['same'], store=store)
    commit = metrics.closest_commit (closest_fn=max, metric='common_lines',
                                    ratio=ratio, range=range,
                                    name=name)
    info_str = "{}: most similar upstream checkout is {} " \
        + "(diff: {}, date: {}, hash: {})."
    logging.info (info_str.format(
                            name, commit['sequence'], commit['diff'],
                            commit['date'], commit['hash']
                            ))
    logging.info ('Number of commits computed: ' + str(len(metrics.metrics)) \
                + " out of a total of " + str(metrics.last_commit_no()+1))
    # Compare the closest commit with the head (last commit)
    metrics_data = metrics.compare_checkouts (commit['sequence'],
                                            metrics.last_commit_no())
    logging.info ("Metrics comparing with last commit: " + str(metrics_data))
    metrics_data['diff_commits'] = metrics.last_commit_no() - commit['sequence']
    result_str = "{}: technical lag to master HEAD is " \
        + "{} (commits), {} (lines), {} (files)"
    print (result_str.format(name, metrics_data['diff_commits'],
                            metrics_data['common_lines'], metrics_data['common_files']),
            flush=True)
    return metrics_data
