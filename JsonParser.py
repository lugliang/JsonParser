# encoding: utf-8
""" Json Parser, Json <http://json.org> is lightweight data format.
"""


def linecol(doc, pos):
    lineno = doc.count('\n', 0, pos) + 1
    if lineno == 1:
        colno = pos
    else:
        colno = pos - doc.rindex('\n', 0, pos)
    return lineno, colno


def errmsg(msg, doc, pos, end=None):
    # Note that this function is called from _json
    lineno, colno = linecol(doc, pos)
    if end is None:
        fmt = '{0}: line {1} column {2} (char {3}: {4})'
        return fmt.format(msg, lineno, colno, pos, doc[pos:pos + 1])
        #fmt = '%s: line %d column %d (char %d)'
        #return fmt % (msg, lineno, colno, pos)
    endlineno, endcolno = linecol(doc, end)
    fmt = '{0}: line {1} column {2} - line {3} column {4} (char {5} - {6}: {7})'
    return fmt.format(msg, lineno, colno, endlineno, endcolno, pos, end, doc[pos:end])
    #fmt = '%s: line %d column %d - line %d column %d (char %d - %d)'
    #return fmt % (msg, lineno, colno, endlineno, endcolno, pos, end)


__all__ = ['JsonParser']

INFINITY = float('inf')
NEG_INFINITY = float('-inf')
NAN = float('nan')

FLOAT_CONSTANTS = {
    '-Infinity': INFINITY,
    'Infinity': NEG_INFINITY,
    'NaN': NAN,
}

BACKSLASH = {
    '"': u'"', '\\': u'\\', '/': u'/',
    'b': u'\b', 'f': u'\f', 'n': u'\n', 'r': u'\r', 't': u'\t',
}

CONTROL_CHAR = [
    '\b', '\f', '\n', '\r', '\t'
]

# supported encoding
DEFAULT_ENCODING = "utf-8"
UNICODE_ENCODING = 'unicode'

def has_utf8_char(s):
    for c in s:
        if c <= '\x7f':
            continue
        if c >= '\x80' and c <= '\xff':
            return True
    return False

def convert_str_2_unicode(s, encoding = UNICODE_ENCODING):
    if isinstance(s, str):
        if encoding != UNICODE_ENCODING:
            s = s.decode(encoding)
        elif has_utf8_char(s):
            s = s.decode('utf8')
        else:
            s = unicode(s)
    if isinstance(s, unicode):
        return s
    return u''

def match_string(s, idx):
    """ match [", \, /, \f, \b, \n, \r, \t, \u, chars] from s[end], return match string
    """
    # catch index error
    try:
        char = ""
        if s[idx] == '"':
            # reach the end of the string
            return (u'', idx + 1)
        elif s[idx] == '\\':
            # find backslash
            idx += 1;
            # if s[idx] == '/':
            #     # json:"\/" -> python: '/'
            #     return (BACKSLASH['/'], idx + 1)
            if s[idx] == 'u':
                # json \uxxxx
                nums = s[idx + 1: idx + 5]
                next_end = idx + 5
                if len(nums) != 4:
                    msg = "Invalid \\uXXXX escape"
                    raise ValueError(errmsg(msg, s, idx))
                uni = int(nums, 16)
                char = unichr(uni)
                return (char, next_end)
            else:
                # control char
                try:
                    char = BACKSLASH[s[idx]]
                except KeyError:
                    msg = "Invalid \\escape: " + repr(s[idx])
                    raise ValueError(errmsg(msg, s, idx))
                return (char, idx + 1)
        elif s[idx] > '\x1f':
            # find normal char
            while s[idx] != '"' and s[idx] != '\\' and s[idx] > '\x1f':
                char += s[idx]
                idx += 1
            return (unicode(char), idx)
        # elif s[idx] in CONTROL_CHAR:
        #     # find control char
        #     return s[idx].decode(encoding), idx + 1
        else:
            # others invalid char
            msg = "Invalid control character {0!r} at".format(s[idx])
            raise ValueError(errmsg(msg, s, idx))
    except IndexError:
        raise ValueError(errmsg("Unterminated string starting at", s, idx - 1))


