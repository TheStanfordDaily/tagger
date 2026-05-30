import re
from collections import OrderedDict
from unidecode import unidecode
from bs4 import BeautifulSoup

NON_TEXT_TAGS = ["img", "figure", "figcaption", "video", "audio", "iframe", "embed", "object", "svg"]

regex_tags = {
    r'\<script src(.*?)\</script>': '',
    r'\<blockquote class((.|\n)*?)\</blockquote>': '',
    r'\<a href(.*?)\<img(.*?)/>\</a>': '',
    r'\[caption id(.*?)\[/caption]': '',
    r'\<a href(.*?)>(.*?)\</a>': r'\2',
    r'\<span(.*?)>(.*?)\</span>': r'\2',
    r' \'(\d\d)': r' <\#213>\1',
    r'  +': r' ',
    r' +\n': r'\n',
}

tags = OrderedDict([
    (('<b>', '<strong>'), '<@CEBold>'),
    (('<i>', '<em>'), '<@CEIt>'),
    (('</b>', '</strong>', '</i>', '</em>'), '<@$p>'),
    ((' -- ', '--', ' - '), '<\\p><\\_><\\p>'),
    ((' ... ', '...'), '<\\p>...<\\p>'),
    (('&nbsp;',), ''),
    (('&amp;',), '&'),
    (('\n\n\n', '\n\n',), '\n'),
    (('\n<@CEBold>',), '\n\n<@CEBold>'),
    (('\n',), '\n\t'),
    (('\n\t\n',), '\n\n'),
    (('\n\t<@CEBold>',), '\n<@CEBold>'),
])


def html_to_xquark(html: str) -> str:
    """Convert formatted HTML to XQuarkXPress tagged text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(NON_TEXT_TAGS):
        tag.decompose()
    for p in soup.find_all("p"):
        italic = p.find(["em", "i"])
        if italic and re.match(r"(Update|Correction):", italic.get_text().strip(), re.IGNORECASE):
            p.decompose()
    text = unidecode(str(soup))

    for pattern, replacement in regex_tags.items():
        text = re.sub(re.compile(pattern), replacement, text)

    for html_tags, xquark_tag in tags.items():
        if xquark_tag == '\n\t':
            text = '\t' + text
        for tag in html_tags:
            text = text.replace(tag, xquark_tag)

    # Handle bullet lists
    text = re.sub(r'</?ul>', '', text)
    text = re.sub(r'</li>', '', text)
    text = re.sub(r'[\t ]*<li>', r'@Bullet indent:<@Bullet>l<@\\$p><\\i> ', text)

    # Remove empty inline tags
    text = re.sub(r'<@\w+>\s+<@\$p>', '', text)

    # Fix doubled em-dash markers
    text = re.sub(r'<\\p><\\p>', r'<\\p>', text)

    # Handle dropcap second-paragraph tab
    dropcap = re.search(r'<.*\*d.*>', text)
    if dropcap:
        text = re.sub(r'\t', '', text, count=1)
        text = re.sub(r'\t', '<*d(0)>\t', text, count=1)

    # Widen dropcap width for opening quotation marks
    text = re.sub(r'\*d\(1\,(\d)\)>([<>az$9]*)?"', r'*d(2,\1)>\2"', text)

    return text.rstrip()
