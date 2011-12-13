/*
 * Univention Directory Listener
 *  handler.c
 *
 * Copyright 2004-2010 Univention GmbH
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

/*
 * The Python handlers (and possibly, C and Shell handlers in the future)
 * are initialized and run here.
 */

#define _GNU_SOURCE /* asprintf */

#include <dirent.h>
#include <string.h>
#include <stdlib.h>
#include <sys/types.h>
#include <python2.4/Python.h>
#include <python2.4/compile.h>
#include <python2.4/marshal.h>
#include <python2.4/node.h>
#include <univention/debug.h>

#include "cache_lowlevel.h"
#include "base64.h"
#include "common.h"
#include "filter.h"
#include "handlers.h"

extern int INIT_ONLY;
extern char *cache_dir;
extern char **module_dirs;
extern int module_dir_count;

Handler *handlers = NULL;

/* Import a Python module (source or compiled) the same way __import__ does.
   Unfortunately there doesn't seem to be any higher level interface for this.
   I agree this isn't very intuitive. */
static PyObject* module_import(char *filename)
{
	/* It is essential that every module is imported under a different name;
	   This used to be strdup("") which caused the modules to get overwritten,
	   and as a consequence thereof, the handlers were called with a different
	   module providing the global variables, which messed up big time;
	   This is due to the fact that Python remembers which modules have already
	   been imported even in these low-level functions */
	char *name = strdup(filename);
	char *namep;
	FILE *fp;
	PyCodeObject *co;
	PyObject *m;

	if ((fp = fopen(filename, "r")) == NULL)
		return NULL;
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "Load file %s", filename);
	
	namep = strrchr(filename, '.');
	if ((namep != NULL) && (strcmp(namep, ".pyo") == 0)) {
		long magic;
		
		magic = PyMarshal_ReadLongFromFile(fp);
		/* we should probably check the magic here */
		(void) PyMarshal_ReadLongFromFile(fp);

		co = (PyCodeObject*) PyMarshal_ReadLastObjectFromFile(fp);
	} else {
		node *n;

		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Parse file %s", filename);
		if ((n = PyParser_SimpleParseFile(fp, filename, Py_file_input)) == NULL) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Parse failed %s", filename);
			return NULL;
		}
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "pyNode compile %s", filename);
		co = PyNode_Compile(n, filename);
		PyNode_Free(n);
	}
	fclose(fp);
	
	if (co == NULL || !PyCode_Check(co)) {
		Py_XDECREF(co);
		free(name);
		return NULL;
	}

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "execCodeModuleEx %s", filename);
	m = PyImport_ExecCodeModuleEx(name, (PyObject*) co, filename);
	free(name);
	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "Module done %s", filename);

	return m;
}

static PyObject* module_get_object(PyObject *module, char *name)
{
	if (!PyObject_HasAttrString(module, name))
		return NULL;
	return PyObject_GetAttrString(module, name);
}

static char* module_get_string(PyObject *module, char *name)
{
	PyObject *var;
	char *str1, *str2;

	if ((var=PyObject_GetAttrString(module, name)) == NULL)
		return NULL;
	PyArg_Parse(var, "s", &str1);
	str2 = strdup(str1);
	Py_DECREF(var);

	return str2;
}

static char** module_get_string_list(PyObject *module, char *name)
{
	PyObject *list;
	char **res;
	int len, i;

	if ((list=PyObject_GetAttrString(module, name)) == NULL)
		return NULL;
	if (!PyList_Check(list)) {
		Py_DECREF(list);
		return NULL;
	}
	
	len = PyList_Size(list);
	if ((res = malloc((len+1)*sizeof(char*))) == NULL) {
		Py_DECREF(list);
		return NULL;
	}
	for (i = 0; i < len; i++) {
		PyObject *var;
		var = PyList_GetItem(list, i);
		res[i] = strdup(PyString_AsString(var));
		Py_DECREF(var);
	}
	res[len] = NULL;
	Py_DECREF(list);

	return res;
}

