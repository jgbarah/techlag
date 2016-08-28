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
import perceval.backends
import subprocess
import logging
import io
import datetime
import shutil
import shelve

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
                    logging.debug("Unique file from cache: %s (lines: %d)" %
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
    """Class for getting metrics comparing a git repository with a directory.

    metrics_kinds are the kind of metrics that will be computed to compare
    each commit with the directory. They may be any list from ['same', 'diff']

    :param repo:          Repo object (git repository)
    :param dir:           directory to compare with the git repository
    :param metrics_kinds: kinds of metrics to analyze each commit

    """

    def __init__(self, repo, dir, metrics_kinds=['diff']):

        # List of commit hashes, ordered as returned by git
        self.commits = []
        # Dictionary with metrics, key is the commit number (order in commits)
        self.metrics = {}
        # Repository and directory to compare
        self.repo = repo
        self.dir = dir
        for metric in metrics_kinds:
            assert metric in ['diff', 'same']
        self.metrics_kinds = metrics_kinds

    def add_commit(self, commit, date):
        """Add commit info to data structure.

        :param commit: hash of the commit
        :param date: commit date

        """

        self.commits.append([commit, date])

    def add_commits(self, commits):
        """Update info about commits to data structure.

        Commits come as a list of dictionaries, one per commit, in order
        (according to the order in Perceval, or git log for that matter).
        Each item in the list is a list [commit, date].

        :param commits: list of hashes for commits

        """

        self.commits = commits

    def get_commit(self, seq_no):
        """Get a commit tuple (hash, date) for a given commit sequence.

        """

        return self.commits[seq_no]

    def num_commits(self):
        """Return the number of commits stored.

        """

        return len(self.commits)

    def compute_metrics(self, commit_no):
        """Compute metrics for commmit number (ordered as from git log).

        For an explanation of the metrics instantiation parameter, read
        the comments for the BaseDir.compare function.

        Checks out the corresponding commit in the git repository, and
        compute the metrics for its difference with the given package.
        The returned metrics are those produced by BaseDir.compare plus:
         * commit: hash for the commit
         * date: commit date for the commit (as a string)

        :param commits: list of all commits
        :param commit_no: commit number (starting in 0)
        :returns: dictionary with metrics
        """

        commit = self.commits[commit_no]
        subprocess.call(["git", "-C", self.repo.dir, "checkout", commit[0]],
                        stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
        dircmp = BaseDir(self.dir, metrics=self.metrics_kinds)
        m = dircmp.compare(self.repo.dir)
        logging.debug ("Commit %s. Metrics: %s" % (str(commit), str(m)))
        m["commit_seq"] = commit_no
        m["commit"] = commit[0]
        m["date"] = commit[1]
        return m

    def compute_range (self, first, last, step):
        """Compute metrics for a range of commits.

        Compute metrics for a range of commits, but only for those in the
        appropriate steps.

        :param first: first commit to consider
        :param last: last commit to consider
        :param step: only consider commits coincident with step
        :returns: dictionary with (updated) metrics

        """

        for seq_no in list(range(first, last, step)) + [last]:
            logging.info("Computing metrics for %d." % seq_no)
            if seq_no not in self.metrics:
                m = self.compute_metrics(seq_no)
                logging.debug(m)
                self.metrics[seq_no] = m

    def closest_range (self, length, metric='diff_files',closest_fn=min):
        """Find range of minimum values.

        Returns a range of closes values. The range will have at least
        length values. In fact, a tuple with the lowest sequence number, and
        the maximum sequence number for the range, the sequence number for
        the closest value, and the closest value.

        :param length: length (number of values) of the range
        :param metric: name of the metric to consider for comparison
        :param closest_fn: function to use to find the closest value (min, max)
        :returns: tuple (min, max, closest_index, closest_value)

        """

        assert closest_fn in [min, max]
        if closest_fn is min:
            farthest_fn = max
        else:
            farthest_fn = min
        values = []
        indexes = []
        seq_commits = sorted(self.metrics)
        for seq_no in seq_commits:
            value = self.metrics[seq_no][metric]
            if len(values) <= length:
                # Still room, just add to lists
                values.append(value)
                indexes.append(seq_no)
            else:
                # Only worry if valus is closer than farthest in lists
                furthest = furthest_fn(values)
#                largest = max(values)
                if closer_fn([value, furthest]) == value:
                    # Value is closer than furthest. Remove it from lists
                    farthest_index = values.index(farthest)
                    values.pop(farthest_index)
                    indexes.pop(farthest_index)
                    # And now add value to the right
                    values.append(value)
                    indexes.append(seq_no)
            logging.debug("values: " + str(values))
            logging.debug("indexes " + str(indexes))
        closest_value = closest_fn(values)
        closest_index = indexes[values.index(closest_value)]
        # Add next computed checkout on the left and on the right, just in case we're
        # on the edge of the checkouts we have computed
        if indexes[0] > seq_commits[0]:
            left_seq = seq_commits[seq_commits.index(indexes[0])-1]
            indexes.insert(0, left_seq)
            values.insert(0, self.metrics[left_seq][metric])
        if indexes[-1] < seq_commits[-1]:
            right_seq = seq_commits[seq_commits.index(indexes[-1])+1]
            indexes.append(right_seq)
            values.append(self.metrics[right_seq][metric])
        logging.info("values: " + str(values))
        logging.info("indexes " + str(indexes))
        return (indexes[0], indexes[-1], closest_index, closest_value)

    def metrics_items (self):
        """Iterator returning metrics for all computed commits.

        """

        return [self.metrics[seq_no] for seq_no in sorted(self.metrics)]

    def find_upstream_commit (self, steps=10, name=None,
            closest_fn=min, metric='diff_files'):
        """Find the most likely upstream commit.

        Compares a source code directory with the checkouts from its upstream
        git repo, with the intention of finding the most likely upstream commit
        for the specific source code in the directory. The directory usually
        corresponds to a snapshot of the git repository, like a downloadable
        tarball, or a Debian/Ubuntu package. Although it is derived from the
        upstream repository, usually it is not exactly equal to any checkout
        (commit) from it. Therefore, we use several metrics to estimate how
        close any checkout from the upstream repo is to the directory.

        closest_fn and metric usually work together. metric is the metric that
        will be used to decide if a commit is closer to the directory than other.
        Depending on the metric, we want to maximize (for similarity metrics)
        or minimize it (for difference metrics).

        :param after:        check only commits after this date
        :type after:         datetime.datetime
        :param steps:        do approximation according to these steps
        :param name:         name of package being computed (Default: dir)
        :type name:          string
        :param closest_fn:   function to evaluate the closest commit (min or max)
        :param metric:       metric to decide if a commit is closer or not
        :returns:            dictionary with infom about most similar commit

        """

        if name is None:
            name = self.dir
        self.add_commits(self.repo.get_commits())
        logging.info("%d commits parsed." % self.num_commits())

        left = 0
        right = self.num_commits() - 1
        # Next calculates the ceiling integer division
        # Needed because we want eg. 1/3 to be 1
        step = -(-self.num_commits() // steps)
        while step >= 1:
            self.compute_range (left, right, step)
            (left, right, closest_seq, closest_value) \
                = self.closest_range(length=3, metric=metric,
                                    closest_fn=closest_fn)
            logging.info("Step: %d, left: %d, right: %d, closest seq: %d, closest value: %d."
                    % (step, left, right, closest_seq, closest_value))
            if step == 1:
                step = 0
            else:
                candidate_step = -(-step // steps)
                if candidate_step >= step:
                    step = step - 1
                else:
                    step = candidate_step
        closest_commit = self.get_commit(closest_seq)
        most_similar = {
            'sequence': closest_seq,
            'diff': closest_value,
            'hash': closest_commit[0],
            'date': closest_commit[1]
            }

        csv_header = "CSV,name,"
        csv_string = "CSV,{name},"
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
        return (most_similar)

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

    def checkout(self, commit_no, store=None):
        """Checkout the version of the repository corresponding to commit_no.

        If store is None, just checkout the commit in the repo, in the
        directory specified when instantiating the object, but don't
        copy it to a directory.

        If store is not None, it will be the directory for
        storage, where a subdirectory will be produced, with the hash as name,
        to copy the checkout.

        If specified, store should exist. If there is already a checkout for
        this commit in store, just checkout in the repository, but don't copy.

        :param commit_no: commit number to check out
        :param store:     directory to copy the checkout to (default: None)
        :returns:         path of directory with the checkout, or None if none

        """

        hash = self.commits[commit_no][0]
        subprocess.call(["git", "-C", self.dir, "checkout", hash],
                        stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
        if store is not None:
            checkout_dir = os.path.join(store, hash)
            if not os.path.isdir(checkout_dir):
                shutil.copytree(self.dir, checkout_dir)
            return checkout_dir
        else:
            return None

    # def compute_diff(self, commit_no, dir, metrics=['diff']):
    #     """Compute diff metrics between the repo checkout for commit_no and dir.
    #
    #     Checks out commit_no (as per git log order) in the git repository, and
    #     computes the metrics for its difference with the given directory.
    #     The returned metrics are those produced by compare_dirs plus:
    #      * commit: hash for the commit
    #      * date: commit date for the commit (as a string)
    #
    #     :param commit_no: commit number to checkout
    #     :param dir:       directory to compare
    #     :param metrics:   metrics to produce when comparing (list)
    #     :returns:         dictionary with metrics
    #
    #     """
    #
    #     commit = self.commits[commit_no]
    #     self.checkout(commit_no)
    #
    #     dircmp = BaseDir(self.dir, metrics)
    #     m = dircmp.compare(dir)
    #
    #     logging.debug ("Commit %s. Files: %d, %d, %d, lines: %d, %d, %d, %d)"
    #         % (commit[0], m["left_files"], m["right_files"], m["diff_files"],
    #         m["left_lines"], m["right_lines"],
    #         m["added_lines"], m["removed_lines"]))
    #     m["total_files"] = m["left_files"] + m["right_files"] + m["diff_files"]
    #     m["total_lines"] = m["left_lines"] + m["right_lines"] \
    #         + m["added_lines"] + m["removed_lines"]
    #     m["commit_seq"] = commit_no
    #     m["commit"] = commit[0]
    #     m["date"] = commit[1]
    #     return m
