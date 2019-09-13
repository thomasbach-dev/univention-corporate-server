#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Configuration Registry
#  add and remove nfs shares from the LDAP directory to /etc/fstab
#
# Copyright 2004-2019 Univention GmbH
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

from __future__ import print_function
from argparse import ArgumentParser
import os
import univention.config_registry
import ldap
import univention.uldap
import sys
import subprocess
import shlex
from io import StringIO

configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()
verbose = False

ldap_hostdn = configRegistry.get('ldap/hostdn')

MAGIC_LDAP = '#LDAP Entry DN:'


def debug(msg, out=sys.stderr):
	"""Print verbose information 'msg' to 'out'."""
	if verbose:
		print(msg, end=' ', file=out)


def exit(result, message=None):
	"""Exit with optional error message."""
	script = os.path.basename(sys.argv[0])
	if message:
		print('%s: %s' % (script, message), file=sys.stderr)
	sys.exit(result)


def query_policy(dn):
	"""Get NFS shares from LDAP as per policy for dn."""
	nfsmount = set()
	debug('Retrieving policy for %s...\n' % dn)
	try:
		p = subprocess.Popen(['univention_policy_result', '-D', ldap_hostdn, '-y', '/etc/machine.secret', '-s', dn], stdout=subprocess.PIPE)
		stdout, stderr = p.communicate()
	except OSError:
		exit(1, "FAIL: failed to execute `univention_policy_result %s'" % dn)
	for line in stdout.splitlines():
		line = line.rstrip('\n')
		k, v = line.split('=', 1)
		debug("Retrieved %s=%s\n" % (k, v))
		if k == 'univentionNFSMounts':
			v, = shlex.split(v)
			debug("Found %s\n" % v)
			nfsmount.add(v)
	return nfsmount


def main():
	# parse command line
	parser = ArgumentParser()
	parser.add_argument('--simulate', '-s', action='store_true', help='simulate update and just show actions')
	parser.add_argument('--verbose', '-v', action='store_true', help='print verbose information')
	args = parser.parse_args()

	if args.verbose:
			global verbose
			verbose = True

	hostdn = configRegistry.get('ldap/hostdn')
	if not hostdn:
		print("Error: ldap/hostdn is not set.", file=sys.stderr)
		exit(1)
	debug("Hostdn is %s\n" % hostdn)

	nfsmounts = query_policy(hostdn)

	lo = univention.uldap.getMachineConnection()

	# remove all nfs mounts from the fstab
	debug("Rewriting /etc/fstab...\n")
	fstabNew = "/etc/fstab.new.%d" % os.getpid()
	sources = set()
	mount_points = set()
	try:
		with open('/etc/fstab', 'r') as f_old:
			if args.simulate:
				# f_new = os.fdopen(os.dup(sys.stderr.fileno()), "w")
				f_new = StringIO()
			else:
				f_new = open(fstabNew, 'w')

			for line in f_old:
				if MAGIC_LDAP not in line:
					f_new.write(line)
					debug("= %s" % line)
				else:
					debug("- %s" % line)

				if line.startswith('#'):
					continue

				line = line.rstrip('\n')
				fields = line.split(' ')  # source_spec mount_point fs options freq passno

				sp = fields[0]
				sources.add(sp)

				try:
					mp = fields[1]
					if not mp.startswith('#'):
						mount_points.add(mp)
				except IndexError:
					pass
	except IOError as e:
		exit(1, e)

	fqdn = "%(hostname)s.%(domainname)s" % configRegistry
	to_mount = set()
	for nfsmount in nfsmounts:
		debug("NFS Mount: %s ..." % nfsmount)
		fields = nfsmount.split(' ')  # dn_univentionShareNFS mount_point
		dn = fields[0]
		if not dn:
			debug('no dn, skipping\n')
			continue

		try:
			result = lo.lo.search_s(
				dn,
				ldap.SCOPE_SUBTREE,
				'objectclass=*',
				attrlist=['univentionShareHost', 'univentionSharePath'])
		except ldap.NO_SUCH_OBJECT:
			continue

		try:
			attributes = result[0][1]
			share_host = attributes['univentionShareHost'][0]
			share_path = attributes['univentionSharePath'][0]
		except LookupError:
			debug('not found, skipping\n')
			continue

		mp = fields[-1] or share_path
		# skip share if target already in fstab
		if mp in mount_points:
			debug('already mounted on %s, skipping\n' % mp)
			continue

		# skip share if from self
		if share_host == fqdn and share_path == mp:
			debug('is self, skipping\n')
			continue

		nfs_path_fqdn = "%s:%s" % (share_host, share_path)
		# skip share if the source is already in the fstab
		if nfs_path_fqdn in sources:
			debug('already mounted from %s, skipping\n' % nfs_path_fqdn)
			continue

		# get the ip of the share_host
		hostname, domain = share_host.split('.', 1)
		result = lo.lo.search_s(configRegistry['ldap/base'], ldap.SCOPE_SUBTREE, '(&(relativeDomainName=%s)(zoneName=%s))' % (hostname, domain), attrlist=['aRecord'])
		try:
			attributes = result[0][1]
			nfs_path_ip = "%s:%s" % (attributes['aRecord'][0], share_path)
		except LookupError:
			nfs_path_ip = nfs_path_fqdn

		# skip share if the source is already in the fstab
		if nfs_path_ip in sources:
			debug('already mounted from %s, skipping\n' % nfs_path_ip)
			continue

		line = "%s\t%s\tnfs\tdefaults\t0\t0\t%s %s\n" % (nfs_path_ip, mp, MAGIC_LDAP, dn)
		f_new.write(line)
		debug("\n+ %s" % line)
		to_mount.add(mp)

	f_new.close()
	debug('Switching /etc/fstab...\n')
	if not args.simulate:
		if os.path.isfile(fstabNew) and os.path.getsize(fstabNew) > 0:
			os.rename(fstabNew, '/etc/fstab')

	with open('/etc/mtab', 'r') as fp:
		for line in fp:
			line = line.rstrip('\n')
			fields = line.split(' ')  # source_spec mount_point fs options freq passno
			to_mount.discard(fields[1])

	for mp in sorted(to_mount):
		if not os.path.exists(mp):
			os.makedirs(mp)
		debug('Mounting %s...\n' % mp)
		if not args.simulate:
			subprocess.Popen(['mount', mp])


if __name__ == '__main__':
	main()
