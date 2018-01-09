__author__ = 'yottatsa'

import codecs
import datetime
import os
import sys
import urlparse
import xml.dom.minidom
import html5lib
import lxml.etree

import utils


class Sitemap(object):
    def __init__(self):
        robots = open('robots.txt', 'r').read().split()
        self.sitemap = urlparse.urlparse(robots[robots.index('Sitemap:') + 1])
        self.sitemap_file = open(self.sitemap.path.lstrip('/'), 'w')

    def generate(self, url):
        return self.sitemap._replace(path=os.path.join('/', url)).geturl()

    def add(self, url):
        url = self.generate(url)
        url = url.replace('index.html', '')
        self.sitemap_file.write(url + '\n')
        return url


class HTML(object):
    def __init__(self, html, url, sitemap):
        self.tree = html5lib.parse(html, treebuilder="dom")
        self.tree.encoding = 'utf-8'
        self.head = self.tree.getElementsByTagName('head')[0]
        self.body = self.tree.getElementsByTagName('body')[0]
        self.outfile = url
        self.url = sitemap.add(url)

    def append_head(self, dom):
        self.head.appendChild(dom)

    def append_foot(self, dom):
        self.body.appendChild(dom)

    def do(self):
        with open(self.outfile, "w") as out:
            content = self.tree.toxml("utf-8")
            content = content.replace('<?xml version="1.0" encoding="utf-8"?>', '')
            out.write(content)


class Page(HTML):
    _renderers = {}
    CSS = [
        "../style.css"
    ]
    DOCTYPE = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'''

    def __init__(self, filename, sitemap):
        self.filename = filename
        fn, ext = filename.rsplit('.', 1)
        url = '{}.html'.format(fn)

        content = open(filename).read().decode('utf-8')
	content = utils.strip_pgp(content)
        render = Page._renderers.get(ext.lower())
        html = render(content)

        super(Page, self).__init__(Page.DOCTYPE + html, url, sitemap)

        html = self.tree.getElementsByTagName('html')[0]
        html.setAttribute("xmlns", "http://www.w3.org/1999/xhtml")

        for css in Page.CSS:
            stylesheet = self.tree.createElement('link')
            stylesheet.setAttribute("rel", "stylesheet")
            stylesheet.setAttribute("href", css)
            self.append_head(stylesheet)

        body = self.tree.getElementsByTagName('body')[0]
        body.setAttribute('class', 'container hentry')

        titles = self.tree.getElementsByTagName('h1')
        if titles:
            title = titles[0]
            self.title = title.childNodes[0].wholeText

            title_elm = self.tree.createElement('title')
            title_elm.appendChild(self.tree.createTextNode(self.title))
            self.append_head(title_elm)

            title.parentNode.insertBefore(self.modified, title)
            title.parentNode.replaceChild(self.heading('h1'), title)

        p = self.tree.getElementsByTagName('p')
        if p:
            for c in p:
                if c.childNodes:
                    self.p = c
                    self.p.setAttribute("class", "entry-summary")
                    break
            else:
                self.p = None

    def heading(self, name):
        heading = self.tree.createElement(name)
        link = self.tree.createElement('a')
        link.appendChild(self.tree.createTextNode(self.title))
        link.setAttribute('href', self.url)
        link.setAttribute('class', 'entry-title')
        link.setAttribute('rel', 'bookmark')
        heading.appendChild(link)
        return heading

    @property
    def abstract(self):
        if self.p:
            return self.p.cloneNode(True)

    @property
    def file_modified(self):
        return datetime.datetime.fromtimestamp(os.stat(self.filename).st_mtime)

    @property
    def modified(self):
        timestamp = self.file_modified
        modified = self.tree.createElement('abbr')
        modified.setAttribute('class', 'published updated')
        modified.setAttribute('title', timestamp
                              .strftime('%Y-%m-%d %H:%M:%S'))
        modified.appendChild(
            self.tree.createTextNode(
                "published on " + \
                timestamp.strftime('%d %h %Y')))
        return modified

    @classmethod
    def register(cls, exts, default=False):
        def deco(func):
            for ext in exts:
                cls._renderers[ext.lower()] = func

        return deco


@Page.register(['mkd', 'md', 'txt'])
def mkd(content):
    import markdown
    return u'<div class="document">{}</div>'.format(markdown.markdown(content))


@Page.register(['rst'])
def rst(content):
    import docutils.core
    return docutils.core.publish_string(content, writer_name='html')


class Home(HTML):
    def __init__(self, filename, sitemap):
        content = open(filename, 'r+').read().decode('utf-8')
        content = content.replace('<?xml version="1.0" encoding="utf-8"?>', '')
        super(Home, self).__init__(content, filename, sitemap)
        self.etree = lxml.etree.HTML(content)

        for article in self.tree.getElementsByTagName("article"):
            self.body.removeChild(article)
            article.unlink()

    def append_paper(self, page):
        item = self.tree.createElement('article')
        item.setAttribute('class', 'hentry')
        self.body.appendChild(item)

        item.appendChild(page.heading('h2'))

        abstract = page.abstract.cloneNode(True)
        abstract.appendChild(self.tree.createTextNode(' '))
        abstract.setAttribute('class', 'entry-summary')
        abstract.appendChild(page.modified)

        address = self.tree.createElement('address')
        address.setAttribute('class', 'vcard author')
        address.appendChild(self.author)
        item.appendChild(abstract)
        item.appendChild(address)

    @property
    def headers(self):
        yield self.head.getElementsByTagName('script')[0].cloneNode(True)

        for elm in self.head.getElementsByTagName('meta'):
            yield elm.cloneNode(True)

    @property
    def hcard(self):
        address = self.tree.getElementsByTagName('address')
        if address:
            ret = address[0].cloneNode(True)
            img = ret.getElementsByTagName('img')
            if img:
                ret.removeChild(img[0])
                img[0].unlink()
            return ret

    @property
    def author(self):
        regexpNS = "http://exslt.org/regular-expressions"
        find = lxml.etree.XPath("//*[re:test(@class, 'vcard', 'i')]"
                                "//*[re:test(@class, 'fn', 'i')]",
                                namespaces={'re': regexpNS})
        fn = find(self.etree)
        if fn:
            root = xml.dom.minidom.parseString(lxml.etree.tostring(fn[0]))
            return root.childNodes[0]


def render(homefile, pages):
    sitemap = Sitemap()
    home = Home(homefile, sitemap)
    for filename in pages:
        page = Page(filename, sitemap)
        home.append_paper(page)
        for elm in home.headers:
            page.append_head(elm)
        address = page.tree.getElementsByTagName('address')
        if address:
            t = address[0]
            t.parentNode.replaceChild(home.hcard, t)
        else:
            page.append_foot(home.hcard)
        page.do()
        print page.title, page.url
    home.do()


if __name__ == '__main__':
    if len(sys.argv) > 2:
        render(sys.argv[1], sys.argv[2:])