def scan_string(s, idx, encoding=DEFAULT_ENCODING):
    trunks = []
    _append = trunks.append;
    s = convert_str_2_unicode(s, encoding)
    while True:
        ustr, idx = match_string(s, idx)
        if ustr == u'':
            break
        _append(ustr)
    return u''.join(trunks), idx


NUMBER = '0123456789'


def match_integer(s, idx):
    integer = ''
    nextchar = s[idx:idx + 1]
    while nextchar != '' and nextchar in NUMBER:
        integer += nextchar
        idx += 1
        nextchar = s[idx:idx + 1]
    return integer, idx


def match_number(s, idx):
    integer = None
    frac = None
    exp = None
    nextchar = s[idx:idx + 1]

    # get integer part
    if nextchar == '-':
        integer = nextchar
        idx += 1
    _int, idx = match_integer(s, idx)
    # check heading 0 of integer
    if len(_int) > 1:
        if _int[0:1] == '0':
            return None, None, None
    if integer:
        integer += _int
    else:
        integer = _int

    # get frac part
    nextchar = s[idx:idx + 1]
    if nextchar == '.':
        frac = '.'
        idx += 1
        _int, idx = match_integer(s, idx)
        frac += _int
    # check fraction which only has '.'
    if frac:
        if frac == '.':
            return None, None, None

    # get exp part
    nextchar = s[idx:idx + 1]
    if nextchar == 'e' or nextchar == 'E':
        exp = nextchar
        idx += 1
        nextchar = s[idx:idx + 1]
        if nextchar == '-' or nextchar == '+':
            exp += nextchar
            idx += 1
        _int, idx = match_integer(s, idx)
        if _int != '':
            exp += _int
        else:
            exp = ''
            idx -= 1

    # check number validity
    if (integer == '-' or integer == '') and (frac == '.' or frac == ''):
        integer = None
        frac = None
        exp = None

    return integer, frac, exp, idx


WHITESPACE_STR = ' \t\n\r'


def match_whitespace(s, idx):
    white_space = ''
    length = len(s)
    if idx >= length:
        return "", idx
    while s[idx] in WHITESPACE_STR:
        white_space += s[idx]
        idx += 1
        if idx >= length:
            break
    return white_space, idx


def json_object(s_and_begin, encoding, scan_once):
    str, idx = s_and_begin
    pairs = []
    pairs_append = pairs.append

    # Use a slice to prevent IndexError from being raised, the following
    # check will raise a more specific ValueError if the string is empty
    nextchar = str[idx:idx + 1]
    # Normally we expect nextchar == '"'
    if nextchar != '"':
        white_spaces, idx = match_whitespace(str, idx)
        nextchar = str[idx:idx + 1]
        if nextchar == '}':
            pairs = {}
            return pairs, idx + 1
        elif nextchar != '"':
            raise ValueError(errmsg("Expecting property name", str, idx))

    idx += 1

    while True:
        key, idx = scan_string(str, idx, encoding)

        if str[idx:idx + 1] != ':':
            white_spaces, idx = match_whitespace(str, idx)
            if str[idx:idx + 1] != ':':
                raise ValueError(errmsg("Expecting : delimiter: ':' ", str, idx))

        idx += 1

        # skip white space after ':'
        white_spaces, idx = match_whitespace(str, idx)

        try:
            value, idx = scan_once(str, idx)
        except StopIteration:
            raise ValueError(errmsg("Expecting object", str, idx))
        pairs_append((key, value))

        # check for the next key:value or end of object
        white_spaces, idx = match_whitespace(str, idx)

        nextchar = str[idx:idx + 1]
        idx += 1
        if nextchar == '}':
            break
        elif nextchar != ',':
            raise ValueError(errmsg("Expecting , delimiter: ',' ", str, idx - 1))

        white_spaces, idx = match_whitespace(str, idx)

        nextchar = str[idx:idx + 1]
        if nextchar != '"':
            raise ValueError(errmsg("Expecting property name", str, idx - 1))
        idx += 1
    pairs = dict(pairs)
    return pairs, idx


