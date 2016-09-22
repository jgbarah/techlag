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

class TestRepo(unittest.TestCase):
    """Tests for checking general issues of class Repo"""

    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='gitlag_')
        cls.url_git = os.path.join(cls.tmp_path, 'dir_git')
        cls.cloned_git = os.path.join(cls.tmp_path, 'cloned_git')

        subprocess.check_call(['tar', '-xzf', 'data/dir_git.tar.gz',
                               '-C', cls.tmp_path])
        cls.repo = techlag.gitlag.Repo(url=cls.url_git, dir=cls.cloned_git)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

    def test_checkout(self):
        """Test Repo.checkout"""

        self.repo.checkout(commit_no=1)
        result = subprocess.getstatusoutput('git -C ' + self.cloned_git \
                                    + ' log -1 --oneline')
        self.assertEqual(result, (0, 'a8c5848 Second commit.'))

    def test_checkout_copy (self):
        """Test Repo.checkout with copy parameter"""

        copy = os.path.join(self.tmp_path, 'copy')
        self.repo.checkout(commit_no=1, copy=copy)
        result = os.listdir(copy)
        self.assertEqual(result, ['file_dir2.txt', 'only_1', 'dir_common'])

if __name__ == "__main__":
#    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