/* load handler and insert it into list of handlers */
static int handler_import(char* filename)
{
	char *filter;
	int num_filters;
	char *state_filename;
	FILE *state_fp;
	Handler *handler;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "importing handler %s", filename);

	if ((handler = malloc(sizeof(Handler))) == NULL)
		return 1;
	memset(handler, 0, sizeof(Handler));

	if ((handler->module=module_import(filename)) == NULL) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "import of filename=%s failed", filename);
		PyErr_Print();
		free(handler);
		return 1;
	}
	
	handler->name = module_get_string(handler->module, "name");
	if ( PyObject_HasAttrString(handler->module, "modrdn")) {
		handler->modrdn = module_get_string(handler->module, "modrdn");
	} else {
		handler->modrdn = NULL;
	}
	handler->description = module_get_string(handler->module, "description");

	num_filters = 0;
	if ((filter = module_get_string(handler->module, "filter")) != NULL) {
		handler->filters = realloc(handler->filters, (num_filters+2)*sizeof(struct filter*));
		handler->filters[0] = malloc(sizeof(struct filter));
		handler->filters[0]->base = NULL;
		handler->filters[0]->scope = LDAP_SCOPE_SUBTREE;
		handler->filters[0]->filter = filter;
		num_filters++;
		handler->filters[num_filters] = NULL;
	}
	if (PyObject_HasAttrString(handler->module, "filters")) {
		PyObject *filters = PyObject_GetAttrString(handler->module, "filters");
		int len = PyList_Size(filters), i;
		handler->filters = realloc(handler->filters, (num_filters+len+1)*sizeof(struct filter*));
		for (i = 0; i < len; i++) {
			PyObject *py_tuple = PyList_GetItem(filters, i);
			PyObject *py_base = PyTuple_GetItem(py_tuple, 0);
			PyObject *py_scope = PyTuple_GetItem(py_tuple, 1);
			PyObject *py_filter = PyTuple_GetItem(py_tuple, 2);
			
			handler->filters[num_filters] = malloc(sizeof(struct filter));
			handler->filters[num_filters]->base = strdup(PyString_AsString(py_base));
			handler->filters[num_filters]->scope = PyInt_AsLong(py_scope);
			handler->filters[num_filters]->filter = strdup(PyString_AsString(py_filter));
			num_filters++;
		}
		handler->filters[num_filters] = NULL;
		Py_DECREF(filters);
	}

	handler->attributes = module_get_string_list(handler->module, "attributes");

	handler->handler = module_get_object(handler->module, "handler");
	handler->initialize = module_get_object(handler->module, "initialize");
	handler->clean = module_get_object(handler->module, "clean");
	handler->prerun = module_get_object(handler->module, "prerun");
	handler->postrun = module_get_object(handler->module, "postrun");
	handler->setdata = module_get_object(handler->module, "setdata");

	/* read handler state */
	asprintf(&state_filename, "%s/handlers/%s", cache_dir, handler->name);
	state_fp = fopen(state_filename, "r");
	if (state_fp == NULL)
		handler->state = 0;
	else {
		fscanf(state_fp, "%d", &handler->state);
		fclose(state_fp);
	}
	free(state_filename);

	/* insert into list */
	if ( handlers == NULL ) {
		handler->next = handlers;
		handlers = handler;
	} else {
		Handler *tmp = handlers;

		while (tmp->next != NULL) {
			tmp = tmp->next;
		}
		tmp->next = handler;
		handler->next = NULL;
	}


	return 0;
}

/* run prerun handler; this only needs to be done once for multiple calls
   to the same handler until the postrun handler is run */
static int handler_prerun(Handler *handler)
{
	PyObject *result;

	if (handler->prerun == NULL || handler->prepared) {
		handler->prepared = 1;
		return 0;
	}
	if ((result = PyObject_CallObject(handler->prerun, NULL)) == NULL) {
		PyErr_Print();
		drop_privileges();
		return 1;
	}
	
	drop_privileges();
	handler->prepared=1;
	
	Py_DECREF(result);
	return 0;
}