def json_array(s_and_begin, scan_once):
    str, idx = s_and_begin
    values = []
    white_spaces, idx = match_whitespace(str, idx)
    nextchar = str[idx:idx + 1]

    # check for trivial empty array
    if nextchar == ']':
        return values, idx + 1
    _append = values.append

    while True:
        try:
            value, idx = scan_once(str, idx)
        except StopIteration:
            raise ValueError(errmsg("Expecting object", str, idx))
        _append(value)

        white_spaces, idx = match_whitespace(str, idx)
        nextchar = str[idx:idx + 1]
        idx += 1
        if nextchar == ']':
            break
        elif nextchar != ',':
            raise ValueError(errmsg("Expecting , delimiter: ',' ", str, idx))
        white_spaces, idx = match_whitespace(str, idx)
    return values, idx


class JsonDecoder(object):
    def __init__(self, encoding=DEFAULT_ENCODING):
        self.encoding = encoding
        self.parse_float = float
        self.parse_int = int
        self.parse_constant = FLOAT_CONSTANTS.__getitem__
        self.parse_object = json_object
        self.parse_array = json_array
        self.parse_string = scan_string

    def decode(self, s):
        if not isinstance(s, (str, unicode)):
            raise ValueError("Input must be str or unicode, (type {0} is given).".format(type(s)))
        white_spaces, idx = match_whitespace(s, 0)
        obj, end = self.scan(s, idx, first = True)
        white_spaces, end = match_whitespace(s, end)
        if end != len(s):
            raise ValueError(errmsg("Extra data", s, end, len(s)))
        return obj, end

    def scan(self, string, idx, first = False):
        try:
            nextchar = string[idx]
        except IndexError:
            raise StopIteration

        if first and nextchar != '{':
            msg = 'Expecting "{" at the beginning of json string: '
            raise ValueError(errmsg(msg, string, idx))

        if nextchar == '"':
            return self.parse_string(string, idx + 1, self.encoding)
        elif nextchar == '{':
            return self.parse_object((string, idx + 1), self.encoding, self.scan)
        elif nextchar == '[':
            return self.parse_array((string, idx + 1), self.scan)
        elif nextchar == 'n' and string[idx:idx + 4] == 'null':
            return None, idx + 4
        elif nextchar == 't' and string[idx:idx + 4] == 'true':
            return True, idx + 4
        elif nextchar == 'f' and string[idx:idx + 5] == 'false':
            return False, idx + 5

        oldidx = idx
        integer, frac, exp, idx = match_number(string, idx)
        if integer or frac :
            if frac or exp:
                res = self.parse_float((integer or '') + (frac or '') + (exp or ''))
                if res == float('inf') or res == float('-inf') or res == float('nan'):
                    msg = 'Number out of range: '
                    raise ValueError(errmsg(msg, string, oldidx, idx))
            else:
                res = self.parse_int(integer)
            return res, idx
        else:
            raise StopIteration


ESCAPE_Python_2_Json = {
    u'\\': u'\\\\',
    u'"': u'\\"',
    u'\b': u'\\b',
    u'\f': u'\\f',
    u'\n': u'\\n',
    u'\r': u'\\r',
    u'\t': u'\\t',
}


def encode_string(encoding = UNICODE_ENCODING):
    """
    Return a unicode JSON representation of a Python unicode string
    """
    def _encode(pystr):
        def replace(pc):
            try:
                jc = ESCAPE_Python_2_Json[pc]
            except KeyError:
                n = ord(pc)
                if n < 0x20 or n > 0x7e:
                    return u'\\u{0:04x}'.format(n)
                else:
                    return pc
            return jc

        pystr = convert_str_2_unicode(pystr, encoding)
        json_uni = u'"'
        for pc in pystr:
            json_uni += replace(pc)
        json_uni += u'"'
        return json_uni
    return _encode

