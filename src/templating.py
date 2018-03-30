#8< ---[templating.py]---
#!/usr/bin/env python
"""Templating defines a simple templating language that is designed to work
very well with data serialized as JSON. Templates instruction all have the
same syntax:

>    ${DIRECTIVE:PARAMS...}

The available directives are the follwing;

'${resolve:NAME}'::
'${resolve:NAME.NAME}'::
'${resolve:NAME|format}'::
Resolves the variable with the given NAME in the current context. The
variable NAME supports dot-notation, such as 'item.name' (in which
case 'item' is expected to be a dict) or 'item.0' in which case
item is expected to be a list.

In case you are iterating on an object, the current object is accesible
by the 'this' variable (like 'this.name') as the scope defaults to the
global scope.

'${if:NAME}...${end}::
'${if:NAME(OPERATOR VALUE)}...${end}::
'${if:NAME}...[${elif:NAME OPERATOR VALUE}...](${else}...)${end}::
Will skip the content '...' if 'NAME' cannot be resolved or resolves
to either 'null', '0', '{}' or '[]'.
You can additionally provide an
expression with an OPERATOR (`==`, `!=`, `>`, `<`, `<=` and `>=`) with
a value that's either a (quoted) string or a number.

'${for:NAME}...${end}::
'${for:NAME}...(${empty}...)${end}::
Will iterate on the elements contained in the value returned by the
resolution of 'NAME'. This expects that this value is either a list
or a dict (in which case iteration will happen on the values). If
the value is not iterable, the block '...' won't be processed.

'${T:LANG="STRING",...}'::
Expands to the string bound to the 'LANG' key, where 'LANG' denotes
a language (typically 'en', 'fr', 'es', etc.)."""

import sys
import re, sys, json, cgi, types

__version__       = "0.8.7"
IS_PYTHON3        = (sys.version_info[0] > 2)
DEFAULT_LOCALE    = 'en'
DEFAULT_ENCODING  = 'utf-8'
TRANSLATION       = '\\w+=(\'[^\']+\'|"[^"]+"|[^},]+)'
RE_DIRECTIVE      = re.compile('((?P<prefix>\n\\s*)\\$\\{(?P<contentA>[^\\}]+)\\})|(\\$\\{(?P<contentB>[^\\}]+)\\})')
RE_VARIABLE       = re.compile('([A-Za-z0-9]+(\\.[A-Za-z_0-9]+)*)(\\:[\\w\\s\\,]+)?(\\|[\\w\\d\\+]+)?')
RE_CONTROL        = re.compile('(if|else|for|with|end)(:([^\\}]+))?')
RE_TRANSLATION    = re.compile((((('T\\:(' + TRANSLATION) + '(,') + TRANSLATION) + ')*)'))
RE_EXPRESSION     = re.compile('^\\s*([A-Za-z0-9\\.]+)\\s*(\\=\\=|\\!\\=)?([^$]*)$')

TRANSLATE_DEFAULT = 'default'
TRANSLATE_STRICT  = 'strict'

FORMATTERS        = {'json':json.dumps, 'escapeHTML':cgi.escape, 'repr':repr}

OP_RESOLVE        = 'resolve'
OP_IF             = 'if'
OP_ELSE           = 'else'
OP_FOR            = 'for'
OP_WITH           = 'with'
OP_END            = 'end'
OP_TRANSLATE      = 'T'
TYPE_LIST         = 'list'
TYPE_MAP          = 'map'
TYPE_STRING       = 'string'

# -----------------------------------------------------------------------------
#
# ABSTRACT TYPE
#
# -----------------------------------------------------------------------------

class Type(object):

	def __init__( self ):
		self.attributes = None

	def setAttributes(self, attributes):
		self.attributes = attributes

	def export(self):
		if self.attributes:
			return {'value':'Any', 'attributes':self.attributes}
		else:
			return 'Any'

# -----------------------------------------------------------------------------
#
# LIST TYPE
#
# -----------------------------------------------------------------------------

