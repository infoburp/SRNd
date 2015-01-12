#!/usr/bin/python
import os
import sqlite3
import time
import threading
from hashlib import sha1
from datetime import datetime, timedelta
from email.utils import parsedate_tz
from calendar import timegm
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import guess_lexer, guess_lexer_for_filename, get_lexer_by_name, ClassNotFound

if __name__ == '__main__':
  import signal
  import fcntl
else:
  import Queue
  from pygments.lexers import *
  from pygments.lexers._phpbuiltins import MODULES
  #from pygments.lexers._lassobuiltins import BUILTINS

class main(threading.Thread):

  def __init__(self, thread_name, args):
    threading.Thread.__init__(self)
    self.name = thread_name
    self.should_terminate = False
    self.debug = 5
    for arg in ('template_directory', 'output_directory', 'database_directory'):
      if not arg in args:
        self.log('error: {0} not in arguments'.format(arg), 0)
        self.log('terminating', 0)
        self.should_terminate = True
        if __name__ == '__main__':
          exit(1)
        else:
          return
    self.outputDirectory = args['output_directory']
    self.database_directory = args['database_directory']
    self.templateDirectory = args['template_directory']
    if not os.path.exists(self.templateDirectory):
      self.log("error: template directory '{0}' does not exist".format(self.templateDirectory), 0)
      self.log("terminating", 0)
      self.should_terminate = True
      return

    if __name__ == '__main__':
      self.log("initializing as standalone application..", 2)
      if 'watch_directory' not in args:
        self.log("error: called without watch_directory and thus should receive articles via .add_article() but this class runs as own application.", 0)
        self.log("terminating", 0)
        exit(1)
      self.watching = args['watch_directory']
      self.log("creating directory watcher..", 2)
      signal.signal(signal.SIGIO, self.handle_new)
      try:
        fd = os.open(self.watching, os.O_RDONLY)
      except OSError as e:
        if e.errno == 2:
          self.log("{0}".format(e), 0)
          exit(1)
        else:
          raise e
      fcntl.fcntl(fd, fcntl.F_SETSIG, 0)
      fcntl.fcntl(fd, fcntl.F_NOTIFY,
                  fcntl.DN_MODIFY | fcntl.DN_CREATE | fcntl.DN_MULTISHOT)
      if not os.path.exists(self.database_directory):
        os.mkdir(self.database_directory)
      self.sqlite_conn = sqlite3.connect(os.path.join(self.database_directory, 'pastes.db3'))
      self.sqlite = self.sqlite_conn.cursor()
      self.sqlite.execute('''CREATE TABLE IF NOT EXISTS pastes
                    (article_uid text, hash text PRIMARY KEY, sender text, email text, subject text, sent INTEGER, body text, root text, received INTEGER)''')
      self.sqlite_conn.commit()
    else:
      self.log("initializing as plugin..", 2)
      if 'watch_directory' in args:
        self.log("error: called with watch_directory and thus should watch a directory for changes but this class does not run as own application.", 0)
        self.log("terminating", 0)
        self.should_terminate = True
        return
      self.queue = Queue.Queue()
      # needed for working inside a chroot to recognize latin1 charset
      try:
        lexer = guess_lexer("svmmsjj".encode('latin1'), encoding='utf-8')
      except ClassNotFound as e:
        pass
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
    self.formatter = HtmlFormatter(linenos=True, cssclass="source", encoding='utf-8', anchorlinenos=True, lineanchors='line', full=False, cssfile="./styles.css", noclobber_cssfile=True)
    self.lexers = dict()
    #allowed_lexers = ('Bash', 'HTML+Lasso', 'NumPy')
    self.allowed_lexers = ('Bash', 'NumPy', 'Perl') # TODO: add php because of shebang line?
    self.recognized_extenstions = ('sh', 'py', 'pyx', 'pl', 'hs', 'haskell', 'js', 'php', 'html', 'c', 'cs')
    f = open(os.path.join(self.templateDirectory, 'single_paste.tmpl'), 'r')
    self.template_single_paste = f.read()
    f.close()
    f = open(os.path.join(self.templateDirectory, 'index.tmpl'), 'r')
    self.template_index = f.read()
    f.close()
    if __name__ == '__main__':
      self.busy = False
      self.retry = False
      i = open(os.path.join(self.templateDirectory, 'master.css'), 'r')
      o = open(os.path.join(self.outputDirectory, 'styles.css'), 'w')
      o.write(i.read())
      o.close()
      i.close()
      self.handle_new(None, None)

  def add_article(self, message_id):
    self.queue.put(message_id)

  def shutdown(self):
    self.running = False

  def log(self, message, debuglevel):
    if self.debug >= debuglevel:
      print "[{0}] {1}".format(self.name, message)

  def run(self):
    if self.should_terminate:
      self.shutdown()
      return
    if  __name__ == '__main__':
      return
    if not os.path.exists(self.outputDirectory):
      os.mkdir(self.outputDirectory)
    if not os.path.exists(self.database_directory):
      os.mkdir(self.database_directory)
    i = open(os.path.join(self.templateDirectory, 'master.css'), 'r')
    o = open(os.path.join(self.outputDirectory, 'styles.css'), 'w')
    o.write(i.read())
    o.close()
    i.close()
    self.sqlite_conn = sqlite3.connect(os.path.join(self.database_directory, 'pastes.db3'))
    self.sqlite = self.sqlite_conn.cursor()
    self.sqlite.execute('''CREATE TABLE IF NOT EXISTS pastes
                  (article_uid text, hash text PRIMARY KEY, sender text, email text, subject text, sent INTEGER, body text, root text, received INTEGER)''')
    self.sqlite_conn.commit()
    self.running = True
    self.regenerate_index = False
    self.log("starting up as plugin..", 2)
    while self.running:
      try:
        message_id = self.queue.get(block=True, timeout=1)
        f = open(os.path.join('articles', message_id), 'r')
        message_content = f.readlines()
        f.close()
        if len(message_content) == 0:
          self.log("empty NNTP message '{0}'. wtf?".format(message_id), 1)
          continue
        if not self.parse_message(message_id, message_content):
          continue
        self.regenerate_index = True
      except Queue.Empty as e:
        if self.regenerate_index:
          self.recreate_index()
          self.regenerate_index = False
    self.sqlite_conn.close()
    self.log("bye", 2)

  def basicHTMLencode(self, input):
    return input.replace('<', '&lt;').replace('>', '&gt;')

  def parse_message(self, message_id, message_content):
    if self.sqlite.execute('SELECT hash FROM pastes WHERE article_uid = ?', (message_id,)).fetchone():
      self.log("{0} already in database..".format(message_id), 2)
      return False
    #self.log("new paste: {0}".format(message_id), 2)
    hash_message_uid = sha1(message_id).hexdigest()
    identifier = hash_message_uid[:10]
    subject = 'No Title'
    sent = 0
    sender = 'None'
    email = 'non@giv.en'
    for index in xrange(0, len(message_content)):
      if message_content[index].lower().startswith('subject:'):
        subject = self.basicHTMLencode(message_content[index].split(' ', 1)[1][:-1])
      elif message_content[index].lower().startswith('date:'):
        sent = message_content[index].split(' ', 1)[1][:-1]
        sent_tz = parsedate_tz(sent)
        if sent_tz:
          offset = 0
          if sent_tz[-1]: offset = sent_tz[-1]
          sent = timegm((datetime(*sent_tz[:6]) - timedelta(seconds=offset)).timetuple())
        else:
          sent = int(time.time())
      elif message_content[index].lower().startswith('from:'):
        sender = self.basicHTMLencode(message_content[index].split(' ', 1)[1][:-1].split(' <', 1)[0])
        try:
          email = self.basicHTMLencode(message_content[index].split(' ', 1)[1][:-1].split(' <', 1)[1].replace('>', ''))
        except:
          pass
      elif message_content[index] == '\n':
        bar = message_content[index+1:]
        break
    bar = ''.join(bar)
    f = open(os.path.join(self.outputDirectory, identifier + '.txt'), 'w')
    f.write(bar)
    f.close()
    self.log("new paste: {0}".format(subject), 2)
    found = False
    try:
      if '.' in subject:
        if subject[-1] == ')':
          if ' (' in subject:
            name = subject.split(' (')[0]
          elif '(' in subject:
            name = subject.split('(')[0]
          else:
            name = subject
        else:
          name = subject
        if name.split('.')[-1] in self.recognized_extenstions:
          lexer = guess_lexer_for_filename(name, bar, encoding='utf-8')
          found = True
      if not found:
        if len(bar) >= 2:
          if bar[:2] == '#!':
            lexer = guess_lexer(bar, encoding='utf-8')
            if lexer.name not in self.allowed_lexers:
              lexer = get_lexer_by_name('text', encoding='utf-8')
          else:
            lexer = get_lexer_by_name('text', encoding='utf-8')
        else:
          lexer = get_lexer_by_name('text', encoding='utf-8')
    except ClassNotFound as e:
      self.log("{0}: {1}".format(subject, e), 0)
      lexer = get_lexer_by_name('text', encoding='utf-8')
    except ImportError as e:
      self.log("{0}: {1}".format(subject, e), 0)
      lexer = get_lexer_by_name('text', encoding='utf-8')
    result = highlight(bar, lexer, self.formatter)
    template = self.template_single_paste.replace('%%title%%', subject)
    template = template.replace('%%sender%%', sender)
    template = template.replace('%%sent%%', datetime.utcfromtimestamp(sent).strftime('%Y/%m/%d %H:%M UTC'))
    template = template.replace('%%identifier%%', identifier)
    template = template.replace('%%paste%%', result)
    f = open(os.path.join(self.outputDirectory, identifier + '.html'), 'w')
    f.write(template)
    f.close()
    self.sqlite.execute('INSERT INTO pastes VALUES (?,?,?,?,?,?,?,?,?)', (message_id, hash_message_uid, sender.decode('UTF-8'), email.decode('UTF-8'), subject.decode('UTF-8'), sent, ''.join(bar).decode('UTF-8'), '', int(time.time())))
    self.sqlite_conn.commit()
    del result, bar, template
    return True

  def recreate_index(self):
    self.log("rewriting index: {0}..".format(os.path.join(self.outputDirectory, 'index.html')), 3)
    paste_recent = list()
    for row in self.sqlite.execute('SELECT hash, subject, sender, sent FROM pastes ORDER by sent DESC').fetchall():
      paste_recent.append('<tr><td><a href="{0}.html">{1}</a></td><td>{2}</td><td>{3}</td></tr>\n'.format(row[0][:10], row[1].encode('UTF-8'), row[2].encode('UTF-8'), datetime.utcfromtimestamp(row[3]).strftime('%Y/%m/%d %H:%M UTC')))
    f = open(os.path.join(self.outputDirectory, 'index.html'), 'w')
    template = self.template_index.replace('%%reply%%', '')
    template = template.replace('%%target%%', '')
    template = template.replace('%%pasterows%%', ''.join(paste_recent))
    f.write(template)
    f.close()

  def handle_new(self, signum, frame):
    if self.busy:
      self.retry = True
      return
    self.busy = True
    something_new = False
    for message_id in os.listdir(self.watching):
      f = open(os.path.join(self.watching, message_id), 'r')
      message_content = f.readlines()
      f.close()
      if len(message_content) == 0:
        self.log("empty NNTP message '{0}'. wtf?".format(message_id), 1)
        os.remove(os.path.join(self.watching, message_id))
        continue
      if not self.parse_message(message_id, message_content):
        os.remove(os.path.join(self.watching, message_id))
        continue
      something_new = True
      os.remove(os.path.join(self.watching, message_id))
    if something_new:
      self.recreate_index()
    self.busy = False
    if self.retry:
      self.retry = False
      self.handle_new(None, None)

if __name__ == '__main__':
  #hook_dir = '/home/user/dev/anonet/nntp/SRNd/data/hooks/paste/'
  #templateDirectory = '/home/user/dev/anonet/nntp/SRNd/data/plugins/paste/'
  #outputDirectory = '/home/user/dev/anonet/nntp/SRNd/data/plugins/paste/out/'
  #foo = paster(templateDirectory, outputDirectory, hook_dir)
  args = dict()
  args['watch_directory'] = 'hooks/paste'
  args['template_directory'] = 'plugins/paste/templates'
  args['output_directory'] = 'plugins/paste/out'
  args['database_directory'] = 'plugins/paste'
  args['debug'] = '5'
  #hook_dir = 'hooks/paste/'
  #templateDirectory = 'plugins/paste/'
  #outputDirectory = 'plugins/paste/out/'
  #foo = paster('plugins/paste', 'plugins/paste/out', 'hooks/paste')
  foo = main('paster', args)
  foo.start()
  while True:
    try:
      #time.sleep(3600)
      signal.pause()
    except:
      print
      foo.shutdown()
      exit(0)
