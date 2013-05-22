import sublime
import sublime_plugin
import os
import re
import urllib
import urllib2
import threading
import json
from os.path import basename

#
# TranslationKey Class
#
class TranslationKey:
  _label = ""
  _description = ""
  _rank = 0
  def __init__(self, label, description, rank):
    self._label = label
    self._description = description
    self._rank = rank
  def label(self):
    return self._label
  def description(self):
    return self._description
  def rank(self):
    return self._rank
  def option(self):
    if self._description == None:
      return self._label
    return [self._label, self._description]


#
# Translation Method
#
class TranslationMethod:
  view = None
  sel = None
  start_match = None
  end_match = None

  def __init__(self, view, sel):
    self.view = view
    self.sel = sel
    self.parse()

  def parse(self):
    # print self.view.line(self.sel)
    # print self.view.full_line(self.sel)
    line_region = self.view.line(self.sel)
    line_text = self.view.substr(line_region)
    # print line_text

    tr_start_regx = r"tr\([\"']"
    tr_end_regx = r"[\"']\)"

    current_match = self.view.find(tr_start_regx, line_region.a)
    # if there is no tr method call on the line at all, then just use the entire line
    if current_match == None:
      return
    
    next_match = self.view.find(tr_start_regx, current_match.b+1)
    while next_match and next_match.a < self.sel.a:
      current_match = next_match
      next_match = self.view.find(tr_start_regx, current_match.b+1)

    self.start_match = current_match  
    self.end_match = self.view.find(tr_end_regx, current_match.b+1)
    if self.end_match:
      end_line_region = self.view.line(self.end_match)
      if line_region.a != end_line_region.a:
        self.end_match = None


  def is_valid(self):
    if self.start_match == None:
      return False
    if self.start_match.a > self.sel.a:
      return False
    return True  

  def text_region(self):
    if self.end_match == None:
      return sublime.Region(self.start_match.b, self.sel.b)

    return sublime.Region(self.start_match.b, self.end_match.a)

  def text(self):
    return self.view.substr(self.text_region())

  def label(self):
    label = self.text()
    bracket = label.find('"')
    if bracket != -1:
      label = label[:bracket]
    return label

  def replace(self, edit, tkey):
    if tkey.description() == None or len(tkey.description()) == 0:
      replacement = tkey.label()
    else:
      replacement = tkey.label() + "\",\"" + tkey.description()

    self.view.replace(edit, self.text_region(), replacement)

#
# Tr8n Api Call Class
#
class Tr8nApiCall(threading.Thread):
  def __init__(self, caller, text):
    self.caller = caller
    self.text = text
    self.timeout = 5
    threading.Thread.__init__(self)

  def run(self):
    try:
        query = urllib.urlencode({'query': self.text})
        # request = urllib2.Request('http://translate-sandbox.geni.com/tr8n/api/v1/translation_key/lookup', query,
        #     headers={"User-Agent": "Sublime Tr8n"})
        request_url = 'http://translate-sandbox.geni.com/tr8n/api/v1/translation_key/lookup?%s' % query
        print request_url
        request = urllib2.Request(request_url)
        http_file = urllib2.urlopen(request, timeout=self.timeout)
        data = json.loads(http_file.read())
        # print data
        if 'error' in data:
          sublime.error_message(data['error'])
          return 
        
        for jkey in data['results']:
          self.caller.add_key(TranslationKey(jkey['label'], jkey['description'], len(jkey['translations'])))

        sublime.set_timeout(self.caller.show_results, 0)
        return

    except (urllib2.HTTPError) as (e):
        err = '%s: HTTP error %s contacting API' % (__name__, str(e.code))
    except (urllib2.URLError) as (e):
        err = '%s: URL error %s contacting API' % (__name__, str(e.reason))

    sublime.error_message(err)


#
# Tr8n Command Class
#
class Tr8nCommand(sublime_plugin.TextCommand):

  results = []

  def run(self, edit):
    self.results = []
    self.edit = edit
    self.selection_region = self.view.sel()[0]
    self.tr_method = None

    self.selected_text = self.view.substr(self.selection_region)

    # if there is no text selected, try to guess the begining of the translatable text
    if len(self.selected_text) == 0:
      self.tr_method = TranslationMethod(self.view, self.selection_region)
      if not self.tr_method.is_valid():
        sublime.error_message("Please select some text or be within a tr function call.")
        return 
      self.selected_text = self.tr_method.label()

    print self.selected_text
    thread = Tr8nApiCall(self, self.selected_text)
    thread.start()    

  def add_key(self, tkey):
    self.results.append(tkey)

  def show_results(self):
    options = []

    if len(self.results) == 0:
      sublime.status_message("No translation keys have been found")
      return

    for tkey in self.results:
      options.append(tkey.option())

    sublime.status_message("Found %d translation keys" % len(options))
    self.view.window().show_quick_panel(options, self.on_done)

  def on_done(self, arg):
    if arg != -1:
      tkey = self.results[arg]
      if self.tr_method:
        self.tr_method.replace(self.edit, tkey)
      else:
        self.view.replace(self.edit, self.selection_region, tkey.label())
    else:
        pass    


