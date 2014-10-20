/*
 * Copyright 2014 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/promise/all",
	"dijit/layout/ContentPane",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/Wizard",
	"umc/widgets/ContainerWidget",
	"umc/widgets/LabelPane",
	"umc/widgets/Form",
	"umc/widgets/ComboBox",
	"umc/widgets/Text",
	"umc/widgets/TextBox",
	"umc/widgets/HiddenInput",
	"umc/widgets/Tree",
	"umc/widgets/RadioButton",
	"umc/modules/uvmm/TreeModel",
	"umc/modules/uvmm/types",
	"umc/i18n!umc/modules/uvmm"
], function(declare, lang, array, all, ContentPane, tools, dialog, Wizard, ContainerWidget, LabelPane, Form, ComboBox, Text, TextBox, HiddenInput, Tree, RadioButton, TreeModel, types, _) {

	return declare("umc.modules.uvmm.CreatePage", [ Wizard ], {
		umcpCommand: null,
		_generalForm: null,
		_tree: null,

		postMixInProperties: function() {
			this.inherited(arguments);

			/* ... for node or cloud */
			var _getNodes = lang.hitch(this, function() {
				var deferreds = [];
				deferreds.push(this.umcpCommand('uvmm/node/query'));
				deferreds.push(this.umcpCommand('uvmm/cloud/query'));

				return all(deferreds).then(lang.hitch(this, function(results) {
					var servers = [];
					array.forEach(results, function(iresult) {
						array.forEach(iresult.result, function(iserver) {
							if (tools.isTrue(iserver.available)) {
								servers.push(iserver);
							}
						});
					});
					return servers;
				}));
			});

			/* ... for cloud type */
			var _getCloudTypes = lang.hitch(this, function() {
				var deferreds = [];
				deferreds.push(this.umcpCommand('uvmm/cloudtype/get'));

				return all(deferreds).then(lang.hitch(this, function(results) {
					var types = [];
					array.forEach(results, function(iresult) {
						array.forEach(iresult.result, function(itype) {
							types.push(itype);
						});
					});
					return types;
				}));
			});

			lang.mixin(this, {
				headerText: _('Create a virtual machine'),
				helpText: _('Select the cloud in which a new virtual machine instance is going to be created. Alternatively, it is possible to register a new cloud connection.'),
				headerButtons: [{
					name: 'close',
					iconClass: 'umcCloseIconWhite',
					label: _('Back to overview'),
					callback: lang.hitch(this, 'onCancel')
				}],
				footerButtons: [{
					label: _('Next'),
					defaultButton: true,
					name: 'next',
					callback: lang.hitch(this, '_finish')
				}],
				pages: [{
					name: 'general',
					headerText: _('Create a virtual machine or a cloud connection'),
					helpText: _('Select if you want to create a new machine at a specific location, or if you want to create a new cloud connection to a specific provider.'),
				        widgets: [{
						type: RadioButton,
						radioButtonGroup: 'type',
						name: 'vm',
						checked: true,
						label: _('Create a new virtual machine instance.'),
						onChange: lang.hitch(this, function(checked, widgets) {
							widgets.server.set('disabled', !checked);
						})
					}, {
						type: ComboBox,
						name: 'server',
						dynamicValues: _getNodes,
						//depends: ['vm'],
						label: _('Where should the virtual machine instance be created'),
						labelConf: {'class': 'umc-ucssetup-wizard-indent'}
					}, {
						type: RadioButton,
						radioButtonGroup: 'type',
						name: 'cloud',
						label: _('Create a new cloud connection service account.'),
					}, {
						type: ComboBox,
						name: 'cloudtype',
						dynamicValues: _getCloudTypes,
						label: _('Which type of connection should be created'),
						labelConf: {'class': 'umc-ucssetup-wizard-indent'}
					}],
				}],
			});
		},

		_getSelectedServer: function() {
			var serverID = this.getWidget('server').get('value');
			var server = array.filter(this.getWidget('server').getAllItems(), function(item) {
				return item.id == serverID;
			});
			if (!server.length) {
				return null;
			}
			return server[0];
		},

		_getSelectedCloudType: function() {
			var cloudtypeID = this.getWidget('cloudtype').get('value');
			var cloudtype = array.filter(this.getWidget('cloudtype').getAllItems(), function(item) {
				return item.id == cloudtypeID;
			});
			if (!cloudtype.length) {
				return null;
			}
			return cloudtype[0];
		},

		getValues: function() {
			// save the type that shall be created
			var values = {};

			var type = this.getWidget('general', 'vm').get('value') ? 'vm' : 'cloud';

			values.type = type;
			var server = this._getSelectedServer();
			var cloudtype = this._getSelectedCloudType();
			if (type == 'vm' && server.type == 'cloud') {
				values.type = 'instance';
				values.cloud = server.id;
				values.cloudtype = server.cloudtype;
			}
			else if (type == 'vm' && server.type == 'node') {
				values.type = 'domain';
				values.nodeURI = server.id;
			} else if (type == 'cloud') {
				values.cloudtype = cloudtype.id;
			}
			return values;
		},

		_finish: function() {
			// trigger finished event
			this.onFinished(this.getValues());
		},
	});
});