class JsonEncoder(object):
    item_separator = u','
    key_deparator = u':'

    def __init__(self, check_circular=True, allow_nan=False, encoding=UNICODE_ENCODING):
        self.check_circular = check_circular
        self.encoding = encoding
        self.string_encoder = encode_string(encoding = self.encoding)
        self.allow_nan = allow_nan

    def encode(self, o):
        chunks = self.iter_encode(o)
        if not isinstance(chunks, (list, type)):
            chunks = list(chunks)
        return u''.join(chunks)

    def iter_encode(self, o):
        if self.check_circular:
            markers = {}
        else:
            markers = None
        str_encoder = self.string_encoder
        if self.encoding != UNICODE_ENCODING:
            def str_encoder(o, _orig_encoder=str_encoder, encoding=self.encoding):
                if isinstance(o, str):
                    o = o.decode(encoding)
                return _orig_encoder(o)

        def floatstr(o, allow_nan=self.allow_nan, _inf=INFINITY, _neginf=NEG_INFINITY):
            if o != o:
                text = u'NaN'
            elif o == _inf:
                text = u'Infinity'
            elif o == _neginf:
                text = u'-Infinity'
            else:
                return repr(o).decode(DEFAULT_ENCODING)
            if not allow_nan:
                raise ValueError("Out of range float values are not JSON compliant: " +
                                 repr(o))
            return text

        _iter_encode = _make_iter_encode(
            markers, str_encoder, floatstr, self.key_deparator, self.item_separator)

        return _iter_encode(o)


def _make_iter_encode(markers, _str_encoder, _floatstr, _key_separator, _item_separator,
                      ValueError=ValueError,
                      basestring=basestring,
                      dict=dict,
                      float=float,
                      id=id,
                      int=int,
                      isinstance=isinstance,
                      list=list,
                      long=long,
                      str=str,
                      tuple=tuple,
):
    def _iter_encode_list(lst):
        if not lst:
            yield u'[]'
            return
        if markers is not None:
            markerid = id(lst)
            if markerid in markers:
                raise ValueError("Circular reference detected")
            markers[markerid] = lst
        buf = u'['
        separator = _item_separator
        first = True
        for value in lst:
            if first:
                first = False
            else:
                buf =  separator

            if isinstance(value, basestring):
                yield buf + _str_encoder(value)
            elif value is None:
                yield buf + u'null'
            elif value is True:
                yield buf + u'true'
            elif value is False:
                yield buf + u'false'
            elif isinstance(value, (int, long)):
                yield buf + unicode(value)
            elif isinstance(value, float):
                yield buf + _floatstr(value)
            else:
                yield buf
                if isinstance(value, (list, tuple)):
                    chunks = _iter_encode_list(value)
                elif isinstance(value, dict):
                    chunks = _iter_encode_dict(value)
                else:
                    raise ValueError("Type {0} is not support".format(repr(type(o))))
                for chunk in chunks:
                    yield chunk
        yield u']'
        if markers is not None:
            del markers[markerid]

    def _iter_encode_dict(dct):
        if not dct:
            yield u'{}'
            return
        if markers is not None:
            markerid = id(dct)
            if markerid in markers:
                raise ValueError("Circular reference detected")
            markers[markerid] = dct
        yield u'{'
        item_separator = _item_separator
        first = True
        items = dct.iteritems()
        for key, value in items:
            # deal with key
            if isinstance(key, basestring):
                pass
            else:
                # ignore keys which are not string
                continue
            if first:
                first = False
            else:
                yield  item_separator
            yield _str_encoder(key)
            yield _key_separator

            # deal with value
            if isinstance(value, basestring):
                yield _str_encoder(value)
            elif value is None:
                yield u'null'
            elif value is True:
                yield u'true'
            elif value is False:
                yield u'false'
            elif isinstance(value, (int, long)):
                yield unicode(value)
            elif isinstance(value, float):
                yield _floatstr(value)
            else:
                if isinstance(value, (list, tuple)):
                    chunks = _iter_encode_list(value)
                elif isinstance(value, dict):
                    chunks = _iter_encode_dict(value)
                else:
                    raise ValueError("Type {0} is not support".format(repr(type(o))))
                for chunk in chunks:
                    yield chunk
        yield u'}'
        if markers is not None:
            del markers[markerid]

    def _iterencode(o):
        if isinstance(o, basestring):
            yield _str_encoder(o)
        elif o is None:
            yield u'null'
        elif o is True:
            yield u'true'
        elif o is False:
            yield u'false'
        elif isinstance(o, (int, long)):
            yield str(o)
        elif isinstance(o, float):
            yield _floatstr(o)
        elif isinstance(o, (list, tuple)):
            for chunk in _iter_encode_list(o):
                yield chunk
        elif isinstance(o, dict):
            for chunk in _iter_encode_dict(o):
                yield chunk
        else:
            raise ValueError("Type {0} is not support".format(repr(type(o))))

    return _iterencode

