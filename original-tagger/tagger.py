# Author: Catherine Dong
# 9/30/14
# ------------------------------------------------------------------------------
# Updated: Do-Hyoung Park
# 1/30/15
# Added more staff writers/editors, added sports column header
# ------------------------------------------------------------------------------
# Updated: Stephanie Chen
# 2/16/16
# - updated directory, added new weekender italic tags
# - removes extra whitespace (doublespacing after periods, ends of paragraphs)
# - adds <*d(0)> on dropcaps articles
# - fixed arts (non weekender) header
# - added @ATTRIB for briefs
# - first letter should be handled (????)
#
# 10/2/16
# - moved weekender script to usage: python tagger.py tagging weekender
# -     note: but we don't use weekender anymore, yay
# -     also note: weekender script is buggy re: tabbing on bold/italic headers, italics on contact lines 
# 
# 10/12/16
# - drop letter details on quotation marks + "I" sentences
# ------------------------------------------------------------------------------
#
# STAFF LIST UPDATED: 9/21/16
#
# ------------------------------------------------------------------------------
# README:
# This program will convert a directory of .rtf files into tagged and formatted
# .txt files.
# 
# (1)   Create a new folder somewhere.
# (2)   For each article to be tagged, find the Wordpress post (though the admin
#       page, not online). Select the "Text" tab on the top right of the post 
#       content frame. This will display a stripped-down version of the text and
#       may contain HTML tags. Select all the text and copy/paste it into a new
#       TextEdit document. 
# (3)   Save the document:
#       - the file format should be "Rich Text Document"
#       - name the file using the usual convension but add a space followed by
#         the author's name at the end, e.g. "NEWassu26 Catherine Dong"
#       - save in the folder you created in step (1)
# (4)   
#
# USAGE:    python tagger.py [dirpath]
# e.g.:     python tagger.py /Users/Catherine/Documents/Daily/tagging
#
# NOTES: 
# - Must fill in @NewsHeader (NEWS) and Series Title (OPS) tags
# - Must replace FIRST LETTER in dropcaps (OPS and A&L)
# - Does not handle underlined text
#
# ISSUES:
# - blockquotes don't get deleted
# - identifies last paragraph as @@line if there is a tag with a @
# - class years followed by punctuation (Catherine '16, blablaba)

import subprocess
import sys
import os
import codecs
import re
from unidecode import unidecode
from collections import OrderedDict

weekender = False

if len(sys.argv) < 2:
    print('2nd argument required: directory to be processed, e.g. "tagging". Example usage: python tagger.py tagging')
    sys.exit()
if len(sys.argv) == 3 and sys.argv[2] == 'weekender':
    weekender = True




regex_tags = {
     r'\<script src(.*?)\</script>' : '',                   # remove twitter scripts
     r'\<blockquote class((.|\n)*?)\</blockquote>' : '',    # remove twitter blockquotes 
     r'\<a href(.*?)\<img(.*?)/>\</a>' : '',                # remove images
     r'\[caption id(.*?)\[/caption]' : '',                  # remove captions
     r'\<a href(.*?)>(.*?)\</a>' : r'\2',                   # remove links leaving text
     r'\<span(.*?)>(.*?)\</span>' : r'\2',
     r' \'(\d\d)' : r' <\#213>\1',                          # replace class year apostrophes
     r'  +' : r' ',                                         # remove double/triple spaces
     r' +\n': r'\n',                                        # remove spaces at ends of paragraphs
}

if not weekender:
    tags = OrderedDict([                        # WARNING: processing of this dict is order-sensitive
        (('<b>', '<strong>'),'<@CEBold>'),
        (('<i>', '<em>'), '<@CEIt>'),
        (('</b>', '</strong>', '</i>', '</em>'), '<@$p>'),
        ((' -- ', '--', ' - '), '<\p><\_><\p>'),
        ((' ... ', '...'), '<\p>...<\p>'),
        (('&nbsp;',), ''),
        (('&amp;',), '&'),
        (('\n\n\n', '\n\n',), '\n'),            # remove extra space between paragraphs
        (('\n<@CEBold>',), '\n\n<@CEBold>'),    # adds space before paragraphs that start bold (header)
        (('\n',), '\n\t'),                      # adds tabs to every paragraph
        (('\n\t\n',), '\n\n'),                  # removes tabs from empty lines
        (('\n\t<@CEBold>',), '\n<@CEBold>')     # removes tabs from paragraphs that start bold (header)
    ])
