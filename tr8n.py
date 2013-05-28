#--
# Copyright (c) 2013 Michael Berkovich, tr8nhub.com
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#++

import sublime
import sublime_plugin
import os
import re
import urllib
import urllib2
import threading
import json
from os.path import basename

##################################################################################################################################
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
    if self._description == None or len(self._description) == 0:
      return [self._label, 'No description', 'Rank: %d' % self.rank()]
    return [self._label, self._description]


##################################################################################################################################
#
# Application Class
#
class Application:
  _name = ""
  _description = ""
  _key = ""
  def __init__(self, name, description, key):
    self._name = name
    self._description = description
    self._key = key
  def name(self):
    return self._name
  def description(self):
    return self._description
  def key(self):
    return self._key
  def option(self):
    if self._description == None or len(self._description) == 0:
      return [self._name, 'No description']
    return [self._name, self._description]


##################################################################################################################################
#
# Translation Method Class
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
    line_region = self.view.line(self.sel)
    line_text = self.view.substr(line_region)
    tr_start_regx = r"tr\([\"']"
    tr_end_regx = r"[\"'][,\)]"

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

    print self.end_match

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
    print label
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

##################################################################################################################################
#
# Tr8n Lookup Command
#
class Tr8nLookupApiCall(threading.Thread):
  def __init__(self, caller, host, text):
    self.caller = caller
    self.host = host
    self.text = text
    self.timeout = 5
    threading.Thread.__init__(self)

  def run(self):
    try:
        request_url = 'http://' + self.host + '/tr8n/api/v1/translation_key/lookup?' + urllib.urlencode({'query': self.text})
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

class Tr8nLookupCommand(sublime_plugin.TextCommand):
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
        sublime.error_message("Please select some text or be inside a tr function call.")
        return 
      self.selected_text = self.tr_method.label()

    sublime.status_message('Tr8n: Looking up translation key...')
    settings = sublime.load_settings('tr8n.sublime-settings')
    thread = Tr8nLookupApiCall(self, settings.get('host'), self.selected_text)
    thread.start()    

  def add_key(self, tkey):
    self.results.append(tkey)

  def show_results(self):
    options = []

    if len(self.results) == 0:
      sublime.status_message("Tr8n: No translation keys have been found")
      return

    for tkey in self.results:
      options.append(tkey.option())

    sublime.status_message("Tr8n: Found %d translation keys" % len(options))
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

##################################################################################################################################
# Tr8n Register Command
#
class Tr8nRegisterApiCall(threading.Thread):
  def __init__(self, caller, host, access_token, app_key, label, description):
    self.caller = caller
    self.host = host
    self.access_token = access_token
    self.app_key = app_key
    self.label = label
    self.description = description
    self.timeout = 5
    threading.Thread.__init__(self)

  def run(self):
    try:
      query = urllib.urlencode({'access_token': self.access_token, 'app_key': self.app_key, 'label': self.label, 'description': self.description})
      request = urllib2.Request('http://' + self.host + '/tr8n/api/v1/translation_key/register', query, headers={"User-Agent": "Sublime Tr8n"})
      http_file = urllib2.urlopen(request, timeout=self.timeout)
      data = json.loads(http_file.read())
      print data
      if 'error' in data:
        sublime.error_message(data['error'])
        return 
      
      sublime.set_timeout(self.caller.show_results, 0)
      return

    except (urllib2.HTTPError) as (e):
        err = '%s: HTTP error %s contacting API' % (__name__, str(e.code))
    except (urllib2.URLError) as (e):
        err = '%s: URL error %s contacting API' % (__name__, str(e.reason))

    sublime.error_message(err)