/* run postrun handler */
static int handler_postrun(Handler *handler)
{
	PyObject *result;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "postrun handler: %s (prepared=%d)",
			handler->name, handler->prepared);
	if (handler->postrun == NULL || !handler->prepared)
		return 0;
	if ((result = PyObject_CallObject(handler->postrun, NULL)) == NULL) {
		PyErr_Print();
		drop_privileges();
		return 1;
	}
	
	drop_privileges();
	handler->prepared=0;
	
	Py_DECREF(result);
	return 0;
}

int handlers_postrun_all(void)
{
	Handler *cur;

	for (cur=handlers; cur != NULL; cur=cur->next) {
		handler_postrun(cur);
	}
	return 0;
}

/* execute handler with arguments */
static int handler_exec(Handler *handler, PyObject *argtuple)
{
	PyObject *result;
	int rv;

	if ((handler->state & HANDLER_READY) != HANDLER_READY) {
		if (INIT_ONLY) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (not ready) (ignore)", handler->name);
		} else {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (not ready)", handler->name);
			return 1;
		}
	}
	
	handler_prerun(handler);

	if ((result = PyObject_CallObject(handler->handler, argtuple)) == NULL) {
		PyErr_Print();
		return -1;
	}
	/* make sure that privileges are properly dropped in case the handler
	   does setuid() */
	drop_privileges();

	if (result != Py_None)
		rv=1;
	else
		rv=0;

	Py_DECREF(result);
	return rv;
}

/* call clean function of handler */
int handler_clean(Handler *handler)
{
	PyObject *result;

	if (handler->clean == NULL)
		return 0;
	
	if ((result = PyObject_CallObject(handler->clean, NULL)) == NULL) {
		PyErr_Print();
		drop_privileges();
		return 1;
	}
	
	drop_privileges();
	
	Py_DECREF(result);
	return 0;
}

int handlers_clean_all(void)
{
	Handler *cur;
	for (cur=handlers; cur != NULL; cur=cur->next) {
		handler_clean(cur);
	}
	return 0;
}

/* call handler's initialize function */
int handler_initialize(Handler *handler)
{
	PyObject *result;

	if (handler->initialize == NULL)
		return 0;
	if ((result = PyObject_CallObject(handler->initialize, NULL)) == NULL) {
		PyErr_Print();
		drop_privileges();
		return 1;
	}
	
	drop_privileges();
	
	Py_DECREF(result);
	return 0;
}

int handlers_initialize_all(void)
{
	Handler *cur;
	for (cur=handlers; cur != NULL; cur=cur->next) {
		handler_initialize(cur);
	}
	return 0;
}

static void handler_dump(Handler *handler)
{
	struct filter **filter;
	
	printf("name: %s\n", handler->name);
	printf("description: %s\n", handler->description);

	for (filter = handler->filters; filter != NULL; filter++) {
		printf("filter: %s %d %s\n", (*filter)->base, (*filter)->scope, (*filter)->filter);
	}
	
	printf("clean handler: %d\n", handler->clean != NULL);
	printf("initialize handler: %d\n", handler->initialize != NULL);
	printf("prerun handler: %d\n", handler->prerun != NULL);
	printf("postrun handler: %d\n", handler->postrun != NULL);
	printf("setdata handler: %d\n", handler->setdata != NULL);
}

int handlers_dump(void)
{
	Handler *handler;
	for (handler=handlers; handler != NULL; handler=handler->next)
		handler_dump(handler);

	return 0;
}

int handlers_load_path(char *path)
{
	struct stat st;
	int rv = 1;
	
	stat(path, &st);
	if (S_ISDIR(st.st_mode)) {
		DIR *dir;
		struct dirent *de;

		/* Load replication.py before any other module, so that it
		   gets considered first when initializing modules and stuff.
		   I don't think this is the right place, and it should
		   rather be done when actually initializing the modules,
		   but I'll leave it like this for now (RB). Anyway, we do
		   this so that other handler modules can rely on LDAP being
		   there */
		dir = opendir(path);
		while ((de = readdir(dir))) {
			if (strcmp(de->d_name, "replication.py") == 0) {
				char *filename;
				asprintf(&filename, "%s/%s", path, de->d_name);
				rv = handler_import(filename);
				free(filename);
			}
		}
		closedir(dir);

		dir = opendir(path);
		while ((de = readdir(dir))) {
			/* Don't load replication.py twice, of course */
			if (strcmp(de->d_name, "replication.py") != 0) {
				char *s = strrchr(de->d_name, '.');
				/* Only load *.py files */
				if ((s != NULL) && (strcmp(s, ".py") == 0)) {
				 	char *filename;
				 	asprintf(&filename, "%s/%s", path, de->d_name);
				 	rv = handler_import(filename);
				 	free(filename);
				}
			}
		}
		closedir(dir);
	} else if (S_ISREG(st.st_mode)) {
		handler_import(path);
	} else {
		return 1;
	}

	return rv;
}

