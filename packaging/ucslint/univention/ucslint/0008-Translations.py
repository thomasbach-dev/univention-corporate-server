# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

from __future__ import absolute_import
import univention.ucslint.base as uub
import re
from codecs import open

# 1) check if translation strings are correct; detect something like  _('foo %s bar' % var)  ==> _('foo %s bar') % var
# 2) check if all translation strings are translated in de.po file


def _or(*disjunct: str, name: str = None) -> str:
	return r'(?%s%s)' % (
		':' if name is None else f'P<{name}>',
		'|'.join(disjunct),
	)


RE_FUZZY = re.compile(r'\n#.*?fuzzy')
RE_EMPTY = re.compile(r'msgstr ""\n\n', re.DOTALL)
RE_CHARSET = re.compile(r'"Content-Type: text/plain; charset=(.*?)\\n"', re.DOTALL)
ESCAPE_RAW = r'\\(?:$|.)'
ESCAPE_BYTES = r'''\\(?:$|[\\'"abfnrtv]|[0-7]{1,3}|x[0-9a-fA-F]{2})'''
ESCAPE_UNIICODE = _or(ESCAPE_BYTES, r'\\(?:N\{[^}]+\}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})')
ESCAPE_LENIENT = r'\\.'
LITERALS = _or(
	r"'''(?:[^'\\]|%(esc)s|'[^']|''[^'])*?'''",
	r'"""(?:[^"\\]|%(esc)s|"[^"]|""[^"])*?"""',
	r"'(?:[^'\\\n]|%(esc)s)*?'",
	r'"(?:[^"\\\n]|%(esc)s)*?"',
)
MATCHED_RAW = r'\b%s%s' % (
	_or('[Rr]', '[BbFfUu][Rr]', '[Rr][BbFf]'),  # (ur|ru) only in 2, (rb) since 3.3
	LITERALS % dict(esc=ESCAPE_RAW),
)
MATCHED_BYTES = r'\b[Bb]%s' % (
	LITERALS % dict(esc=ESCAPE_BYTES),
)
MATCHED_UNICODE = r'(?:\b[FfUu])?%s' % (  # [u] not in 3.0-3.2, [f] since 3.6
	LITERALS % dict(esc=ESCAPE_UNIICODE),
)
MATCHED_LENIENT = r'(?:\b[BbFfRrUu]{1,2})?%s' % (
	LITERALS % dict(esc=ESCAPE_LENIENT),
)
MATCHED_STRING = _or(MATCHED_RAW, MATCHED_BYTES, MATCHED_UNICODE)  # name='str'
COMMENT = _or(r'#[^\n]*$')  # name='cmt'
NON_STRING = r"""[^'"#\n]"""
CONTEXT = _or(NON_STRING, MATCHED_STRING)
SEPARATOR = r"[([{\s,:]"
TRANSLATION = r"(_\(\s*" + MATCHED_STRING + r"\s*%\s*(?:[^\n]+\))?)"
RE_TRANSLATION = re.compile(CONTEXT + SEPARATOR + TRANSLATION, re.DOTALL | re.MULTILINE | re.VERBOSE)


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):

	def getMsgIds(self):
		return {
			'0008-1': (uub.RESULT_ERROR, 'substitutes before translation'),
			'0008-2': (uub.RESULT_WARN, 'failed to open file'),
			'0008-3': (uub.RESULT_ERROR, 'po-file contains "fuzzy" string'),
			'0008-4': (uub.RESULT_WARN, 'po-file contains empty msg string'),
			'0008-5': (uub.RESULT_ERROR, 'po-file contains no character set definition'),
			'0008-6': (uub.RESULT_ERROR, 'po-file contains invalid character set definition'),
		}

	def postinit(self, path):
		""" checks to be run before real check or to create precalculated data for several runs. Only called once! """

	def check(self, path):
		""" the real check """
		super(UniventionPackageCheck, self).check(path)

		py_files = []
		po_files = []
		for fn in uub.FilteredDirWalkGenerator(path, suffixes=('.py', '.po')):
			if fn.endswith('.py'):
				py_files.append(fn)
			if fn.endswith('.po'):
				po_files.append(fn)

		self.check_py(py_files)
		self.check_po(po_files)

	def check_py(self, py_files):
		"""Check Python files."""
		for fn in py_files:
			try:
				content = open(fn, 'r', 'utf-8').read()
			except EnvironmentError:
				self.addmsg('0008-2', 'failed to open and read file', filename=fn)
				continue
			self.debug('testing %s' % fn)
			for regex in (RE_TRANSLATION,):
				pos = 0
				while True:
					match = regex.search(content, pos)
					if not match:
						break
					else:
						line = content.count('\n', 0, match.start()) + 1
						pos = match.end()
						self.addmsg('0008-1', 'substitutes before translation: %s' % match.group(1), fn, line)

	def check_po(self, po_files):
		"""Check Portable Object files."""
		for fn in po_files:
			try:
				content = open(fn, 'r', 'utf-8', 'replace').read()
			except EnvironmentError:
				self.addmsg('0008-2', 'failed to open and read file', fn)
				continue

			match = RE_CHARSET.search(content)
			if not match:
				self.addmsg('0008-5', 'cannot find charset definition', fn)
			elif not match.group(1).lower() in ('utf-8'):
				self.addmsg('0008-6', 'invalid charset (%s) defined' % (match.group(1)), fn)

			self.debug('testing %s' % fn)
			for regex, errid, errtxt in [
				(RE_FUZZY, '0008-3', 'contains "fuzzy"'),
				(RE_EMPTY, '0008-4', 'contains empty msgstr')
			]:
				pos = 0
				while True:
					match = regex.search(content, pos)
					if not match:
						break
					else:
						# match.start() + 1 ==> avoid wrong line numbers because RE_FUZZY starts with \n
						line = content.count('\n', 0, match.start() + 1) + 1
						pos = match.end()
						self.addmsg(errid, errtxt, fn, line)