class Tr8nRegisterCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    self.edit = edit
    self.settings = sublime.load_settings('tr8n.sublime-settings')

    access_token = self.settings.get('access_token') 
    if access_token == None: 
      self.view.run_command("tr8n_login")
      return
    app_key = self.settings.get('app_key') 
    if app_key == None: 
      self.view.run_command("tr8n_app")
      return

    self.tr_method = None
    selection_region = self.view.sel()[0]
    self.label = self.view.substr(selection_region)
    self.description = ''

    # if there is no text selected, try to guess the begining of the translatable text
    if len(self.label) == 0:
      self.tr_method = TranslationMethod(self.view, selection_region)
      if not self.tr_method.is_valid():
        sublime.error_message("Please select some text or be inside a tr function call.")
        return 
      self.label = self.tr_method.label()
      self.description = self.tr_method.description()
    
    self.view.window().show_input_panel("Label:", self.label, self.on_label_entered, None, None)

  def on_label_entered(self, arg):
    if arg != -1:
      self.label = arg
      self.view.window().show_input_panel("Description:", self.description, self.on_description_entered, None, None)

  def on_description_entered(self, arg):
    if arg != -1:
      self.description = arg
      sublime.status_message('Tr8n: Registering translation key...')
      settings = sublime.load_settings('tr8n.sublime-settings')
      thread = Tr8nRegisterApiCall(self, settings.get('host'), settings.get('access_token'), settings.get('app_key'), self.label, self.description)
      thread.start()    

  def on_done(self, arg):
    if arg != -1:
      sublime.status_message('Tr8n: Translation key has been registered')
    else:
        pass    

##################################################################################################################################
#
# Tr8n App Command
#
class Tr8nAppApiCall(threading.Thread):
  def __init__(self, caller, host, access_token):
    self.caller = caller
    self.host = host
    self.access_token = access_token
    self.timeout = 5
    threading.Thread.__init__(self)

  def run(self):
    try:
      request_url = 'http://' + self.host + '/tr8n/api/v1/translator/applications?' + urllib.urlencode({'access_token': self.access_token})
      request = urllib2.Request(request_url)
      http_file = urllib2.urlopen(request, timeout=self.timeout)
      data = json.loads(http_file.read())
      if 'error' in data:
        sublime.error_message(data['error'])
        return 

      for app in data['results']:
        self.caller.add_app(Application(app['name'], app['description'], app['key']))

      sublime.set_timeout(self.caller.show_results, 0)
      return

    except (urllib2.HTTPError) as (e):
      err = '%s: HTTP error %s contacting API' % (__name__, str(e.code))
    except (urllib2.URLError) as (e):
      err = '%s: URL error %s contacting API' % (__name__, str(e.reason))
    sublime.error_message(err)

class Tr8nAppCommand(sublime_plugin.TextCommand):
  results = []

  def run(self, edit):
    self.results = []
    self.settings = sublime.load_settings('tr8n.sublime-settings')
    access_token = self.settings.get('access_token') 
    if access_token == None: 
      self.view.run_command("tr8n_login")
      return

    settings = sublime.load_settings('tr8n.sublime-settings')
    thread = Tr8nAppApiCall(self, settings.get('host'), access_token)
    thread.start()    

  def add_app(self, app):
    self.results.append(app)

  def show_results(self):
    options = []

    if len(self.results) == 0:
      sublime.status_message("Tr8n: No applications have been found")
      return

    for app in self.results:
      options.append(app.option())

    sublime.status_message("Tr8n: Found %d application(s)" % len(options))
    self.view.window().show_quick_panel(options, self.on_done)

  def on_done(self, arg):
    if arg != -1:
      app = self.results[arg]
      self.settings.set('app_key', app.key())
      sublime.status_message('Tr8n: You have selected %s application' % app.name())
    else:
        pass    

##################################################################################################################################
#
# Tr8n Host Command
#
class Tr8nHostCommand(sublime_plugin.TextCommand):

  def run(self, edit):
    self.settings = sublime.load_settings('tr8n.sublime-settings')
    self.view.window().show_input_panel("What is the domain name where the tr8n service is running?", self.settings.get('host'), self.on_done, None, None)

  def on_done(self, arg):
    if arg != -1:
      self.settings.set('host', arg)
      sublime.status_message('Tr8n: Settings have been updated')
    else:
        pass    


