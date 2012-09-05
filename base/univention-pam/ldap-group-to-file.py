#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention PAM
#   Dump all ldap groups with members to a single file
#
# Copyright 2011-2012 Univention GmbH
#
# http://www.univention.de/
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
# <http://www.gnu.org/licenses/>.

import univention.uldap
import optparse
import ldap
import string
import sys
import os
import tempfile


def _get_members(lo, g, recursion_list, check_member = False):
	result = []
	for m in g[1].get('uniqueMember', []):
		if m.startswith('uid='):
			# Does the member exist?
			if check_member:
				try:
					res = lo.search(base=m, scope=ldap.SCOPE_BASE, filter='uid=*', attr=['uid'])
					if len(res) < 1:
						# Not found
						continue
				except ldap.NO_SUCH_OBJECT:
					continue
			mrdn = ldap.explode_rdn(m)
			mname = string.join( string.split(mrdn[0],'=')[1:], '=')
			result.append(mname)
		elif m.startswith('cn='):
			try:
				members = lo.search(base=m, scope=ldap.SCOPE_BASE, filter='objectClass=*', attr=['uniqueMember', 'gidNumber', 'objectClass', 'cn'])
			except ldap.NO_SUCH_OBJECT:
				print m
				# Member not found
				continue

			if len(members) == 1:
				member = members[0]
			elif len(members) > 1:
				# Not possible
				continue
			else:
				# Member not found
				continue
			if 'univentionGroup' in member[1].get('objectClass', []):
				if member[0] not in recursion_list:
					recursion_list.append(g[0])
					result += _get_members(lo, member, recursion_list, options.check_member)
				else:
					# Recursion !!!
					pass
			else:
				result.append(member[1].get('cn')[0]+'$')
	return result

if __name__ == '__main__':
	parser = optparse.OptionParser( )
	parser.add_option("--file", dest="file", default='/var/lib/extrausers/group', action="store", help="write result to the given file, default is /var/lib/extrausers/group")
	parser.add_option("--verbose", dest="verbose", default=False, action="store_true", help="verbose output")
	parser.add_option("--check_member", dest="check_member", default=False, action="store_true", help="checks if the member exists")
	(options, args) = parser.parse_args()

	try:
		lo = univention.uldap.getMachineConnection()
	except ldap.SERVER_DOWN:
		print "Abort: Can't contact LDAP server."
		sys.exit(1)

	result = []
	groups = lo.search('objectClass=univentionGroup', attr=['uniqueMember', 'cn', 'gidNumber'])
	if options.verbose:
		print 'Found %d ldap groups' % len(groups)

	if len(groups) < 1:
		print 'Abort: Did not found any LDAP group.'
		sys.exit(1)
	

	# Write to a temporary file
	(fdtemp, fdname) = tempfile.mkstemp()
	fd = os.fdopen(fdtemp, 'w')

	for group in groups:
		rdn = ldap.explode_rdn(group[0])
		groupname = string.join( string.split(rdn[0],'=')[1:], '=')
		members=_get_members(lo, group, [], options.check_member)
		# The list(set(members)) call removes all duplicates from the group members
		fd.write('%s:*:%s:%s\n' % (groupname, group[1].get('gidNumber', [''])[0], string.join(list(set(members)), ',')))
	fd.close()

	os.chmod(fdname, 0644)

	# Replace the file
	os.rename(fdname, options.file)
	if options.verbose:
		print 'The file %s was created.' % options.file

	sys.exit(0)