class ListType(object):

	def __init__( self ):
		self.content = None

	def defineSlot(self, slotName, slotType=None):
		if self.content is None:
			self.content = MapType()
			res = self.content.defineSlot(slotName, slotType)
			return res
		elif isinstance(self.content, MapType):
			res=self.content.defineSlot(slotName, slotType)
			return res
		else:
			raise Exception("Incompatible slot types: {0} != {1}".format(self.content, slotType))

	def export(self):
		if self.content:
			return [self.content.export()]
		else:
			return [Type().export()]

# -----------------------------------------------------------------------------
#
# MAP TYPE
#
# -----------------------------------------------------------------------------

class MapType:

	def __init__( self ):
		self.content = {}
		self.order = []

	def defineSlot(self, slotName, slotValue=None):
		if slotValue is None: slotValue = None
		names = slotName.split('.', 1)
		name  = names[0]
		if (slotValue is None):
			slotValue = Type()
		if len(names) == 1:
			if (not (name in self.order)):
				self.order.append(name)
			self.content[name] = slotValue
			return slotValue
		else:
			if name not in self.content or isinstance(self.content[name], Type):
				if name not in self.order:
					self.order.append(name)
				self.content[name] = MapType()
			text = u""
			self.content[name].defineSlot('.'.join(names[1:]), slotValue)
			return slotValue

	def export(self):
		result = {'order':self.order, 'values':{}}
		values = result['values']
		for key, value in self.content.items():
			if (type(value) is str):
				values[key] = value
			else:
				values[key] = value.export()
		return result

# -----------------------------------------------------------------------------
#
# TEMPLATE
#
# -----------------------------------------------------------------------------

