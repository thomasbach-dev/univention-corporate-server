"""pytest runner for ucs-test"""

from __future__ import absolute_import

import os
from optparse import OptionGroup

import pytest

from univention.testing.format.junit import Junit


class PytestRunner(object):

	def __init__(self, options):
		self.options = options

	def run_tests(self, test_set):
		args = ['--strict']
		if self.options.dry:
			args.append('--collect-only')
		if self.options.hold:
			args.append('--exitfirst')
		if self.options.format == 'junit':
			args.append('--junit-xml=%s' % (os.path.expanduser('~/%s/' % (Junit().outdir,)),))
		if self.options.verbose:
			args.append('-' + 'v' * self.options.verbose)
		args.append('--continue-on-collection-errors')
		args.extend(self.options.pytest_arg)
		args.append('/usr/share/ucs-test/')
		return pytest.main(args)

	@classmethod
	def get_option_group(cls, parser):
		"""The option group for ucs-test-framework"""
		group = OptionGroup(parser, 'Additional pytest options')
		group.add_option('--pytest-arg', dest='pytest_arg', action='append', default=[])
		return group


def get_ignored_files():
	return []