int handlers_load_all_paths(void)
{
	char **module_dir;

	for (module_dir=module_dirs; module_dir != NULL && *module_dir != NULL; module_dir++) {
		handlers_load_path(*module_dir);
	}

	return 0;
}

int handler_free(Handler *handler)
{
	char **a;
	struct filter **f;
	char *state_filename;
	FILE *state_fp;

	if ( handler == NULL || handler->name == NULL ) {
		return 0;
	}
	
	/* write handler state */
	/* XXX: can be removed, once we use a database for this */
	asprintf(&state_filename, "%s/handlers/%s", cache_dir, handler->name);
	state_fp = fopen(state_filename, "w");
	if (state_fp == NULL) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "could not open %s", state_filename);
	} else {
		fprintf(state_fp, "%d", handler->state);
		fclose(state_fp);
	}
	free(state_filename);

	/* free list node */
	free(handler->name);
	free(handler->description);
	for (f = handler->filters; f != NULL && *f != NULL; f++) {
		free((*f)->base);
		free((*f)->filter);
		free(*f);
	}
	free(handler->filters);
	for (a = handler->attributes; a != NULL && *a != NULL; a++)
		free(*a);
	free(handler->attributes);
	Py_XDECREF(handler->module);
	Py_XDECREF(handler->handler);
	Py_XDECREF(handler->initialize);
	Py_XDECREF(handler->clean);
	Py_XDECREF(handler->prerun);
	Py_XDECREF(handler->postrun);

	return 0;
}

int handlers_free_all(void)
{
	Handler *cur;

	while (handlers != NULL) {
		cur = handlers;
		handlers = handlers->next;
		handler_free(cur);
		free(cur);
	}

	return 0;
}

int handlers_reload_all_paths(void)
{
	handlers_free_all();
	return handlers_load_all_paths();
}

int handlers_init(void)
{
	/* all byte-compiled Univention Python modules are compiled optimized,
	   so we'll better run handlers optimized as well */
	Py_OptimizeFlag++;
	Py_Initialize();
	handlers_load_all_paths();
	return 0;
}

/* convert our C entry structure into a Python dictionary */
static PyObject* handlers_entrydict(CacheEntry *entry)
{
	PyObject *entrydict;
	CacheEntryAttribute **attribute;

	if ((entrydict = PyDict_New()) == NULL)
		return NULL;

	if (entry == NULL)
		return entrydict;

	for (attribute=entry->attributes; attribute != NULL && *attribute != NULL; attribute++) {
		PyObject *valuelist, *s;
		char **value;
		int *length;

		/* make value list */
		if ((valuelist = PyList_New(0)) == NULL) {
			Py_DECREF (entrydict);
			return NULL;
		}
		for (value=(*attribute)->values, length=(*attribute)->length; value != NULL && *value != NULL; value++, *length++) {
			if (length!=NULL && *length != strlen(*value)) {
				s = PyString_FromStringAndSize(*value,*length-1);
			} else {
				s = PyString_FromString(*value);
			}
			PyList_Append(valuelist, s);
			Py_DECREF(s);
		}

		s = PyString_FromString((*attribute)->name);
		PyDict_SetItem(entrydict, s, valuelist);
		Py_DECREF(s);
		Py_DECREF(valuelist);
	}

	return entrydict;
}

