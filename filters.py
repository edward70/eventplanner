# https://stackoverflow.com/questions/62984099/jinja2-mark-specific-html-tag-as-safe

import re
from jinja2 import evalcontextfilter, Markup, escape

_paragraph_re = re.compile(r'(\n)')

@evalcontextfilter
def nl2br(eval_ctx, value):

    result = ''.join('%s' % p.replace('\n', Markup('<br>'))
        for p in _paragraph_re.split(escape(value)))

    if eval_ctx.autoescape:
        result = Markup(result)

    return result