else: # weekender
    tags = OrderedDict([                        # WARNING: processing of this dict is order-sensitive
    (('<b>', '<strong>'),'<@WeidBold>'),
    (('<i>', '<em>'), '<@WeidmedItal>'),
    (('</b>', '</strong>', '</i>', '</em>'), '<@$p>'),
    ((' -- ', '--', ' - '), '<\p><\_><\p>'),
    ((' ... ', '...'), '<\p>...<\p>'),
    (('&nbsp;',), ''),
    (('&amp;',), '&'),
    (('\n\n\n', '\n\n',), '\n'),            # remove extra space between paragraphs
    (('\n<@CEBold>',), '\n\n<@WeidBold>'),    # adds space before paragraphs that start bold (header)
    (('\n',), '\n\t'),                      # adds tabs to every paragraph
    (('\n\t\n',), '\n\n'),                  # removes tabs from empty lines
    (('\n\t<@CEBold>',), '\n<@WeidBold>')     # removes tabs from paragraphs that start bold (header)
])

headers = {
    'NEW' :
    '<v9.21><e0>\n'
    '@NewsHeader:SECTION\n'
    '@byline:By AUTHOR\n'
    '@bysub:POSITION\n'
    '@normalcopy:\n',

    'SPO' :
    '<v9.21><e0>\n'
    '@byline:By AUTHOR\n'
    '@bysub:POSITION\n'
    '@normalcopy:\n',

    'OPS' :
    '<v9.21><e0>\n'
    'Series Title: Series\n'
    'Author: Name\n'
    'Column Title: Column\n'
    '@normalcopy:<*d(1,3)><z9>FIRST LETTER<z$>',

    'A&L' :
    '<v9.30><e0>\n'
    '@NewsHeader:SECTION\n'
    '@A&Lbyline:By AUTHOR\n'
    '@A&Lbysub:POSITION\n'
    '@normalcopy:\n'
    '<@A&Ldropcap><*bn(7.2,1,0)*d(1,6)>FIRST LETTER<@$p>',

    # For sports columns
    'SPC' :
    '<v9.21><e0>\n'
    '@normalcopy:<@SPOdrop><*d(1,5)><a$$>FIRST LETTER<@$p><t-6>',

    # sports briefs
    'SPB' :
    '<v9.21><e0>\n'
    '@SpoBrief:Title\n'
    '@normalcopy:\n',

    # news briefs
    'NEB' :
    '<v9.21><e0>\n'
    '@NEWSBRIEFS:Title\n'
    '@normalcopy:\n',

    # the grind
    'GRI' :
    '<v9.30><e0>\n'
    '@NewsHeader:SECTION\n'
    '@GRIbyline:By AUTHOR\n'
    '@GRIbysub:POSITION\n'
    '@normalcopy:\n'
    '<@GRIdropcap><*bn(7.2,1,0)*d(1,6)>FIRST LETTER<@$p>',

    # humor
    'HUM' :
    '<v9.30><e0>\n'
    '@NewsHeader:SECTION\n'
    '@HUMbyline:By AUTHOR\n'
    '@HUMbysub:POSITION\n'
    '@normalcopy:\n'
    '<@HUMdropcap><*bn(7.2,1,0)*d(1,6)>FIRST LETTER<@$p>',

    # police blotter
    'POL':
    '<v9.21><e0>\n'
    '@NewsHeader:CRIME & SAFETY\n'
    '@byline:By AUTHOR\n'
    '@bysub:POSITION\n'
    '@normalcopy:\n',
}