/* build Python argument tuple for handler */
static PyObject* handlers_argtuple(char *dn, CacheEntry *new, CacheEntry *old)
{
	PyObject *argtuple;
	PyObject *newdict;
	PyObject *olddict;

	/* make argument list */
	if ((argtuple = PyTuple_New(3)) == NULL)
		return NULL;
	newdict = handlers_entrydict(new);
	olddict = handlers_entrydict(old);

	/* PyTuple_SetItem steals a reference. Thus there's no need to
	   DECREF the objects */
	PyTuple_SetItem(argtuple, 0, PyString_FromString(dn));
	PyTuple_SetItem(argtuple, 1, newdict);
	PyTuple_SetItem(argtuple, 2, olddict);

	return argtuple;
}
static PyObject* handlers_argtuple_command(char *dn, CacheEntry *new, CacheEntry *old, char *command)
{
	PyObject *argtuple;
	PyObject *newdict;
	PyObject *olddict;

	/* make argument list */
	if ((argtuple = PyTuple_New(4)) == NULL)
		return NULL;
	newdict = handlers_entrydict(new);
	olddict = handlers_entrydict(old);

	/* PyTuple_SetItem steals a reference. Thus there's no need to
	   DECREF the objects */
	PyTuple_SetItem(argtuple, 0, PyString_FromString(dn));
	PyTuple_SetItem(argtuple, 1, newdict);
	PyTuple_SetItem(argtuple, 2, olddict);
	PyTuple_SetItem(argtuple, 3, PyString_FromString(command));

	return argtuple;
}

/* return boolean indicating whether attribute has changed */
int attribute_has_changed(char** changes, char* attribute)
{
	char **cur;

	for (cur = changes; cur != NULL && *cur != NULL; cur++) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "%s ? %s", *cur, attribute);
		if (strcmp(*cur, attribute) == 0)
			return 1;
	}

	return 0;
}


/* a little more low-level interface than handler_update */
static int handler__update(Handler *handler, char *dn, CacheEntry *new, CacheEntry *old, PyObject *argtuple, char **changes, CacheEntry *scratch)
{
	int matched;
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "handler: %s considered", handler->name);

	/* check if attributes for handler have changed */
	if (cache_entry_module_present(old, handler->name)) {
		char **cur;
		int uptodate = 0;

		if (changes == NULL) {
			uptodate = 1;
			goto up_to_date;
		}
		for (cur = handler->attributes; cur != NULL && *cur != NULL; cur++) {
			if (attribute_has_changed(changes, *cur))
				break;
		}
		if (cur != NULL && *cur == NULL && handler->attributes != NULL && *handler->attributes != NULL) {
			uptodate = 1;
			goto up_to_date;
		}

	up_to_date:
		if (uptodate) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (up-to-date)", handler->name);
			cache_entry_module_add(new, handler->name);
			if ( scratch != NULL ) {
				cache_entry_module_add(scratch, handler->name);
			}
			return 0;
		}
	}

	/* check if the handler's search filter matches */
	matched = cache_entry_ldap_filter_match(handler->filters, dn, new);
	if (!matched) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ALL, "handler: %s (filter doesn't match)", handler->name);
		return 0;
	}

	/* run handler */
	if (handler_exec(handler, argtuple) == 0) {
		cache_entry_module_add(new, handler->name);
		if ( scratch != NULL ) {
			cache_entry_module_add(scratch, handler->name);
		}
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (successful)", handler->name);
	} else {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "handler: %s (failed)", handler->name);
		rv=1;
	}

	return rv;
}

/* run all handlers if object has changed */
int handlers_update(char *dn, CacheEntry *new, CacheEntry *old, char command, CacheEntry *scratch)
{
	PyObject *argtuple;
	PyObject *argtuple_command;
	Handler *handler;
	char** changes;
	int rv = 0;
	char cmd[2];

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "running handlers for %s", dn);

	changes = cache_entry_changed_attributes(new, old);
	argtuple = handlers_argtuple(dn, new, old);
	cmd[0]=command;
	cmd[1]='\0';
	argtuple_command = handlers_argtuple_command(dn, new, old, cmd);

	for (handler=handlers; handler != NULL; handler=handler->next) {
		if (!strcmp(handler->name, "replication")) {
			handler__update(handler, dn, new, old, argtuple, changes, scratch);
		}
	}
	for (handler=handlers; handler != NULL; handler=handler->next) {
		if (strcmp(handler->name, "replication")) {
			if ( handler->modrdn ) {
				handler__update(handler, dn, new, old, argtuple_command, changes, scratch);
			} else {
				handler__update(handler, dn, new, old, argtuple, changes, scratch);
			}
		}
	}
	
	Py_DECREF(argtuple);
	Py_DECREF(argtuple_command);
	free(changes);
	
	return rv;
}

