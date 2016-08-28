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

class TestCompareGit(unittest.TestCase):
    """Tests for comparing a dirctory to a git repository"""

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

    def test_upstream_commit(self):
        """Test find_upstream_commit"""

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

if __name__ == "__main__":
#    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
