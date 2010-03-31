
from django import template
from django.template import Node, TemplateSyntaxError, Variable
from django.conf import settings

from BeautifulSoup import BeautifulSoup, NavigableString
from cairotext import get_png_size, TextImage, render_text

try:
    from hashlib import md5
except ImportError:
    from md5 import md5
import struct
from urlparse import urljoin
from os import remove, rename
from os.path import join, abspath, exists, split
from pprint import pformat

CAIROTEXT_PARSER_PRESETS = settings.CAIROTEXT_PARSER_PRESETS

register = template.Library()

def get_text_image(params, text, namespace="default"):
    # The code in this function is copied from cairotext and slightly modified.
    try:
        presets = CAIROTEXT_PARSER_PRESETS
        params = dict(presets[namespace][params])
    except (AttributeError, KeyError):
        raise KeyError('Preset "%s" in namespace "%s" not found in '
                               'settings.CAIROTEXT_PARSER_PRESETS' % (params, namespace))

    name = md5(text.encode('UTF-8') + pformat(params)).hexdigest()
    render_dir = getattr(settings, 'CAIROTEXT_DIR', 'cairotext_cache')
    filename = '%s.png' % name
    fileurl = urljoin(settings.MEDIA_URL, join(render_dir, filename))
    filepath = join(settings.MEDIA_ROOT, render_dir, filename)
    size = None
    if not exists(filepath):
        size = render_text(text, filepath, params)

    pngsize = get_png_size(filepath)
    assert size is None or size == pngsize, \
       'size mismatch: expected %rx%r, got %rx%r' % (size+pngsize)
    text_img = TextImage(fileurl, filepath, pngsize)
    
    return text_img


class CairoTextParser(template.Node):
    def __init__(self, nodelist, namespace):
        self.nodelist = nodelist
        self.namespace = namespace
        
    
    def convert_node(self, node, tag_name, text):
        text_img = get_text_image(tag_name, text, namespace=self.namespace)
            
        style = "text-indent:-99999px; background: url(%(url)s) bottom left no-repeat;\
            display: block; width: %(width)spx; height: %(height)spx;" % {
            "width": text_img.width,
            "height": text_img.height,
            "url": text_img.url,   
        }
        if node.has_key("style"):
            node["style"] = ";".join(style, node["style"])
        else:
            node["style"] = style
    
    def convert_tags(self, soup, tag_name):
        for node in soup.findAll(tag_name):
            
            # Get all text from the node and its children.
            def traverse(n, text):
                for c in n:
                    if isinstance(c, NavigableString):
                        text.append(c)
                    if getattr(c, "contents", None):
                        return traverse(c.contents, text)
                return text
            
            # If there is a link, and it has text, use it. Place the image on the link.
            # Oterwise place the image on the node.
            text = None
            link = node.find("a")
            if link:
                text = traverse(link, [])
                if text:
                    node = link
                    text = unicode(u"".join(text))
                    node = link
            if not text:
                text = traverse(node, [])
                text = unicode(u"".join(text))
            
            self.convert_node(node, tag_name, text)
        return soup
        
    def render(self, context):
        self.context = context
        namespace = self.namespace
        if namespace[0] in ("'", '"') and namespace[0] == namespace[-1]:
            namespace = namespace[1:-1]
        else:
            namespace = Variable(namespace).resolve(context)
        self.namespace = namespace
        output = self.nodelist.render(context)
        soup = BeautifulSoup(output, convertEntities=BeautifulSoup.HTML_ENTITIES )
        
        for tag_name in CAIROTEXT_PARSER_PRESETS[namespace].keys():
            soup = self.convert_tags(soup, tag_name)
        return soup


def do_cairotext_parser(parser, token):
    error_string = '%r tag accepts one optional argument.' % token.contents[0]
    try:
        # split_contents() knows not to split quoted strings.
        bits = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(error_string)
    if len(bits) == 2:
        namespace = bits[1]
    elif len(bits) == 1:
        namespace = "'default'"
    else:
        raise template.TemplateSyntaxError(error_string)
    
    
    nodelist = parser.parse(('endcairotext_parser',))
    parser.delete_first_token()
    return CairoTextParser(nodelist, namespace=namespace)
do_cairotext_parser = register.tag('cairotext_parser', do_cairotext_parser)