if weekender:
    headers['A&L'] = '<v9.30><e0>\n' + \
    '@A&Lbyline:By AUTHOR\n' + \
    '@A&Lbysub:POSITION\n' + \
    '@normalcopy:\n' + \
    '<@A&Ldropcap><*bn(7.2,1,0)*d(1,6)>FIRST LETTER<@$p>'


# import bylines from runsheet pls don't type them out manually
editors = {
    'KYLIE JUE': 'EDITOR IN CHIEF',
    'WILL FERRER': 'EXECUTIVE EDITOR',
    # news
    'VICTOR XU': 'MANAGING EDITOR',
    'ADA THROCKMORTON': 'MANAGING EDITOR',
    'ADA STATLER-THROCKMORTON': 'MANAGING EDITOR',
    'ALEX ZIVKOVIC': 'SENIOR STAFF WRITER',
    'HANNAH KNOWLES': 'DESK EDITOR',
    'REGAN PECJAK': 'DEPUTY DESK EDITOR',
    'SANDRA ORTELLADO': 'STAFF WRITER',
    'JACK HERRERA': 'STAFF WRITER',
    'KATLYN ALAPATI': 'STAFF WRITER',
    'REBECCA AYDIN': 'STAFF WRITER',
    'CALEB SMITH': 'DESK EDITOR',
    'SUSANNAH MEYER': 'DESK EDITOR',
    'ARIELLE RODRIGUEZ': 'DEPUTY DESK EDITOR',
    'CAROLINE KIMMEL': 'CONTRIBUTING WRITER',
    'NAMITA NABAR': 'CONTRIBUTING WRITER',
    'IRENE HSU': '',
    'FANGZHOU LIU': 'DESK EDITOR',
    'ANDREA VILLA': 'DEPUTY DESK EDITOR',
    'GILLIAN BRASSIL': 'CONTRIBUTING WRITER',
    'ARIEL LIU': 'DESK EDITOR',
    'ANNE-MARIE HWANG': 'DEPUTY DESK EDITOR',
    'ERIN PERRINE': 'CONTRIBUTING WRITER',
    'CHRISTINA PAN': 'STAFF WRITER',
    'ZACHARY BROWN': 'CONTRIBUTING WRITER',
    'MAX PIENKNY': 'STAFF WRITER',
    'AULDEN FOLTZ': 'CONTRIBUTING WRITER',
    'AUGUSTINE CHEMPARATHY': 'STAFF WRITER',
    'ISABELA BUMANLAG': 'CONTRIBUTING WRITER',
    'MIGUEL SAMANO': 'DEPUTY DESK EDITOR',
    'JEREMY QUACH': 'MANAGING EDITOR',
    'ALEX BOURDILLON': 'MANAGING EDITOR',
    # sports
    'OLIVIA HUMMER': 'MANAGING EDITOR',
    'TRISTAN VANECH': 'MANAGING EDITOR',
    'AMANDA MCLEAN': 'DESK EDITOR',
    'LORENZO ROSAS': 'DESK EDITOR',
    'LAURA SUSSMAN': 'DESK EDITOR',
    'MATTHEW BERNSTEIN': 'DESK EDITOR',
    'KIT RAMGOPAL': 'DESK EDITOR',
    'MICHAEL PETERSON': 'STAFF WRITER',
    'ALEXA PHILIPPOU': 'SENIOR STAFF WRITER',
    'LAUREN WEGNER': 'CONTRIBUTING WRITER',
    'ANDREW MATHER': 'SENIOR STAFF WRITER',
    'VIHAN LAKSHMAN': 'SENIOR STAFF WRITER',
    'LAURA STICKELLS': 'SENIOR STAFF WRITER',
    'DIVINE EDEM': 'CONTRIBUTING WRITER',
    'DO-HYOUNG PARK': 'SENIOR STAFF WRITER',
    'YOUSEF HINDY': 'STAFF WRITER',
    'SYDNEY SHAW': 'STAFF WRITER',
    'SANDIP SRINIVAS': 'SENIOR STAFF WRITER',
    'NEEL RAMACHANDRAN': 'SENIOR STAFF WRITER',
    'ANDREW VOGELEY': 'SENIOR STAFF WRITER',
    'ALEXA CORSE': 'STAFF WRITER',
    # arts
    'CARLOS VALLADARES': 'MANAGING EDITOR',
    'REED CANAAN': 'MANAGING EDITOR',
    'ABIGAIL FLOWERS ': 'THEATER DESK EDITOR',
    'ERIC HUANG': 'VISUAL ARTS DESK EDITOR',
    'TYLER DUNSTON': 'MUSIC DESK EDITOR',
    'RAYMOND MASPONS': 'FILM DESK EDITOR',
    # ops
    'MICHAEL GIOIA': 'MANAGING EDITOR',
    'ELIZABETH TRINH': 'DESK EDITOR',
    'JIMMY STEPHENS': 'DESK EDITOR',
    # grind
    'SAMANTHA WONG': 'MANAGING EDITOR',
    'MICHAELA ELIAS': 'EDITOR AT LARGE',
    'VIVIAN LAM': 'STAFF WRITER',
    'ARIANNA LOMBARD': 'STAFF WRITER',
    'DABIYYAH AGBERE': 'STAFF WRITER',
    # photo
    'MCKENZIE LYNCH': 'MANAGING EDITOR',
    'UDIT GOYAL': 'MANAGING EDITOR',
    'ERICA EVANS': 'MANAGING EDITOR',
    'SANTOSH MURUGAN': 'DESK EDITOR',
    'NINA ZUBRILINA': 'DESK EDITOR',
    'RYAN JAE': 'DESK EDITOR',
    # copy
    'STEPHANIE CHEN': 'MANAGING EDITOR',
    'LARK TRUMBLY': 'DESK EDITOR',
    'CLAIRE FRANCIS': 'DESK EDITOR',
    'SIMAR MALHOTRA': 'DESK EDITOR',
    'BOBBI LEET': 'DESK EDITOR',
    'ERIN PERRINE': 'DESK EDITOR',
    # mag
    'JOSH FAGEL': 'CONTRIBUTING WRITER',
    'SAM WEYEN': 'CONTRIBUTING WRITER',
}

