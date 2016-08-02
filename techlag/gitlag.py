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

def extract_dpkg(dpkg):
    """Extract Debian package.

    Extracts a Debian package, give its dsc file. The other components (the
    original file and the diff file should be in the same directory). This
    function assumes that dpkg-source is already installed and ready to run.

    :param   dpkg: dsc file for a Debian package
    :returns: name of directory where the package was extracted.

    """

    dir = os.path.splitext(dpkg)[0]
    logging.info("Extracting Debian pkg in dir: " + dir)
    result = subprocess.call(["dpkg-source", "--extract", dpkg, dir],
                    stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
    if result != 0:
        logging.info('Error while extracting package for {}'.format(dpkg))
        exit()
    return dir

def count_unique(dir, files):
    """Count unique files.

    Unique files are those that are only in one of the directories
    that are compared (left or right).

    :param dir: directory to count
    :param files: files in that directory
    :returns: tuple with number of files and total lines in those files

    """

    num_files = len(files)
    num_lines = 0
    for file in files:
        name = os.path.join(dir, file)
        if os.path.isfile(name):
            num_lines += sum(1 for line in open(name, encoding="ascii",
                                                errors="surrogateescape"))
            logging.debug("Unique file: %s (lines: %d)" % (name, num_lines))
    logging.debug ("Unique files in dir %s: files: %d, lines: %d"
        % (dir, num_files, num_lines))
    return (num_files, num_lines)

def compare_files(file_left, file_right):
    """Compare two files.

    :param file_left: left file to compare
    :param file_right: left file to compare
    :returns: tuple with 1 (if different), 0 (if equal), lines added, removed

    """

    added = 0
    removed = 0
    with open(file_left,'r', encoding="ascii", errors="surrogateescape") as left, \
        open(file_right,'r', encoding="ascii", errors="surrogateescape") as right:
        diff = difflib.ndiff(left.readlines(), right.readlines())
        for line in diff:
            if line.startswith('+'):
                added += 1
            elif line.startswith('-'):
                removed += 1
    if (added + removed) > 0:
        diff = 1
    else:
        diff = 0
    return (diff, added, removed)

def count_common(dir_left, dir_right, files):
    """Count common files.

    Common files are those that are in both directories being compared
    (left or right).

    :param dir_left: left directory to count
    :param dir_right: right directory to count
    :param files: files in both directories
    :returns: tuple with number of diff files, and total lines added,
        removed in those files
    """

    added = 0
    removed = 0
    diff_files = 0
    for file in files:
        name_left = os.path.join(dir_left, file)
        name_right = os.path.join(dir_right, file)
        (diff, added_l, removed_l) = compare_files(name_left, name_right)
        diff_files += diff
        added += added_l
        removed += removed_l
    return (diff_files, added, removed)

def compare_dirs(dcmp):
    """Compare two directories given their filecmp.dircmp object.

    Produces as a result a dictionary with metrcis about the comparison:
     * left_files: number of files unique in left directory
     * right_files: number of files unique in right directory
     * diff_files: number of files present in both directories, but different
     * left_lines: number of lines for files unique in left directory
     * right_lines: number of lines for files unique in left directory
     * added_lines: number of lines added in files present in both directories
     * removed_lines: number of lines removed in files present in both directories

    added_lines, removed_lines refer only to files counted as diff_files

    :param dcmp: filecmp.dircmp object for directories to compare
    :returns: dictionary with differences

    """

    m = {}
    (m["left_files"], m["left_lines"]) \
        = count_unique(dir = dcmp.left, files = dcmp.left_only)
    (m["right_files"], m["right_lines"]) \
        = count_unique(dir = dcmp.right, files = dcmp.right_only)
    (m["diff_files"], m["added_lines"], m["removed_lines"]) \
        = count_common(dcmp.left, dcmp.right, dcmp.common_files)
    for sub_dcmp in dcmp.subdirs.values():
        m_subdir = compare_dirs(sub_dcmp)
        for metric, value in m_subdir.items():
            m[metric] += value
    return m


class Metrics:
    """Data structure for dealing with metrics related to commits.

    """

    def __init__(self, repo, dir):

        # List of commit hashes, ordered as returned by git
        self.commits = []
        # Dictionary with metrics, key is the commit number (order in commits)
        self.metrics = {}
        # Repository and directory to compare
        self.repo = repo
        self.dir = dir

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

        Checks out the corresponding commit in the git repository, and
        compute the metrics for its difference with the given package.
        The returned metrics are those produced by compare_dirs plus:
         * commit: hash for the commit
         * date: commit date for the commit (as a string)

        :param commits: list of all commits
        :param commit_no: commit number (starting in 0)
        :returns: dictionary with metrics
        """

        commit = self.commits[commit_no]
        subprocess.call(["git", "-C", self.repo.dir, "checkout", commit[0]],
                        stdout = subprocess.DEVNULL, stderr = subprocess.DEVNULL)
        dcmp = filecmp.dircmp(self.repo.dir, self.dir)
        m = compare_dirs(dcmp)
        logging.debug ("Commit %s. Files: %d, %d, %d, lines: %d, %d, %d, %d)"
            % (commit[0], m["left_files"], m["right_files"], m["diff_files"],
            m["left_lines"], m["right_lines"],
            m["added_lines"], m["removed_lines"]))
        m["total_files"] = m["left_files"] + m["right_files"] + m["diff_files"]
        m["total_lines"] = m["left_lines"] + m["right_lines"] \
            + m["added_lines"] + m["removed_lines"]
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

    def min_range (self, length, metric):
        """Find range of minimum values.

        Returns a range of minimum values. The range will have at least
        length values. In fact, a tuple with the lowest sequence number, and
        the maximum sequence number for the range, the sequence number for
        the minimum value, and the minimum value.

        :param length: length (number of values) of the range
        :param metric: name of the metric to consider for comparison
        :returns: tuple (min, max, min_index, min_value)

        """

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
                # Only worry if largest in lists is larger than value
                largest = max(values)
                if value < largest:
                    # Largest is larger. Remove it from lists
                    largest_index = values.index(largest)
                    values.pop(largest_index)
                    indexes.pop(largest_index)
                    # And now add value to the right
                    values.append(value)
                    indexes.append(seq_no)
            logging.debug("values: " + str(values))
            logging.debug("indexes " + str(indexes))
        min_value = min(values)
        min_index = indexes[values.index(min_value)]
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
        return (indexes[0], indexes[-1], min_index, min_value)

    def metrics_items (self):
        """Iterator returning metrics for all computed commits.

        """

        return [self.metrics[seq_no] for seq_no in sorted(self.metrics)]
        #return self.metrics.values()

class Repo:
    """Metainformation about a git repository.

    :param url:      repo url
    :param dir:      path of directory for repo
    :param after:    only considering commits after this date (default None, means all considered)
    :type after:      datetime.datetime
    :param branches: branches to consider (default None, means "all branches")
    :type branches:   list of str

    """

    def __init__(self, url, dir, after=None, branches=None):

        self.url = url
        self.dir = dir
        if after is None:
            self.after = datetime.datetime(1970, 1, 1, 0, 0)
        else:
            self.after = after
        self.branches = branches
        parser = perceval.backends.git.Git(uri=self.url, gitpath=self.dir)
        self.commits = []
        for item in parser.fetch(from_date = self.after, branches=self.branches):
            self.commits.append([item['data']['commit'], item['data']['CommitDate']])

    def get_commits (self):
        """Get list of commits.

        :returns:         list of commits (each commit is a list [hash, date])

        """

        return self.commits

    def last_commit (self):
        """Get last commit number.

        """

        return len(self.commits) - 1

    def checkout(self, commit_no, store=None):
        """Copy a checkout of the repo to dir.

        If store is None, just checkout the commit in the repo, but don't
        copy it to a directory. If not none, it will be the directory for
        storage, where a directory will be produced, with the hash as name,
        to copy the checkout.
        If specified, store should exist. If there is already a checkout for
        this commit in store, just checkout in the repository, but don't copy.

        :param commit_no: commit number to check out
        :param store:     directory to copy the checkout to (default: None)
        :returns:          path of directory with the checkout, or None if none

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

    def compute_diff(self, commit_no, dir):
        """Compute diff metrics between the repo checkout for commit_no and dir.

        Checks out commit_no (as per git log order) in the git repository, and
        computes the metrics for its difference with the given directory.
        The returned metrics are those produced by compare_dirs plus:
         * commit: hash for the commit
         * date: commit date for the commit (as a string)

        :param commit_no: commit number to checkout
        :param dir:       directory to compare
        :returns: dictionary with metrics
        """

        commit = self.commits[commit_no]
        self.checkout(commit_no)
        dcmp = filecmp.dircmp(self.dir, dir)
        m = compare_dirs(dcmp)

        logging.debug ("Commit %s. Files: %d, %d, %d, lines: %d, %d, %d, %d)"
            % (commit[0], m["left_files"], m["right_files"], m["diff_files"],
            m["left_lines"], m["right_lines"],
            m["added_lines"], m["removed_lines"]))
        m["total_files"] = m["left_files"] + m["right_files"] + m["diff_files"]
        m["total_lines"] = m["left_lines"] + m["right_lines"] \
            + m["added_lines"] + m["removed_lines"]
        m["commit_seq"] = commit_no
        m["commit"] = commit[0]
        m["date"] = commit[1]
        return m


def find_upstream_commit (upstream, dir, after, steps, name=""):
    """Find the most likely upstream commit.

    Compares a source code directory with the checkouts from its upstream
    git repo, with the intention of finding the most likely upstream commit
    for the specific source code in the directory. The directory usually
    corresponds to a snapshot of the git repository, like a downloadable
    tarball, or a Debian/Ubuntu package. Although it is derived from the
    upstream repository, usually it is not exactly equal to any checkout
    (commit) from it. Therefore, we use several metrics to estimate how
    close any checkout from the upstream repo is to the directory.

    :param upstream: upstream git repository metadata
    :type upstream:   Repo
    :param dir:      source code directory to match to upstream
    :param after:    check only commits after this date
    :type after:      datetime.datetime
    :param steps:    do approximation according to these steps
    :param name:      name of package being computed
    :type name:       string

    :returns:         dictionary with infom about most similar commit

    """

    metrics = Metrics(repo=upstream, dir=dir)
    metrics.add_commits(upstream.get_commits())
    logging.info("%d commits parsed." % metrics.num_commits())

    left = 0
    right = metrics.num_commits()-1
    # Next calculates the ceiling integer division
    # Needed because we want eg. 1/3 to be 1
    step = -(-metrics.num_commits() // steps)
    while step >= 1:
        metrics.compute_range (left, right, step)
        (left, right, min_seq, min_value) = metrics.min_range(length=3, metric="total_lines")
        logging.info("Step: %d, left: %d, right: %d, min. seq: %d, min. value: %d."
                    % (step, left, right, min_seq, min_value))
        if step == 1:
            step = 0
        else:
            candidate_step = -(-step // steps)
            if candidate_step >= step:
                step = step - 1
            else:
                step = candidate_step
    min_commit = metrics.get_commit(min_seq)
    most_similar = {
        'sequence': min_seq,
        'diff': min_value,
        'hash': min_commit[0],
        'date': min_commit[1]
    }
    csv_header = "CSV,{name},commit_seq,date,total_lines," \
        + "total_files,added_lines,removed_lines"
    csv_string = "CSV,{name},{commit_seq:9d},{date},{total_lines:9d},{total_files:6d}," \
        + "{added_lines:9d},{removed_lines:9d}"
    logging.info(csv_header.format(name=name))
    for m in metrics.metrics_items():
        logging.info(csv_string.format(name=name,
                                        commit_seq=m["commit_seq"],
                                        date=m["date"],
                                        total_lines=m["total_lines"],
                                        total_files=m["total_files"],
                                        added_lines=m["added_lines"],
                                        removed_lines=m["removed_lines"]))
    return (most_similar)