class Template(object):
	"""Creates a new template with the given source text"""

	FORMATTERS = FORMATTERS

	@classmethod
	def EnsureUnicode(self, t, encoding=None):
		if encoding is None: encoding = 'UTF8'
		if IS_PYTHON3:
			return t if isinstance(t, str) else str(t, encoding)
		else:
			return t if isinstance(t, unicode) else t.decode(encoding)


	@classmethod
	def IsString(self, t):
		if IS_PYTHON3:
			return isinstance(t, str)
		else:
			return isinstance(t, basestring)

	@classmethod
	def Decompose(self, source):
		result=[]
		offset=0
		source = self.EnsureUnicode(source)
		for re_match in RE_DIRECTIVE.finditer(source):
			result.append(source[offset:re_match.start()])
			directive = (re_match.group('contentA') or re_match.group('contentB'))
			prefix    = re_match.group('prefix')
			dir_match=RE_TRANSLATION.match(directive)
			if dir_match:
				# We found a `${T:en="...",fr=""}`
				result.append(prefix)
				translations = {}
				rest         = dir_match.group(1)
				text         = rest
				# This decomposes the translations in an hashtable.
				# For example 'en=Hello,fr=Bonjour' will be translated
				# to {en:Hello,fr:Bonjour}
				while rest:
					lang, rest=rest.split('=', 1)
					if rest[0] == "'":
						i = rest.find("'", 1)
						text = rest[1:i]
						rest = rest[(i + 1):]
					elif rest[0] == '"':
						i = rest.find('"', 1)
						text = rest[1:i]
						rest = rest[(i + 1):]
					else:
						i = rest.find(',')
						if i != -1:
							text = rest[0:i]
							rest = rest[(i + 1):]
						else:
							text = rest
							rest = None
					translations[lang.replace(',', '').lower()] = text
				result.append([OP_TRANSLATE, translations])
			else:
				# We found a `${if|for|with:...}`
				dir_match = RE_CONTROL.match(directive)
				if dir_match:
					op=dir_match.group(1)
					operand=dir_match.group(3)
					if op == OP_IF:
						result.append([OP_IF, operand])
					elif op == OP_ELSE:
						result.append([OP_ELSE])
					elif op == OP_FOR:
						operand_limit=operand.split('|')
						if len(operand_limit) == 1:
							result.append([OP_FOR, operand_limit[0], -1])
						else:
							result.append([OP_FOR, operand_limit[0], int(operand_limit[1])])
					elif op == OP_WITH:
						result.append([OP_WITH, operand])
					elif op == OP_END:
						result.append([OP_END, operand])
					else:
						raise Exception(('Unrecognized operation: ' + op))
				else:
					# We found a ${name} or ${name|format}
					dir_match = RE_VARIABLE.match(directive)
					if dir_match:
						attributes = dir_match.group(3)
						format     = dir_match.group(4)
						if attributes:
							attributes = attributes[1:].split(',')
						if format:
							format = format[1:].split('+')
						else:
							format = []
						result.append([OP_RESOLVE, dir_match.group(1), attributes, format, prefix])
					else:
						raise Exception((("Unrecognized directive: '" + directive) + "'"))
			offset = re_match.end()
		result.append(source[offset:])
		return result

	def __init__ (self, source=None):
		self.encoding       = DEFAULT_ENCODING
		self.code           = []
		self.defaultLocale  = DEFAULT_LOCALE
		self.translateMode  = TRANSLATE_DEFAULT
		self.postProcessors = []
		self.setSource(source)

	def setSource(self, source=None):
		"""Sets the source tring that will be used to define this template"""
		self.code = Template.Decompose(source)

	def addPostProcessor(self, processor):
		if processor:
			self.postProcessors.append(processor)
		return self

	def listVariables(self):
		"""Returns the list of variables defined in the template. This is useful
		if you want to check that all the requirements to apply the template
		are met."""
		variables = []
		parsed    = {}
		for operation in self.code:
			if isinstance(operation, list) and (operation[0] == OP_RESOLVE):
				variable = operation[1]
				if variable not in parsed:
					parsed[variable] = True
					variables.append(variable)
		return variables

	def listTranslations(self):
		"""Returns the list of translations defined in the template"""
		strings = []
		for operation in self.code:
			if isinstance(operation, list) and operation[0] == OP_TRANSLATE:
				strings.append(operation[1])
		return strings

	def getInformation(self):
		"""Returns the list of variables defined in the template"""
		type_sig = MapType()
		context  = []
		current  = type_sig
		prefix   = ''
		for operation in self.code:
			# FIXME: Not ideal
			if isinstance(operation, list):
				name = self._getAbsoluteSlotName(operation, prefix)
				if operation[0] == OP_RESOLVE:
					current.defineSlot(name).setAttributes(operation[2])
				elif operation[0] == OP_TRANSLATE:
					pass
				elif operation[0] == OP_FOR:
					current.defineSlot(name, ListType())
					context.append([prefix])
					prefix = name
				elif operation[0] == OP_WITH:
					current.defineSlot(name, MapType())
					context.append([prefix])
					prefix = name
				elif operation[0] == OP_END:
					prefix = context[-1][0]
					context.pop()
				else:
					raise Exception(('Unknown operation:' + str(operation)))
		return type_sig

	def _getSlotName(self, operation, prefix):
		"""Returns the slot name of the given operation. Operation is expected to
		be like:

		>   [OPCODE, SLOT NAME?, ...]"""
		name = None
		# First argument of operations is always the name (or so we assume)
		if len(operation) > 1:
			name = operation[1]
		return name

	def _getAbsoluteSlotName(self, operation, prefix):
		"""Returns the absolute slot name of the given oepration. This will
		basically replace "this." with the current prefix."""
		name = None
		# FIXME: This could be simplified
		if len(operation) >= 1:
			name = operation[1]
			if name and isinstance(name, str):
				has_this = name == 'this' or name.find('this.') == 0
				if has_this:
					name = name[len('this'):]
					if name and name[0] == '.':
						name = name[1:]
					if prefix:
						name = prefix + '.' + name
		return name

	def _resolveInContext(self, name, context):
		"""Returns the value bound to the given name (which can be
		a dot-separated expression) in the given context."""
		name_rest=name.split('.', 1)
		# TODO: Support array and map resolution
		if len(name_rest) == 1:
			name = name_rest[0]
			if context:
				index = None
				try:
					index = int(name)
				except Exception as e:
					index = None
				if (type(index) is int):
					return context[index]
				elif (type(context) is dict):
					return context.get(name)
				else:
					if hasattr(context, name):
						return getattr(context, name)
					else:
						return None
			else:
				return None
		else:
			if not context:
				return None
			else:
				name, rest = name_rest
				return self._resolveInContext(rest, self._resolveInContext(name, context))

	def _evaluateExpression(self, expression, context):
		"""Evaluates the given expression. The expression is
		a context resulotion expression, an operator
		and a primitive value. This is used in the IF operation."""
		if expression:
			m      = RE_EXPRESSION.match(expression)
			name   = m.group(1)
			op     = m.group(2)
			rvalue = m.group(3)
			# We should do parsing instead of using json.loads
			lvalue = self._resolveInContext(name, context)
			if ((not op) and (rvalue == '?')):
				# This is the special case that supports empty
				# lists and maps?
				if   isinstance(lvalue, dict):
					return len([_ for _ in lvalue.values() if _])
				elif isinstance(lvalue, list) or isinstance(lvalue, tuple):
					return len([_ for _ in lvalue if _])
				else:
					return lvalue and True or False
			if rvalue:
				rvalue = json.loads(rvalue)
			if (op == '=='):
				return (lvalue == rvalue)
			elif (op == '!='):
				return (lvalue != rvalue)
			elif (op == '>'):
				return (lvalue > rvalue)
			elif (op == '<'):
				return (lvalue < rvalue)
			elif (op == '>='):
				return (lvalue >= rvalue)
			elif (op == '<='):
				return (lvalue <= rvalue)
			else:
				return lvalue
		else:
			return True

	def apply(self, context, locale=None, strict=None, formatters=None):
		"""Applies the given context data to this template. The given `locale` will
		tell how to expand translations, and `strict` will tell wether the lack
		of data will stop the template.

		This method is the one you'll use most often when using the Template class."""
		if locale is None: locale = 'en'
		if strict is None: strict = False
		formatters = formatters or self.FORMATTERS
		# Current dictionary where we resolve variables
		current    = context
		# Current stack of operation made of [OP_CODE, current, prefix, ARGS...]
		stack      = []
		# Current resolution prefix
		prefix     = ''
		# Array of result to be joined at the end
		result     = []
		# Wether we mute the output or not
		mute       = False
		i          = 0
		# We iterate on all the elements in the code (see Template.Decompose)
		while (i < len(self.code)):
			operation=self.code[i]
			if (type(operation) is list):
				# If the operation type is list, then it's an operation (not a string)
				name = self._getSlotName(operation, prefix)
				# NOTE: We should simply have a "this" slot for the current object,
				# and set it right there
				# [OP_RESOLVE, name, attributes, format]
				#  0           1     2           3
				if (operation[0] == OP_RESOLVE):
					replaced=self._resolveInContext(name, current)
					if (not mute):
						if (type(replaced) is dict):
							replaced = (replaced.get(locale) or replaced.get(self.defaultLocale))
						for format in operation[3]:
							replaced = FORMATTERS[format](replaced, locale, operation)
						if (replaced is None):
							result.append (u"[[ERROR: Missing variable {0}]]".format(name))
						elif self.__class__.IsString(replaced):
							result.append(self.__class__.EnsureUnicode(replaced, self.encoding))
						elif (type(replaced) in [int, long, float]):
							result.append(str(replaced))
						else:
							raise Exception(((("Expanded variable '" + name) + "' must be a string, got:") + repr(replaced)))
				elif (operation[0] == OP_TRANSLATE):
					if (not mute):
						translations=operation[1]
						if locale in translations:
							result.append(self.__class__.EnsureUnicode(translations.get(locale)))
						else:
							result.append(self.__class__.EnsureUnicode((((('[[ERROR: Missing translation for locale ' + str(locale)) + ' in ') + repr(translations)) + ']]')))
				elif (operation[0] == OP_IF):
					# As OP_IF may not execute, we store the mute state, which will
					# be restored when the corresponding OP_END will be invoked
					stack.append([OP_IF, current, prefix, current.get('this'), mute])
					mute = (mute or (not self._evaluateExpression(name, current)))
				elif (operation[0] == OP_ELSE):
					mute = (not mute)
				elif (operation[0] == OP_FOR):
					# As with OP_IF, we store the mute state as we might change it. We
					# also store the current context and prefix to restore it later
					collection=self._resolveInContext(name, current)
					stack.append([OP_FOR, current, prefix, i, 0, operation[2], collection, current.get('this'), mute])
					# Parent is used to store the object we're iterating on
					prefix   = self._getAbsoluteSlotName(name, prefix)
					is_empty = ((not collection) or (len(collection) == 0))
					if (not is_empty):
						current['this'] = collection[0]
						current['i'] = 0
					else:
						current['this'] = None
						current['i'] = -1
					mute = (mute or is_empty)
				elif (operation[0] == OP_WITH):
					stack.append([OP_WITH, current, prefix, current.get('this'), mute])
					# FIXME: I'm not even sure `current` is necessary, I think setting
					# the `this` is better (although there might be a conflict)
					current = self._resolveInContext(name, current)
					prefix = self._getAbsoluteSlotName(name, prefix)
				elif (operation[0] == OP_END):
					current = stack[-1][1]
					prefix = stack[-1][2]
					if (stack[-1][0] == OP_FOR):
						# If we're in a loop, then the stack head is
						# [OP_FOR, context, prefix, offset, start, limit, collection, mute]
						#  0       1        2       3       4      5      6           7
						j=(stack[-1][4] + 1)
						limit=stack[-1][5]
						collection=stack[-1][6]
						if collection:
							if (limit == -1):
								limit = len(collection)
							else:
								limit = min(limit, len(collection))
						else:
							limit = 0
						if (j < limit):
							# -- WITHIN ITERATION
							# If we have more elements available, we goto The
							# for offset and iterate again, with an increased
							# offset (j was already increased)
							# FIXME: Not sure what j is for
							i = stack[-1][3]
							current['this'] = collection[j]
							current['i'] = j
							s=stack[-1]
							s[4] = j
						else:
							# -- ITERATION END
							# If we don't have any element available, we
							# retrieve the content and prefix that existed
							# before the loop, and restore the mute status
							current = stack[-1][1]
							prefix = stack[-1][2]
							mute = stack[-1][-1]
							current['this'] = stack[-1][-2]
							current['i'] = j
							stack.pop()
					else:
						# Otherwise we just pop the result
						mute = stack[-1][-1]
						current['this'] = stack[-1][-2]
						current['i'] = -1
						stack.pop()
				else:
					raise Exception(('Unknown operation in templating.apply:' + str(operation)))
			else:
				# The element is not an operation, but a string, so we append
				# it to the result, except if it's mute
				if not mute:
					# NOTE: This special case is to support templates that start
					# with a directive. See `for-nested` test case.
					if ((((len(result) == 0) and (len(stack) > 0)) and operation) and (operation[0] == '\n')):
						op=stack[-1][0]
						if (((op == OP_FOR) or (op == OP_IF)) or (op == OP_WITH)):
							operation = operation[1:]
					if operation:
						result.append(self.__class__.EnsureUnicode(operation))
			i = (i + 1)
		result =  u"".join(result)
		for p in self.postProcessors:
			result = p(result, self)
		return result


# FORMATTERS["escapeQuotes"] = lambda v,l,o:v.replace('"', '\\"').replace("'", "\\'")
# FORMATTERS["lower"]        = lambda _,l,o:_.lower()
# def format_prefix(value, lang, operation):
# 	prefix = operation[4]
# 	if isinstance (prefix, str): prefix = prefix.decode("utf-8")
# 	return u"\n".join([(prefix + line) for line in value.split(u"\n")])
# FORMATTERS["prefix"] = format_prefix

# EOF
