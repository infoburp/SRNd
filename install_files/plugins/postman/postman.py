#!/usr/bin/python

import time
import random
import string
import urllib
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from urllib import unquote
from cgi import FieldStorage
import base64
from hashlib import sha1
from datetime import datetime
import os
import threading
import sqlite3
import socket
if __name__ == '__main__':
  import nntplib

class postman(BaseHTTPRequestHandler):

  def __init__(self, request, client_address, origin):
    self.origin = origin
    #if __name__ != '__main__':
    #  self.origin.log('postman initializing as plugin..', 2)
    #else:
    #  self.origin.log('postman initializing as standalone application..', 2)
    # ^ works
    BaseHTTPRequestHandler.__init__(self, request, client_address, origin)

  def do_POST(self):
    self.path = unquote(self.path)
    if self.path == '/incoming':
      self.handleNewArticle()
    else:
      self.origin.log("illegal access: {0}".format(self.path), 2)
      self.send_response(200)
      self.send_header('Content-type', 'text/plain')
      self.end_headers()
      self.wfile.write('nope')

  def do_GET(self):
    self.path = unquote(self.path)
    self.origin.log("illegal access: {0}".format(self.path), 2)
    self.send_response(200)
    self.send_header('Content-type', 'text/plain')
    self.end_headers()
    self.wfile.write('nope')

  def send_error(self, errormessage):
    self.send_response(200)
    self.send_header('Content-type', 'text/plain')
    self.end_headers()
    self.wfile.write(errormessage)

  def die(self, message=''):
    self.origin.log("{0}:{1} wants to fuck around: {2}".format(self.client_address[0], self.client_address[1], message), 1)
    if self.origin.reject_debug:
      self.send_error('don\'t fuck around here mkay\n{0}'.format(message))
    else:
      self.send_error('don\'t fuck around here mkay')

  def log_request(self, code):
    return

  def log_message(self, format):
    return

  def handleNewArticle(self):
    post_vars = FieldStorage(
      fp=self.rfile,
      headers=self.headers,
      environ={
        'REQUEST_METHOD':'POST',
        'CONTENT_TYPE':self.headers['Content-Type'],
      }
    )
    if not 'frontend' in post_vars:
      self.die('frontend not in post_vars')
      return
    frontend = post_vars['frontend'].value
    self.origin.log("got incoming article from {0}:{1} for frontend '{2}'".format(self.client_address[0], self.client_address[1], frontend), 2)
    if not 'target' in post_vars:
      self.die('target not in post_vars')
      return
    if not frontend in self.origin.frontends:
      self.die('{0} not in configured frontends'.format(frontend))
      return
    for key in self.origin.frontends[frontend]['required_fields']:
      if not key in post_vars:
        self.die('{0} required but missing'.format(key))
        return
    comment = post_vars['comment'].value
    if comment == '':
      self.send_error('no message received. nothing to say?')
      return
    if 'enforce_board' in self.origin.frontends[frontend]:
      group = self.origin.frontends[frontend]['enforce_board']
    else:
      group = post_vars['board'].value
      if group == '':
        self.die('board is empty')
        return
      found = False
      for board in self.origin.frontends[frontend]['allowed_boards']:
        if (board[-1] == '*' and group.startswith(board[:-1])) or group == board:
          found = True
          break
      if not found:
        self.die('{0} not in allowed_boards'.format(group))
        return
    redirect_duration = 2
    if not 'allowed_files' in self.origin.frontends[frontend]:
      file_name = ''
    else:
      file_name = post_vars['file'].filename
      if file_name != '':
        content_type = post_vars['file'].type
        for mime in self.origin.frontends[frontend]['allowed_files']:
          if not ((mime[-1] == '*' and content_type.startswith(mime[:-1])) or content_type == mime):
            self.die('{0} not in allowed_files'.format(content_type))
            return
        redirect_duration = 4
    uid_host = self.origin.frontends[frontend]['uid_host']
    # web.news.sfor.ano

    name = self.origin.frontends[frontend]['defaults']['name']
    email = self.origin.frontends[frontend]['defaults']['email']
    subject = self.origin.frontends[frontend]['defaults']['subject']

    if 'name' in post_vars:
      if post_vars['name'].value != '':
        name = post_vars['name'].value
    if 'email' in post_vars:
      #FIXME add email validation: .+@.+\..+
      if post_vars['email'].value != '':
        email = post_vars['email'].value
    if 'subject' in post_vars:
      # news: no subject
      if post_vars['subject'].value != '':
        subject = post_vars['subject'].value

    sender = '{0} <{1}>'.format(name, email)
    reply = ''
    if 'reply' in post_vars:
      reply = post_vars['reply'].value

    if reply != '':
      result = self.origin.sqlite.execute('SELECT message_id FROM article_hashes WHERE message_id_hash = ?', (reply,)).fetchone()
      if not result:
        self.die('hash {0} not found in hashes.db3'.format(reply))
        return
      else:
        reply = result[0]
    uid_rnd = ''.join(random.choice(string.ascii_lowercase) for x in range(10))
    uid_time = int(time.time())
    message_uid = '<{0}{1}@{2}>'.format(uid_rnd, uid_time, self.origin.frontends[frontend]['uid_host'])
    if 'enforce_target' in self.origin.frontends[frontend]:
      redirect_target = self.origin.frontends[frontend]['enforce_target'].replace('%%sha1_message_uid_10%%', sha1(message_uid).hexdigest()[:10])
    else:
      redirect_target = post_vars['target'].value
    boundary = ''.join(random.choice(string.ascii_letters + string.digits) for x in range(40))
    date = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
    #f = open('tmp/' + boundary, 'w')
    link = os.path.join('incoming', 'tmp', boundary)
    f = open(link, 'w')
    if file_name == '':
      f.write(self.origin.template_message_nopic.format(sender, date, group, subject, message_uid, reply, uid_host, comment))
    else:
      f.write(self.origin.template_message_pic.format(sender, date, group, subject, message_uid, reply, uid_host, boundary, comment, content_type, file_name))
      base64.encode(post_vars['file'].file, f)
      f.write('--{0}--'.format(boundary))
    f.close()
    try:
      self.send_response(200)
      self.send_header('Content-type', 'text/html')
      self.end_headers()
      self.wfile.write('<html><head><META HTTP-EQUIV="Refresh" CONTENT="{0}; URL={1}"></head><body style="font-family: arial,helvetica,sans-serif; font-size: 10pt;"><center><br />your message has been received.<br />this page will <a href="{1}">redirect</a> you in {0} seconds.</center></body></html>'.format(redirect_duration, redirect_target))
      os.rename(link, os.path.join('incoming', boundary))
    except socket.error as e:
      if e.errno == 32:
        self.origin.log(e, 2)
        # Broken pipe
        pass
      else:
        raise e

