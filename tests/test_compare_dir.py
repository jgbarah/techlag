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

if not '..' in sys.path:
    sys.path.insert(0, '..')

import techlag.gitlag

class TestCompareDir(unittest.TestCase):
    """Tests for comparing directories in gitlag"""

    @classmethod
    def setUpClass(cls):
        cls.tmp_path = tempfile.mkdtemp(prefix='gitlag_')
        cls.dir1 = os.path.join(cls.tmp_path, 'dirs', 'dir1')
        cls.dir2 = os.path.join(cls.tmp_path, 'dirs', 'dir2')

        subprocess.check_call(['tar', '-xzf', 'data/dirs.tar.gz',
                               '-C', cls.tmp_path])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_path)

    def test_dirs(self):
        """Test whether metrics for two dirs are computed as they should"""

        result_always = {'diff_files': 1,
                    'added_lines': 5,
                    'removed_lines': 4,
                    'equal_lines': 5}
        result_diff = {'left_files': 3,
                    'left_lines': 9,
                    'right_files': 3,
                    'right_lines': 9}
        result_same = {'same_files': 1,
                    'same_lines': 8}

        dcmp = filecmp.dircmp(self.dir1, self.dir2)
        # Compare dirs with default metrics
        result = result_always.copy()
        result.update(result_diff)
        m = techlag.gitlag.compare_dirs(dcmp)
        self.assertEqual(m, result)

        # Commpare dirs with explicit metrics, which are default metrics
        m = techlag.gitlag.compare_dirs(dcmp, metrics=['diff_files'])
        self.assertEqual(m, result)

        # Compare dirs with explicit metrics ('same_files')
        result = result_always.copy()
        result.update(result_same)
        m = techlag.gitlag.compare_dirs(dcmp, metrics=['same_files'])
        self.assertEqual(m, result)

        # Compare dirs with explicit metrics ('saame_files', 'diff_files')
        result.update(result_diff)
        m = techlag.gitlag.compare_dirs(dcmp, metrics=['same_files', 'diff_files'])
        self.assertEqual(m, result)

if __name__ == "__main__":
    unittest.main()
