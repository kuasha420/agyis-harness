#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Arafat Zahan (@kuasha420)
# Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL)
# Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework)

"""
Test suite alias forwarding tests to tests/test_output_compactor.py.
Ensures discovery patterns like test_*hook*.py execute compactor test cases.
"""

from __future__ import annotations

import unittest

from tests.test_output_compactor import *

if __name__ == "__main__":
    unittest.main()