directory = sys.argv[1]

for dirpath, subdirs, files in os.walk(directory):
    for filename in files:
        if filename.split('.')[-1] != 'rtf': continue
        
        # get author and article (file) names
        if filename.find(' ') > 0:
            author = filename[filename.find(' ')+1 : filename.find('.')]
            article = filename.split()[0]
        else:
            author = ''
            article = filename.split('.')[0]
        
        # convert .rtf to .txt with UTF-8 encoding
        rtf_filepath = os.path.join(dirpath, article + '.rtf')
        txt_filepath = os.path.join(dirpath, article + '.txt')
        subprocess.call(['mv', os.path.join(dirpath, filename), rtf_filepath]) # remove author from filename
        subprocess.call(['textutil', '-convert', 'txt', rtf_filepath])

        # convert UTF-8 to ASCII
        utf_file = codecs.open(txt_filepath, encoding='utf-8')
        plaintxt = unidecode(utf_file.read())
        utf_file.close()

        # tag and format
        for pattern in regex_tags.keys():
            plaintxt = re.sub(re.compile(pattern), regex_tags[pattern], plaintxt)

        for htmltags in tags.keys():
            if tags[htmltags] == '\n\t': plaintxt = '\t' + plaintxt
            for html in htmltags: 
                plaintxt = plaintxt.replace(html, tags[htmltags])

        # add header
        section = filename[0:3]
        if section in headers:
            plaintxt = headers[section] + plaintxt
            if author != '':
                author = author.upper()
                plaintxt = plaintxt.replace('@byline:By AUTHOR', '@byline:By ' + author)
                plaintxt = plaintxt.replace('@A&Lbyline:By AUTHOR', '@A&Lbyline:By ' + author)
                plaintxt = plaintxt.replace('@GRIbyline:By AUTHOR', '@GRIbyline:By ' + author)
                plaintxt = plaintxt.replace('@HUMbyline:By AUTHOR', '@HUMbyline:By ' + author)
                plaintxt = plaintxt.replace('Author: Name', 'Author: ' + author.title())
                position = editors[author] if author in editors else '' # change, this used to be STAFF WRITER but now we have unbylined writers
                plaintxt = plaintxt.replace('@bysub:POSITION', '@bysub:' + position)
                plaintxt = plaintxt.replace('@A&Lbysub:POSITION', '@A&Lbysub:' + position)
                plaintxt = plaintxt.replace('@GRIbysub:POSITION', '@GRIbysub:' + position)
                plaintxt = plaintxt.replace('@HUMbysub:POSITION', '@HUMbysub:' + position)

        # add footer
        plaintxt = plaintxt.rstrip()
        paragraphs = plaintxt.split('\n')
        last = paragraphs[-1]
        ats = [' \'at\' ', ' \"at\" ', '@']
        for at in ats:
            if last.find(at) > 0: 
                last = last.replace(at, '@')
                last = re.sub(re.compile(r'\t\<@CEIt>(.*)\<@\$p>'), r'\1', last) # unitalicize paragraph
                last = last.strip()
                if last[-1] != '.': # adds period at end of contact line
                    last += '.'
                if '@NEWSBRIEFS' in plaintxt or '@SpoBrief' in plaintxt:
                    cline = '\n@ATTRIB:<\p><\_><\p>'
                    caps = re.findall(r'(([A-Z][a-z]*)+)', last)
                    name = ' '.join(tup[0] for tup in caps if tup[1] != 'Contact')
                    last = cline + name
                else:
                    cline = '\n@@line:'
                    last = cline + last
                break
        paragraphs[-1] = last
        plaintxt = '\n'.join(paragraphs)

        # add <d*(0)>
        dropcap = re.search(r'<.*\*d.*>', plaintxt)
        if dropcap:
            plaintxt = re.sub(r'\t', r'', plaintxt, 1) # removes first tab that appears after dropcap
            plaintxt = re.sub(r'\t', r'<*d(0)>\t', plaintxt, 1)

        # first letter
        # now handles "I" sentences, keeps quotes in drop caps
        if 'FIRST LETTER' in plaintxt:
            plaintxt = re.sub(r'FIRST LETTER(<[@$pz<>t\-6]*>)("?\w{1})( ?\w{1})', r'\2\1\3', plaintxt)

        # if quotation mark, first *2* chars need to be dropped -- finds this and replaces
        plaintxt = re.sub(r'\*d\(1\,(\d)\)>([<>az$9]*)?"', r'*d(2,\1)>\2"', plaintxt)

        # fix double <\p>
        plaintxt = re.sub(r'<\\p><\\p>', r'<\\p>', plaintxt)

        # remove empty tags
        plaintxt = re.sub(r'<@\w+>\s+<@\$p>', r'', plaintxt)


        # police blotter (lol)
        if section == 'POL':
            plaintxt = re.sub(r'</?ul>', r'', plaintxt)
            plaintxt = re.sub(r'</li>', r'', plaintxt)
            plaintxt = re.sub(r'<@\$p>\n', r'', plaintxt)
            plaintxt = re.sub(r'<@CEBold>', r'@COPSdate: ', plaintxt)
            plaintxt = re.sub(r'\n\t?\n\t?\n', r'\n\n', plaintxt)
            plaintxt = re.sub(r'\t \t<li>', r'@normalcopy:<@COPSbullet><a$$>n<@$p> <\\i>  ', plaintxt)
        else:
            plaintxt = re.sub(r'</?ul>', r'', plaintxt)
            plaintxt = re.sub(r'</li>', r'', plaintxt)
            plaintxt = re.sub(r'[\t ]*<li>', r'@Bullet indent:<@Bullet>l<@\$p><\\i> ', plaintxt)






        # write to .txt file
        outfile = open(txt_filepath, 'w')
        outfile.write(plaintxt)
        outfile.close()
        subprocess.call(['rm', rtf_filepath]) # deletes original .rtf file











