#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Jesus M. Gonzalez-Barahona <jgb@bitergia.com>
#

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import filecmp
import logging

if not '..' in sys.path:
    sys.path.insert(0, '..')

import techlag.gitlag

class TestGitSimple (unittest.TestCase):
    """Root class for setting up data for tests with a simple git repo.

    Does not include any real test.

    """
    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='gitlag_')
        cls.dir1 = os.path.join(cls.tmp_path, 'dirs', 'dir1')
        cls.dir2 = os.path.join(cls.tmp_path, 'dirs', 'dir2')
        cls.dir3 = os.path.join(cls.tmp_path, 'dirs', 'dir3')
        cls.url_git = os.path.join(cls.tmp_path, 'dir_git')
        cls.cloned_git = os.path.join(cls.tmp_path, 'cloned_git')

        subprocess.check_call(['tar', '-xzf', 'data/dirs.tar.gz',
                               '-C', cls.tmp_path])
        subprocess.check_call(['tar', '-xzf', 'data/dir_git.tar.gz',
                               '-C', cls.tmp_path])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

class TestCompareGit(TestGitSimple):
    """Tests for comparing a directory to a git repository"""

    def test_closest_commit(self):
        """Test Metrics.closest_commit"""

        expected_1 = {
            'date': 'Sat Aug 27 17:00:32 2016 +0200',
            'sequence': 0, 'diff': 30,
            'hash': '1b3a00eb5668e602b70faa3dbc6f6eda0046e8f5'
            }
        expected_2 = {
            'date': 'Sat Aug 27 17:00:32 2016 +0200',
            'sequence': 0, 'diff': 0,
            'hash': '1b3a00eb5668e602b70faa3dbc6f6eda0046e8f5'
            }
        expected_3 = {
            'date': 'Sat Aug 27 17:02:06 2016 +0200',
            'sequence': 1, 'diff': 27,
            'hash': 'a8c58489359197983a2e7235fd3e09346313a430'
            }

        repo = techlag.gitlag.Repo(url=self.url_git, dir=self.cloned_git)
        metrics = techlag.gitlag.Metrics(repo=repo, dir=self.dir1,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                                metric='common_lines')
        self.assertEqual(result, expected_1)

        result = metrics.closest_commit()
        self.assertEqual(result, expected_2)

        metrics = techlag.gitlag.Metrics(repo=repo, dir=self.dir1,
                                        metrics_kinds=['diff'])
        result = metrics.closest_commit(closest_fn=min,
                                                metric='different_lines')
        self.assertEqual(result, expected_2)

        metrics = techlag.gitlag.Metrics(repo=repo, dir=self.dir2,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                                metric='common_lines')
        self.assertEqual(result, expected_3)

class TestCompareCheckouts(TestGitSimple):
    """Tests for comparing checkouts"""

    def test_compare_checkouts (self):
        """Test Metrics.compare_checkouts"""

        expected = {'diff_files': 1, 'left_files': 2, 'right_files': 1,
            'equal_lines': 5, 'different_lines': 10, 'different_files': 2,
            'left_lines': 9, 'added_lines': 4, 'right_lines': 3,
            'removed_lines': 5
            }
        repo = techlag.gitlag.Repo(url=self.url_git, dir=self.cloned_git)
        metrics = techlag.gitlag.Metrics(repo=repo, dir=self.dir2,
                                        metrics_kinds=['same'])
        result = metrics.compare_checkouts(1, 0)
        self.assertEqual (result, expected)

class TestCompareGitSmall(unittest.TestCase):
    """Tests for comparing a dirctory to a small git repository

    This is small, but larger than dir1. In fact, it is based on
    the techlag repo.

    """

    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='gitlag_')
        cls.dir1 = os.path.join(cls.tmp_path, 'dirs2', 'b306b9d')
        cls.dir2 = os.path.join(cls.tmp_path, 'dirs2', '7beb12a')
        cls.dir3 = os.path.join(cls.tmp_path, 'dirs2', '6d1c3c1')
        cls.dir4 = os.path.join(cls.tmp_path, 'dirs2', '7beb12a-close')
        cls.url_git = os.path.join(cls.tmp_path, 'dir2_git')
        cls.cloned_git = os.path.join(cls.tmp_path, 'cloned_git')

        subprocess.check_call(['tar', '-xzf', 'data/dirs2.tar.gz',
                               '-C', cls.tmp_path])
        subprocess.check_call(['tar', '-xzf', 'data/dir2_git.tar.gz',
                               '-C', cls.tmp_path])

        cls.repo = techlag.gitlag.Repo(url=cls.url_git, dir=cls.cloned_git)

        cls.expected = [{
            'date': 'Fri Jun 24 20:46:17 2016 +0200',
            'sequence': 0, 'diff': 676,
            'hash': 'b306b9d7c4bbd7e5310f32150223f94b25d53040'
            },
            {
            'date': 'Sat Aug 6 11:13:41 2016 +0200',
            'sequence': 12, 'diff': 1921,
            'hash': '7beb12a054f84ab0021f34541073033c247146ca'
            },
            {
            'date': 'Sun Aug 28 21:06:55 2016 +0200',
            'sequence': 27, 'diff': 2560,
            'hash': '6d1c3c1ebf30540be4b70ab33ef92baedad21f40'
            }]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

    def test_closest_commit_1(self):
        """Test Metrics.closest_commit"""

        metrics = techlag.gitlag.Metrics(repo=self.repo, dir=self.dir1,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                        metric='common_lines')
        self.assertEqual(result, self.expected[0])

    def test_closest_commit_2(self):
        """Test Metrics.closest_commit"""


        metrics = techlag.gitlag.Metrics(repo=self.repo, dir=self.dir2,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                        metric='common_lines')
        self.assertEqual(result, self.expected[1])

    def test_closest_commit_3(self):
        """Test Metrics.closest_commit"""

        metrics = techlag.gitlag.Metrics(repo=self.repo, dir=self.dir3,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                        metric='common_lines')
        self.assertEqual(result, self.expected[2])

    def test_closest_commit_4 (self):
        """Test Metrics.closest_commit"""

        metrics = techlag.gitlag.Metrics(repo=self.repo, dir=self.dir4,
                                        metrics_kinds=['same'])
        result = metrics.closest_commit(closest_fn=max,
                                        metric='common_lines')
        expected = self.expected[1].copy()
        expected['diff'] = 1890
        self.assertEqual(result, expected)


if __name__ == "__main__":
#    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