class main(threading.Thread):

  def __init__(self, thread_name, args):
    threading.Thread.__init__(self)
    self.name = thread_name
    if 'debug' not in args:
      self.debug = 2
      self.log('debuglevel not defined, using default of debug = 2', 2)
    else:
      try:
        self.debug = int(args['debug'])
        if self.debug < 0 or self.debug > 5:
          self.debug = 2
          self.log('debuglevel not between 0 and 5, using default of debug = 2', 2)
        else:
          self.log('using debuglevel {0}'.format(self.debug), 3)
      except ValueError as e:
        self.debug = 2
        self.log('debuglevel not between 0 and 5, using default of debug = 2', 2)
    if __name__ != '__main__':
      self.log('initializing as plugin..', 2)
    else:
      self.log('initializing as standalone application..', 2)
    self.should_terminate = False
    for key in ('bind_ip', 'bind_port', 'template_directory', 'frontend_directory'):
      if not key in args:
        self.log('{0} not in args'.format(key), 0)
        self.should_terminate = True
    if self.should_terminate:
      self.log('terminating..'.format(key), 0)
      return
    self.ip = args['bind_ip']
    try:
      self.port = int(args['bind_port'])
    except ValueError as e:
      self.log("{0} is not a valid bind_port", 0)
      self.should_terminate = True
      self.log('terminating..'.format(key), 0)
      return
    if 'bind_use_ipv6' in args:
      tmp = args['bind_use_ipv6']
      if tmp.lower() == 'true':
        self.ipv6 = True
      elif tmp.lower() == 'false':
        self.ipv6 = False
      else:
        self.log("{0} is not a valid value for bind_use_ipv6. only true and false allowed.", 0)
        self.should_terminate = True
        self.log('terminating..'.format(key), 0)
        return

    self.log('initializing httpserver..', 3)
    self.httpd = HTTPServer((self.ip, self.port), postman)

    if 'reject_debug' in args:
      tmp = args['reject_debug']
      if tmp.lower() == 'true':
        self.httpd.reject_debug = True
      elif tmp.lower() == 'false':
        self.httpd.reject_debug = False
      else:
        self.log("{0} is not a valid value for reject_debug. only true and false allowed. setting value to false.", 0)
    self.httpd.log = self.log

    # read templates
    self.log('reading templates..', 3)
    template_directory = args['template_directory']
    f = open(os.path.join(template_directory, 'message_nopic.template'), 'r')
    self.httpd.template_message_nopic = f.read()
    f.close()
    f = open(os.path.join(template_directory, 'message_pic.template'), 'r')
    self.httpd.template_message_pic = f.read()
    f.close()

    # read frontends
    self.log('reading frontend configuration..', 3)
    frontend_directory = args['frontend_directory']
    if not os.path.isdir(frontend_directory):
      self.log('error: {0} not a directory'.format(frontend_directory), 0)
    self.httpd.frontends = dict()
    frontends = list()
    for frontend in os.listdir(frontend_directory):
      link = os.path.join(frontend_directory, frontend)
      if not os.path.isfile(link):
        continue
      self.httpd.frontends[frontend] = dict()
      f = open(link, 'r')
      line = f.readline()
      root = ''
      this_is = 'dict'
      while line != "":
        if line[0] == '#' or line == '\n':
          line = f.readline()
          continue
        line = line[:-1]
        if line[0] == '(' and line[-1] == ')':
          root = line[1:-1]
          this_is = 'list'
          self.httpd.frontends[frontend][root] = list()
          line = f.readline()
          continue
        elif line[0] == '[' and line[-1] == ']':
          root = line[1:-1]
          self.httpd.frontends[frontend][root] = dict()
          this_is = 'dict'
          line = f.readline()
          continue
        if this_is == 'list':
          self.httpd.frontends[frontend][root].append(line)
        elif this_is == 'dict':
          if not '=' in line:
            self.log("error while parsing frontend '{0}': no = in '{1}' which was defined as dict.".format(frontend, line), 0)
            continue
          key = line.split('=', 1)[0]
          value = line.split('=', 1)[1]
          if root == '':
            self.httpd.frontends[frontend][key] = value
          else:
            self.httpd.frontends[frontend][root][key] = value
        line = f.readline()
      f.close()
      error = ''
      for key in ('uid_host', 'required_fields', 'defaults'):
        if key not in self.httpd.frontends[frontend]:
          error += '  {0} not in frontend configuration file\n'.format(key)
      if 'defaults' in self.httpd.frontends[frontend]:
        for key in ('name', 'email', 'subject'):
          if key not in self.httpd.frontends[frontend]['defaults']:
            error += '  {0} not in defaults section of frontend configuration file\n'.format(key)
      if error != '':
        del self.httpd.frontends[frontend]
        self.log("removed frontend configuration for {0}:\n{1}".format(frontend, error[:-1]), 0)
      else:
        frontends.append(frontend)

    if len(frontends) > 0:
      self.log('added {0} frontends: {1}'.format(len(frontends), ', '.join(frontends)), 2)
    else:
      self.log('no valid frontends found in {0}.'.format(frontend_directory), 0)
      self.log('terminating..'.format(frontend_directory), 0)
      self.should_terminate = True
      return

  def shutdown(self):
    self.httpd.shutdown()

  def add_article(self, message_id):
    self.log('this plugin does not handle any article. remove hook parts from {0}'.format(os.path.join('config', 'plugins', self.name.split('-', 1)[1])), 0)

  def run(self):
    if self.should_terminate:
      return
    # connect to hasher database
    # FIXME: add database_directory to postman?
    self.database_directory = ''
    self.httpd.sqlite_conn = sqlite3.connect(os.path.join(self.database_directory, 'hashes.db3'))
    self.httpd.sqlite = self.httpd.sqlite_conn.cursor()
    self.log('start listening at http://{0}:{1}'.format(self.ip, self.port), 1)
    self.httpd.serve_forever()
    self.log('bye', 2)

  def log(self, message, debuglevel):
    if self.debug >= debuglevel:
      for line in "{0}".format(message).split('\n'):
        print "[{0}] {1}".format(self.name, line)

if __name__ == '__main__':
  args = dict()
  args['bind_ip'] = "1.4.7.101"
  args['bind_port'] = "58425"
  args['bind_use_ipv6'] = "False"
  args['template_directory'] = "plugins/postman/templates"
  args['frontend_directory'] = "plugins/postman/frontends"
  poster = main("poster", args)
  poster.start()
  try:
    time.sleep(3600)
  except KeyboardInterrupt as e:
    print
    poster.shutdown()
  except Exception as e:
    print
    print "Exception:", e
    raise e