/* run given handler if object has changed */
int handler_update(char *dn, CacheEntry *new, CacheEntry *old, Handler *handler, char command, CacheEntry *scratch)
{
	PyObject *argtuple;
	PyObject *argtuple_command;
	char** changes;
	int rv = 0;
	char cmd[2];

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "running handlers [%s] for %s", handler->name, dn);

	changes = cache_entry_changed_attributes(new, old);
	argtuple = handlers_argtuple(dn, new, old);
	cmd[0]=command;
	cmd[1]='\0';
	argtuple_command = handlers_argtuple_command(dn, new, old, cmd);

	if ( handler->modrdn ) {
		rv = handler__update(handler, dn, new, old, argtuple_command, changes, scratch);
	} else {
		rv = handler__update(handler, dn, new, old, argtuple, changes, scratch);
	}

	Py_DECREF(argtuple);
	Py_DECREF(argtuple_command);
	free(changes);
	
	return rv;
}

/* run handlers if object has been deleted */
int handlers_delete(char *dn, CacheEntry *old, char command)
{
	PyObject *argtuple;
	PyObject *argtuple_command;
	Handler *handler;
	char cmd[2];
	int rv = 0;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "delete handlers for %s", dn);
	argtuple = handlers_argtuple(dn, NULL, old);
	cmd[0]=command;
	cmd[1]='\0';
	argtuple_command = handlers_argtuple_command(dn, NULL, old, cmd);

	for (handler=handlers; handler != NULL; handler=handler->next) {
		if (!cache_entry_module_present(old, handler->name)) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (skipped)", handler->name);
			continue;
		}
		if ( handler->modrdn ) {
			if (handler_exec(handler, argtuple_command) == 0) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (successful)", handler->name);
				cache_entry_module_remove(old, handler->name);
			} else {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (failed)", handler->name);
				rv=1;
			}
		} else {
			if (handler_exec(handler, argtuple) == 0) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (successful)", handler->name);
				cache_entry_module_remove(old, handler->name);
			} else {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "handler: %s (failed)", handler->name);
				rv=1;
			}
		}
	}
	
	Py_DECREF(argtuple);
	Py_DECREF(argtuple_command);

	return rv;
}

/* build filter to match objects for all modules */
char* handlers_filter(void)
{
	return NULL;
}

int handler_set_data(Handler *handler, PyObject *argtuple)
{
	PyObject *result;
	int rv;

	if (handler == NULL)
		return 0;

	if (handler->setdata == NULL)
		return 0;

	if ((result = PyObject_CallObject(handler->setdata, argtuple)) == NULL) {
		PyErr_Print();
		return -1;
	}
	/* make sure that privileges are properly dropped in case the handler
	   does setuid() */
	drop_privileges();

	if (result != Py_None)
		rv=1;
	else
		rv=0;

	Py_DECREF(result);
	return rv;
}

int handlers_set_data_all(char *key, char *value)
{
	Handler *handler;
	PyObject *argtuple;
	int rv = 1;

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "setting data for all handlers: key=%s  value=%s", key, value);

	/* make argument list */
	if ((argtuple = PyTuple_New(2)) == NULL)
		return -1;

	PyTuple_SetItem(argtuple, 0, PyString_FromString(key));
	PyTuple_SetItem(argtuple, 1, PyString_FromString(value));

	univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "DEBUG: handlers=%p", handlers);
	if (handlers == NULL)
		return 0;

	for (handler=handlers; handler != NULL; handler=handler->next) {
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "DEBUG: handler=%p", handler);
		if (handler_set_data(handler, argtuple) < 0)
			rv = -1;
	}

	Py_DECREF(argtuple);

	return 1;
}