##################################################################################################################################
#
# Tr8n Login Command
#
class Tr8nLoginApiCall(threading.Thread):
  def __init__(self, caller, host, email, password):
    self.caller = caller
    self.host = host
    self.email = email
    self.password = password
    self.timeout = 5
    threading.Thread.__init__(self)

  def run(self):
    try:
      query = urllib.urlencode({'email': self.email, 'password': self.password})
      request = urllib2.Request('http://' + self.host + '/tr8n/api/v1/translator/authorize', query, headers={"User-Agent": "Sublime Tr8n"})
      http_file = urllib2.urlopen(request, timeout=self.timeout)
      data = json.loads(http_file.read())

      if 'error' in data:
        sublime.error_message(data['error'])
        return 
      
      self.caller.set_access_token(data['access_token'])
      sublime.set_timeout(self.caller.on_authorized, 0)
      return

    except (urllib2.HTTPError) as (e):
      err = '%s: HTTP error %s contacting API' % (__name__, str(e.code))
    except (urllib2.URLError) as (e):
      err = '%s: URL error %s contacting API' % (__name__, str(e.reason))
    sublime.error_message(err)

class Tr8nLoginCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    self.settings = sublime.load_settings('tr8n.sublime-settings')
    email = self.settings.get('email') 
    if email == None: 
      email = ''
    self.view.window().show_input_panel("What is your tr8n email?", email, self.on_email_entered, None, None)

  def on_email_entered(self, arg):
    if arg != -1:
      self.settings.set('email', arg)
      self.view.window().show_input_panel("What is your tr8n password?", "", self.on_password_entered, None, None)

  def on_password_entered(self, arg):
    if arg != -1:
      thread = Tr8nLoginApiCall(self, self.settings.get('host'), self.settings.get('email'), arg)
      thread.start()    

  def set_access_token(self, token):
    self.access_token = token

  def on_authorized(self):
    self.settings.set('access_token', self.access_token)
    sublime.status_message('Tr8n: You have been logged in')
    self.view.run_command("tr8n_app")


##################################################################################################################################
#
# Tr8n Logout Command
#
class Tr8nLogoutCommand(sublime_plugin.TextCommand):

  def run(self, edit):
    settings = sublime.load_settings('tr8n.sublime-settings')
    settings.set('access_token', None)
    sublime.status_message('Tr8n: You have been logged out')

##################################################################################################################################
#
# Tr8n Help Command
#
class Tr8nHelpCommand(sublime_plugin.TextCommand):

  def run(self, edit):
    options = [
      ["Tr8n: Help", "[cmd+ctrl+t, cmd+ctrl+t]"], 
      ["Tr8n: Change service host", "[cmd+ctrl+t, cmd+ctrl+h]"], 
      ["Tr8n: Lookup translation key", "[cmd+ctrl+t, cmd+ctrl+l]"], 
      ["Tr8n: Login to translation service", "[cmd+ctrl+t, cmd+ctrl+i]"], 
      ["Tr8n: Select application", "[cmd+ctrl+t, cmd+ctrl+a]"], 
      ["Tr8n: Register translation key", "[cmd+ctrl+t, cmd+ctrl+r]"], 
      ["Tr8n: Logout", "[cmd+ctrl+t, cmd+ctrl+o]"]
    ] 
    self.view.window().show_quick_panel(options, self.on_done)

  def on_done(self, arg):
    if arg != -1:
      if arg == 1:
        self.view.run_command("tr8n_host")
      elif arg == 2:
        self.view.run_command("tr8n_lookup")
      elif arg == 3:
        self.view.run_command("tr8n_login")
      elif arg == 4:
        self.view.run_command("tr8n_app")
      elif arg == 5:
        self.view.run_command("tr8n_register")
      elif arg == 6:
        self.view.run_command("tr8n_logout")
    else:        
      pass