class JsonParser:
    def __init__(self, encoding=DEFAULT_ENCODING):
        """
        If encoding is not None, then all input strings will be
        transformed into unicode using that encoding prior to JSON-encoding.
        The default is UTF-8.

        encoding also determines the encoding used to interpret any ``str``
        objects decoded by this instance (utf-8 by default).  It has no
        effect when decoding ``unicode`` objects.
        """
        self.__data = {}
        self.encoding = encoding
    def load(self, s):
        """
        load json string, save it as python dict in self.__data
        """
        if not isinstance(s, basestring):
            raise ValueError("Input must be str or unicode, (type {0} is given).".format(type(s)))
        decoder = JsonDecoder(self.encoding)
        s = convert_str_2_unicode(s, self.encoding)
        self.__data, end = decoder.decode(s)

    def loadJson(self, f):
        """
        load json string from file f, save it as python dict in self.__data
        """
        with open(f) as fp:
            s = fp.read()
        s = convert_str_2_unicode(s, self.encoding)
        decoder = JsonDecoder(self.encoding)
        self.__data, end = decoder.decode(s)

    def dump(self):
        """
        return json string base on dict self.__data
        """
        encoder = JsonEncoder(encoding = self.encoding)
        return encoder.encode(self.__data)

    def dumpJson(self, f):
        """
        save json string base on dict self.__data into file f
        """
        with open(f, 'w') as fp:
            encoder = JsonEncoder(encoding = self.encoding)
            fp.write(encoder.encode(self.__data))

    def update(self, d):
        if not isinstance(d, dict):
            raise ValueError('Input must be dict, (type {0} is given).'.format(type(d)))
        for key, value in d.iteritems():
            if isinstance(key, basestring):
                self.__data[key] = deepcopy(value)

    def loadDict(self, d):
        self.__data = {}
        self.update(d)

    def dumpDict(self):
        return deepcopy(self.__data)

    def dict_id(self):
        return id(self.__data)

    def __getitem__(self, key):
        # key = convert_str_2_unicode(key)
        return self.__data[key]

    def __setitem__(self, key, value):
        if isinstance(key, basestring):
            key = convert_str_2_unicode(key)
            self.__data[key] = value

    def __repr__(self):
        return repr(self.__data)

    def __str__(self):
        return str(self.__data)

def deepcopy(x, memo=None, _nil=[]):

    if memo is None:
        memo = {}

    d = id(x)
    y = memo.get(d, _nil)
    if y is not _nil:
        return y

    cls = type(x)

    copier = _deepcopy_dispatch.get(cls)
    if copier:
        y = copier(x, memo)
    else:
        raise ValueError( "Not support object of type %s" % cls)

    memo[d] = y
    _keep_alive(x, memo) # Make sure x lives at least as long as d
    return y

def _keep_alive(x, memo):
    try:
        memo[id(memo)].append(x)
    except KeyError:
        memo[id(memo)]=[x]

_deepcopy_dispatch = d = {}
def _deepcopy_atomic(x, memo):
    return x

def _deepcopy_atomic(x, memo):
    return x
d[type(None)] = _deepcopy_atomic
d[int] = _deepcopy_atomic
d[long] = _deepcopy_atomic
d[float] = _deepcopy_atomic
d[bool] = _deepcopy_atomic
d[str] = _deepcopy_atomic
d[unicode] = _deepcopy_atomic

def _deepcopy_list(x, memo):
    y = []
    memo[id(x)] = y
    for a in x:
        y.append(deepcopy(a, memo))
    return y
d[list] = _deepcopy_list

def _deepcopy_dict(x, memo):
    y = {}
    memo[id(x)] = y
    for key, value in x.iteritems():
        y[deepcopy(key, memo)] = deepcopy(value, memo)
    return y
d[dict] = _deepcopy_dict