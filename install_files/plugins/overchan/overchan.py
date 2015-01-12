#!/usr/bin/python
import sqlite3
import time
from datetime import datetime, timedelta
from email.utils import parsedate_tz
from calendar import timegm
import random
import string
import os
import threading
import urllib
from hashlib import sha1
from email.feedparser import FeedParser
import Image
import codecs
if __name__ == '__main__':
  import signal
  import fcntl
else:
  import Queue

class main(threading.Thread):

  def __init__(self, thread_name, args):
    threading.Thread.__init__(self)
    self.name = thread_name
    self.should_terminate = False
    self.debug = 5
    # FIXME read debuglevel here

    error = ''
    for arg in ('template_directory', 'output_directory', 'database_directory', 'temp_directory', 'no_file', 'invalid_file'):
      if not arg in args:
        error += "  {0} not in arguments\n".format(arg)
    if error != '':
      self.log('error:', 0)
      self.log(error[:-1], 0)
      self.log('terminating', 0)
      self.should_terminate = True
      if __name__ == '__main__':
        exit(1)
      else:
        return
    self.output_directory = args['output_directory']
    self.database_directory = args['database_directory']
    self.template_directory = args['template_directory']
    self.temp_directory = args['temp_directory']
    if not os.path.exists(self.template_directory):
      self.log("error: template directory '{0}' does not exist".format(self.template_directory), 0)
      self.log("terminating", 0)
      self.should_terminate = True
      if __name__ == '__main__':
        exit(1)
      else:
        return
    self.no_file = args['no_file']
    self.invalid_file = args['invalid_file']
    if not os.path.exists(os.path.join(self.template_directory, self.no_file)):
      self.log("replacement for root posts without picture not found: {0}".format(os.path.join(self.template_directory, self.no_file)), 0)
      self.log("terminating..", 0)
      self.should_terminate = True
      if __name__ == '__main__':
        exit(1)
      else:
        return
    if not os.path.exists(os.path.join(self.template_directory, self.invalid_file)):
      self.log("replacement for posts with invalid pictures not found: {0}".format(os.path.join(self.template_directory, self.invalid_file)), 0)
      self.log("terminating..", 0)
      self.should_terminate = True
      if __name__ == '__main__':
        exit(1)
      else:
        return
    error = ''
    for template in ('board.tmpl', 'board_threads.tmpl', 'thread_single.tmpl', 'message_root.tmpl', 'message_child_pic.tmpl', 'message_child_nopic.tmpl'):
      template_file = os.path.join(self.template_directory, template)
      if not os.path.exists(template_file):
        error += "{0} missing\n".format(template_file)
    if error != '':
      self.log('error:', 0)
      self.log(error[:-1], 0)
      self.log('terminating', 0)
      self.should_terminate = True
      if __name__ == '__main__':
        exit(1)
      else:
        return
    # TODO use tuple instead and load in above loop
    f = open(os.path.join(self.template_directory, 'board.tmpl'))
    self.template_board = f.read()
    f.close()
    f = open(os.path.join(self.template_directory, 'board_threads.tmpl'))
    self.template_board_threads = f.read()
    f.close
    f = open(os.path.join(self.template_directory, 'thread_single.tmpl'))
    self.template_thread_single = f.read()
    f.close
    f = open(os.path.join(self.template_directory, 'message_root.tmpl'))
    self.template_message_root = f.read()
    f.close()
    f = open(os.path.join(self.template_directory, 'message_child_pic.tmpl'))
    self.template_message_child_pic = f.read()
    f.close()
    f = open(os.path.join(self.template_directory, 'message_child_nopic.tmpl'))
    self.template_message_child_nopic = f.read()
    f.close()

    if __name__ == '__main__':
      if not 'watch_dir' in args:
        self.log("watch_dir not in args.", 0)
        self.log("terminating", 0)
        exit(1)
      else:
        self.watch_dir = args['watch_dir']
      if not self.init_standalone():
        exit(1)
    else:
      if not self.init_plugin():
        self.should_terminate = True
        return

  def init_plugin(self):
    self.log("initializing as plugin..", 2)
    try:
      # load required imports for PIL
      something = Image.open(os.path.join(self.template_directory, self.no_file))
      modifier = float(180) / something.size[0]
      x = int(something.size[0] * modifier)
      y = int(something.size[1] * modifier)
      if something.mode == 'RGBA' or something.mode == 'LA':
        thumb_name = 'nope_loading_PIL.png'
      else:
        something = something.convert('RGB')
        thumb_name = 'nope_loading_PIL.jpg'
      something = something.resize((x,y), Image.ANTIALIAS)
      out = os.path.join(self.template_directory, thumb_name)
      something.save(out, optimize=True)
      del something
      os.remove(out)
    except IOError as e:
      self.log("error: can't load PIL library", 0)
      self.log("terminating..", 0)
      self.should_terminate = True
      return False
    self.queue = Queue.Queue()
    return True

  def init_standalone(self):
    self.log("initializing as standalone..", 2)
    signal.signal(signal.SIGIO, self.signal_handler)
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
    self.past_init()
    return True

  def past_init(self):
    required_dirs = list()
    required_dirs.append(self.output_directory)
    required_dirs.append(os.path.join(self.output_directory, 'img'))
    required_dirs.append(os.path.join(self.output_directory, 'thumbs'))
    required_dirs.append(self.database_directory)
    required_dirs.append(self.temp_directory)
    for directory in required_dirs:
      if not os.path.exists(directory):
        os.mkdir(directory)
    del required_dirs
    # TODO use softlinks or at least cp instead
    link = os.path.join(self.output_directory, 'img', self.no_file)
    if not os.path.exists(link):
      f = open(os.path.join(self.template_directory, self.no_file), 'r')
      o = open(link, 'w')
      o.write(f.read())
      o.close()
      f.close()
    link = os.path.join(self.output_directory, 'thumbs', self.no_file)
    if not os.path.exists(link):
      f = open(os.path.join(self.template_directory, self.no_file), 'r')
      o = open(link, 'w')
      o.write(f.read())
      o.close()
      f.close()
    link = os.path.join(self.output_directory, 'thumbs', self.invalid_file)
    if not os.path.exists(link):
      try:
        something = Image.open(os.path.join(self.template_directory, self.invalid_file))
        modifier = float(180) / something.size[0]
        x = int(something.size[0] * modifier)
        y = int(something.size[1] * modifier)
        if not (something.mode == 'RGBA' or something.mode == 'LA'):
          something = something.convert('RGB')
        something = something.resize((x,y), Image.ANTIALIAS)
        something.save(link, optimize=True)
        del something
      except IOError as e:
        self.log("error: can't save {0}. wtf? {1}".format(link, e), 0)
    self.regenerate_boards = list()
    self.regenerate_threads = list()
    self.missing_parents = dict()
    self.sqlite_conn = sqlite3.connect(os.path.join(self.database_directory, 'overchan.db3'))
    self.sqlite = self.sqlite_conn.cursor()
    self.sqlite.execute('''CREATE TABLE IF NOT EXISTS groups
               (group_id INTEGER PRIMARY KEY AUTOINCREMENT, group_name text UNIQUE, article_count INTEGER, last_update INTEGER)''')
    self.sqlite.execute('''CREATE TABLE IF NOT EXISTS articles
               (article_uid text, group_id INTEGER, sender text, email text, subject text, sent INTEGER, parent text, message text, imagename text, imagelink text, thumblink text, last_update INTEGER, PRIMARY KEY (article_uid, group_id))''')
    self.sqlite_conn.commit()
    #self.sqlite_hashes_conn = sqlite3.connect('hashes.db3')
    #self.sqlite_hashes = self.sqlite_hashes_conn.cursor()
    # regenerate all boards and threads - START
    for group_row in self.sqlite.execute('SELECT group_id FROM groups').fetchall():
      if group_row[0] not in self.regenerate_boards:
        self.regenerate_boards.append(group_row[0])
    for thread_row in self.sqlite.execute('SELECT article_uid FROM articles WHERE parent = "" OR parent = article_uid ORDER BY last_update DESC').fetchall():
      if thread_row[0] not in self.regenerate_threads:
        self.regenerate_threads.append(thread_row[0])
    # regenerate all boards and threads - END

  def shutdown(self):
    self.running = False

  def add_article(self, message_id):
    self.queue.put(message_id)

  def log(self, message, debuglevel):
    if self.debug >= debuglevel:
      message = "{0}".format(message)
      for line in message.split('\n'):
        print "[{0}] {1}".format(self.name, line)

  def signal_handler(self, signum, frame):
    for item in os.listdir(self.watching):
      link = os.path.join(self.watching, item)
      f = open(link, 'r')
      if not self.parse_message(message_id, f):
        f.close()
      os.remove(link)
    if len(self.regenerate_boards) > 0:
      for board in self.regenerate_boards:
        self.generate_board(board)
      del self.regenerate_boards[:]
    if len(self.regenerate_threads) > 0:
      for thread in self.regenerate_threads:
        self.generate_thread(thread)
      del self.regenerate_threads[:]

  def run(self):
    if self.should_terminate:
      return
    if  __name__ == '__main__':
      return
    self.log("starting up as plugin..", 2)
    self.past_init()
    self.running = True
    while self.running:
      try:
        message_id = self.queue.get(block=True, timeout=1)
        f = open(os.path.join('articles', message_id), 'r')
        if not self.parse_message(message_id, f):
          f.close()
      except Queue.Empty as e:
        if len(self.regenerate_boards) > 0:
          for board in self.regenerate_boards:
            self.generate_board(board)
          self.regenerate_boards = list()
        if len(self.regenerate_threads) > 0:
          for thread in self.regenerate_threads:
            self.generate_thread(thread)
          self.regenerate_threads = list()
    self.sqlite_conn.close()
    #self.sqlite_hashes_conn.close()
    self.log('bye', 2)

  def basicHTMLencode(self, inputString):
    return inputString.replace('<', '&lt;').replace('>', '&gt;')

  def parse_message(self, message_id, fd):
    if self.sqlite.execute('SELECT subject FROM articles WHERE article_uid = ?', (message_id,)).fetchone():
      self.log("{0} already in database..".format(message_id), 2)
      return False
    self.log('new message: {0}'.format(message_id), 2)

    hash_message_uid = sha1(message_id).hexdigest()
    identifier = hash_message_uid[:10]
    subject = 'None'
    sent = 0
    sender = 'Anonymous'
    email = 'nobody@no.where'
    parent = ''
    groups = list()
    sage = False
    header_found = False
    parser = FeedParser()
    line = fd.readline()
    while line != '':
      parser.feed(line)
      lower_line = line.lower()
      if lower_line.startswith('subject:'):
        subject = self.basicHTMLencode(line.split(' ', 1)[1][:-1])
      elif lower_line.startswith('date:'):
        sent = line.split(' ', 1)[1][:-1]
        sent_tz = parsedate_tz(sent)
        if sent_tz:
          offset = 0
          if sent_tz[-1]: offset = sent_tz[-1]
          sent = timegm((datetime(*sent_tz[:6]) - timedelta(seconds=offset)).timetuple())
        else:
          sent = int(time.time())
      elif lower_line.startswith('from:'):
        sender = self.basicHTMLencode(line.split(' ', 1)[1][:-1].split(' <', 1)[0])
        try:
          email = self.basicHTMLencode(line.split(' ', 1)[1][:-1].split(' <', 1)[1].replace('>', ''))
        except:
          pass
      elif lower_line.startswith('references:'):
        parent = line[:-1].split(' ')[1]
      elif lower_line.startswith('newsgroups:'):
        group_in = lower_line[:-1].split(' ', 1)[1]
        if ';' in group_in:
          groups_in = group_in.split(';')
          for group_in in groups_in:
            if group_in.startswith('overchan.'):
              groups.append(group_in)
        else:
          groups.append(group_in)
      elif lower_line.startswith('x-sage:'):
        sage = True
      elif line == '\n':
        header_found = True
        break
      line = fd.readline()

    if not header_found:
      self.log("{0} malformed article".format(message_id), 2)
      return False
    group_ids = list()
    for group in groups:
      result = self.sqlite.execute('SELECT group_id FROM groups WHERE group_name=?', (group,)).fetchone()
      if not result:
        self.sqlite.execute('INSERT INTO groups(group_name, article_count, last_update) VALUES (?,?,?)', (group, 1, int(time.time())))
        self.sqlite_conn.commit()
        group_ids.append(int(self.sqlite.execute('SELECT group_id FROM groups WHERE group_name=?', (group,)).fetchone()[0]))
      else:
        group_ids.append(int(result[0]))
    for group_id in group_ids:
      if group_id not in self.regenerate_boards:
        self.regenerate_boards.append(group_id)

    if parent != '' and parent != message_id:
      last_update = sent
      if parent not in self.regenerate_threads:
        self.regenerate_threads.append(parent)
      if not sage:
        result = self.sqlite.execute('SELECT last_update FROM articles WHERE article_uid = ?', (parent,)).fetchone()
        if result:
          parent_last_update = result[0]
          if sent > parent_last_update:
            self.sqlite.execute('UPDATE articles SET last_update=? WHERE article_uid=?', (sent, parent))
            self.sqlite_conn.commit()
        else:
          self.log('error: missing parent {0} for post {1}'.format(parent, message_id), 1)
          if parent in self.missing_parents:
            if sent > self.missing_parents[parent]:
              self.missing_parents[parent] = sent
          else:
            self.missing_parents[parent] = sent
    else:
      # root post
      if not message_id in self.missing_parents:
        last_update = sent
      else:
        if self.missing_parents[message_id] > sent:
          # obviously the case. still we check for invalid dates here
          last_update = self.missing_parents[message_id]
        else:
          last_update = sent
        del self.missing_parents[message_id]
        self.log('found a missing parent: {0}'.format(message_id), 1)
        if len(self.missing_parents) > 0:
          self.log('still missing {0} parents'.format(len(self.missing_parents)), 1)
      if message_id not in self.regenerate_threads:
        self.regenerate_threads.append(message_id)

    #parser = FeedParser()
    parser.feed(fd.read())
    fd.close()
    result = parser.close()
    del parser
    image_name_original = ''
    image_name = ''
    thumb_name = ''
    # TODO: check if out dir is remote fs, use os.rename if not
    if result.is_multipart():
      for part in result.get_payload():
        if part.get_content_type().startswith('image/'):
          tmp_link = os.path.join(self.temp_directory, 'tmpImage')
          f = open(tmp_link, 'w')
          f.write(part.get_payload(decode=True))
          f.close()
          # get hash for filename
          f = open(tmp_link, 'r')
          image_name_original = self.basicHTMLencode(part.get_filename())
          imagehash = sha1(f.read()).hexdigest()
          image_name = imagehash + '.' + image_name_original.split('.')[-1].lower()
          out_link = os.path.join(self.output_directory, 'img', image_name)
          f.close()
          # copy to out directory with new filename
          c = open(out_link, 'w')
          f = open(tmp_link, 'r')
          c.write(f.read())
          c.close()
          f.close()
          if image_name_original.split('.')[-1].lower() == 'gif':
            # copy to thumb directory with new filename
            # TODO: use relative link instead
            thumb_link = os.path.join(self.output_directory, 'thumbs', image_name)
            thumb_name = image_name
            c = open(thumb_link, 'w')
            f = open(tmp_link, 'r')
            c.write(f.read())
            c.close()
            f.close()
          else:
            # create thumb, convert to RGB and use jpeg if no transparency involved, png if it is
            try:
              thumb = Image.open(out_link)
              # always use width for modifier
              modifier = float(180) / thumb.size[0]
              #if thumb.size[0] > thumb.size[1]:
              #  modifier = float(200) / thumb.size[0]
              #else:
              #  modifier = float(200) / thumb.size[1]
              x = int(thumb.size[0] * modifier)
              y = int(thumb.size[1] * modifier)
              self.log("old image size: {0}x{1}, new image size: {2}x{3}".format(thumb.size[0], thumb.size[1], x, y), 3)
              if thumb.mode == 'RGBA' or thumb.mode == 'LA':
                thumb_name = imagehash + '.png'
              else:
                thumb = thumb.convert('RGB')
                thumb_name = imagehash + '.jpg'
              thumb_link = os.path.join(self.output_directory, 'thumbs', thumb_name)
              thumb = thumb.resize((x,y), Image.ANTIALIAS)
              #thumb.thumbnail((200, 200), Image.ANTIALIAS)
              thumb.save(thumb_link, optimize=True)
              del thumb
            except Exception as e:
              self.log(e, 3)
              thumb_name = 'invalid'
          os.remove(tmp_link)
          #os.rename('tmp/tmpImage', 'html/img/' + imagelink) # damn remote file systems and stuff
        elif part.get_content_type().lower() == 'text/plain':
          message = part.get_payload(decode=True)
        else:
          message = '----' + part.get_content_type() + '----\n'
          message += part.get_payload() + '\n'
          message += '----' + part.get_content_type() + '----'
    else:
      if result.get_content_type().lower() == 'text/plain':
        message = result.get_payload(decode=True)
      else:
        message = '----' + result.get_content_type() + '----\n'
        message += result.get_payload() + '\n'
        message += '----' + result.get_content_type() + '----'
    del result
    message = self.basicHTMLencode(message)
    for group_id in group_ids:
      self.sqlite.execute('INSERT INTO articles(article_uid, group_id, sender, email, subject, sent, parent, message, imagename, imagelink, thumblink, last_update) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', (message_id, group_id, sender.decode('UTF-8'), email.decode('UTF-8'), subject.decode('UTF-8'), sent, parent, message.decode('UTF-8'), image_name_original.decode('UTF-8'), image_name, thumb_name, last_update))
      self.sqlite.execute('UPDATE groups SET last_update=?, article_count = (SELECT count(article_uid) FROM articles WHERE group_id = ?) WHERE group_id = ?', (int(time.time()), group_id, group_id))
    self.sqlite_conn.commit()
    return True

  def generate_board(self, group_id):
    full_board_name = self.sqlite.execute('SELECT group_name FROM groups WHERE group_id = ?', (group_id,)).fetchone()[0]
    board_name = full_board_name.split('.', 1)[1]
    threads = int(self.sqlite.execute('SELECT count(article_uid) FROM articles WHERE group_id = ? AND (parent = "" OR parent = article_uid)', (group_id,)).fetchone()[0])
    pages = int(threads / 10)
    if threads % 10 != 0:
      pages += 1;
    thread_counter = 0
    page_counter = 1
    threads = list()
    for root_row in self.sqlite.execute('SELECT article_uid, sender, subject, sent, message, imagename, imagelink, thumblink FROM articles WHERE group_id = ? AND (parent = "" OR parent = article_uid) ORDER BY last_update DESC', (group_id,)).fetchall():
      root_message_id_hash = sha1(root_row[0]).hexdigest()[:10] # self.sqlite_hashes.execute('SELECT message_id_hash from article_hashes WHERE message_id = ?', (root_row[0],)).fetchone()
      #if hash_result:
      #  root_message_id_hash = hash_result[0]
      #else:
      #  self.log('message hash for {0} not found. wtf?'.format(root_row[0]), 0)
      #  continue
      if thread_counter == 10:
        self.log("generating {0}/{1}-{2}.html".format(self.output_directory, board_name, page_counter), 2)
        board_template = self.template_board.replace('%%threads%%', ''.join(threads))
        pagelist = list()
        for page in xrange(1, pages + 1):
          if page != page_counter:
            pagelist.append('<a href="{0}-{1}.html">[{1}]</a>&nbsp;'.format(self.basicHTMLencode(board_name), page))
          else:
            pagelist.append('[{0}]&nbsp;'.format(page))
        board_template = board_template.replace('%%pagelist%%', ''.join(pagelist))
        del pagelist
        boardlist = list()
        for group_row in self.sqlite.execute('SELECT group_name, group_id FROM groups ORDER by group_name ASC').fetchall():
          if group_row[1] != group_id:
            boardlist.append('&nbsp;<a href="{0}-1.html">{0}</a>&nbsp;|'.format(self.basicHTMLencode(group_row[0].split('.', 1)[1])))
          else:
            boardlist.append('&nbsp;' + self.basicHTMLencode(group_row[0].split('.', 1)[1]) + '&nbsp;|')
        boardlist[-1] = boardlist[-1][:-1]
        board_template = board_template.replace('%%boardlist%%', ''.join(boardlist))
        board_template = board_template.replace('%%board%%', full_board_name)
        board_template = board_template.replace('%%target%%', "{0}-1.html".format(board_name))
        del boardlist
        f = codecs.open(os.path.join(self.output_directory, '{0}-{1}.html'.format(board_name, page_counter)), 'w', 'UTF-8')
        f.write(board_template)
        f.close()
        threads = list()
        page_counter += 1
        thread_counter = 0
      thread_counter += 1
      if root_row[6] != '':
        root_imagelink = root_row[6]
        if root_row[7] != 'invalid':
          root_thumblink = root_row[7]
        else:
          root_thumblink = self.invalid_file
      else:
        root_imagelink = self.no_file
        root_thumblink = self.no_file
      rootTemplate = self.template_message_root.replace('%%articlehash%%', root_message_id_hash)
      rootTemplate = rootTemplate.replace('%%author%%', root_row[1])
      rootTemplate = rootTemplate.replace('%%subject%%', root_row[2])
      rootTemplate = rootTemplate.replace('%%sent%%', datetime.utcfromtimestamp(root_row[3]).strftime('%Y/%m/%d %H:%M'))
      rootTemplate = rootTemplate.replace('%%imagelink%%', root_imagelink)
      rootTemplate = rootTemplate.replace('%%thumblink%%', root_thumblink)
      rootTemplate = rootTemplate.replace('%%imagename%%', root_row[5])
      childs = list()
      childs.append('')
      child_count = int(self.sqlite.execute('SELECT count(article_uid) FROM articles WHERE parent = ? AND parent != article_uid AND group_id = ?', (root_row[0], group_id)).fetchone()[0])
      if child_count > 4:
        missing = child_count - 4
      else:
        missing = 0
      for child_row in self.sqlite.execute('SELECT * FROM (SELECT article_uid, sender, subject, sent, message, imagename, imagelink, thumblink FROM articles WHERE parent = ? AND parent != article_uid AND group_id = ? ORDER BY sent DESC LIMIT 4) ORDER BY sent ASC', (root_row[0], group_id)).fetchall():
        #message_id_hash = sha1(child_row[0])hexdigest()[:10] #self.sqlite_hashes.execute('SELECT message_id_hash from article_hashes WHERE message_id = ?', (child_row[0],)).fetchone()
        #if hash_result:
        #  message_id_hash = hash_result[0]
        #else:
        #  self.log('message hash for {0} not found. wtf?'.format(child_row[0]), 0)
        #  continue
        if child_row[6] != '':
          if child_row[7] != 'invalid':
            child_thumblink = child_row[7]
          else:
            child_thumblink = self.invalid_file
          childTemplate = self.template_message_child_pic.replace('%%imagelink%%', child_row[6])
          childTemplate = childTemplate.replace('%%thumblink%%', child_thumblink)
          childTemplate = childTemplate.replace('%%imagename%%', child_row[5])
        else:
          childTemplate = self.template_message_child_nopic
        childTemplate = childTemplate.replace('%%articlehash%%', sha1(child_row[0]).hexdigest()[:10])
        childTemplate = childTemplate.replace('%%author%%', child_row[1])
        childTemplate = childTemplate.replace('%%subject%%', child_row[2])
        childTemplate = childTemplate.replace('%%sent%%', datetime.utcfromtimestamp(child_row[3]).strftime('%Y/%m/%d %H:%M'))
        childTemplate = childTemplate.replace('%%message%%', child_row[4])
        childs.append(childTemplate)
      if missing > 0:
        if missing == 1:
          post = "post"
        else:
          post = "posts"
        rootTemplate = rootTemplate.replace('%%message%%', root_row[4] + '\n<a href="thread-{0}.html">{1} {2} omitted</a>'.format(root_message_id_hash, missing, post))
      else:
        rootTemplate = rootTemplate.replace('%%message%%', root_row[4])
      threadsTemplate = self.template_board_threads.replace('%%message_root%%', rootTemplate)
      threadsTemplate = threadsTemplate.replace('%%message_childs%%', ''.join(childs))
      threads.append(threadsTemplate)
      del childs
    if thread_counter > 0 or (page_counter == 1 and thread_counter == 0):
      self.log("generating {0}/{1}-{2}.html".format(self.output_directory, board_name, page_counter), 2)
      board_template = self.template_board.replace('%%threads%%', ''.join(threads))
      pagelist = list()
      for page in xrange(1, pages + 1):
        if page != page_counter:
          pagelist.append('<a href="{0}-{1}.html">[{1}]</a>&nbsp;'.format(board_name, page))
        else:
          pagelist.append('[{0}]&nbsp;'.format(page))
      board_template = board_template.replace('%%pagelist%%', ''.join(pagelist))
      boardlist = list()
      for group_row in self.sqlite.execute('SELECT group_name, group_id FROM groups ORDER by group_name ASC').fetchall():
        if group_row[1] != group_id:
          boardlist.append('&nbsp;<a href="{0}-1.html">{0}</a>&nbsp;|'.format(self.basicHTMLencode(group_row[0].split('.', 1)[1])))
        else:
          boardlist.append('&nbsp;' + self.basicHTMLencode(group_row[0].split('.', 1)[1]) + '&nbsp;|')
      boardlist[-1] = boardlist[-1][:-1]
      board_template = board_template.replace('%%boardlist%%', ''.join(boardlist))
      board_template = board_template.replace('%%board%%', full_board_name)
      board_template = board_template.replace('%%target%%', "{0}-1.html".format(board_name))
      f = codecs.open(os.path.join(self.output_directory, '{0}-{1}.html'.format(board_name, page_counter)), 'w', 'UTF-8')
      f.write(board_template)
      f.close()
      del pagelist
      del boardlist
      del threads

  def generate_thread(self, root_uid):
    root_row = self.sqlite.execute('SELECT article_uid, sender, subject, sent, message, imagename, imagelink, thumblink, group_id FROM articles WHERE article_uid = ?', (root_uid,)).fetchone()
    if not root_row:
      self.log('error: root post not yet available: {0}'.format(root_uid), 1)
      return
    root_message_id_hash = sha1(root_uid).hexdigest() #self.sqlite_hashes.execute('SELECT message_id_hash from article_hashes WHERE message_id = ?', (root_row[0],)).fetchone()
    #if hash_result:
    #  root_message_id_hash = hash_result[0]
    #else:
    #  self.log('message hash for {0} not found. wtf?'.format(root_row[0]), 0)
    #  return
    self.log("generating {0}/thread-{1}.html".format(self.output_directory, root_message_id_hash[:10]), 2)
    if root_row[6] != '':
      root_imagelink = root_row[6]
      if root_row[7] != 'invalid':
        root_thumblink = root_row[7]
      else:
        root_thumblink = self.invalid_file
    else:
      root_imagelink = self.no_file
      root_thumblink = self.no_file
    rootTemplate = self.template_message_root.replace('%%articlehash%%', root_message_id_hash[:10])
    rootTemplate = rootTemplate.replace('%%author%%', root_row[1])
    rootTemplate = rootTemplate.replace('%%subject%%', root_row[2])
    rootTemplate = rootTemplate.replace('%%sent%%', datetime.utcfromtimestamp(root_row[3]).strftime('%Y/%m/%d %H:%M'))
    rootTemplate = rootTemplate.replace('%%imagelink%%', root_imagelink)
    rootTemplate = rootTemplate.replace('%%thumblink%%', root_thumblink)
    rootTemplate = rootTemplate.replace('%%imagename%%', root_row[5])
    rootTemplate = rootTemplate.replace('%%message%%', root_row[4])
    childs = list()
    childs.append('')
    for child_row in self.sqlite.execute('SELECT article_uid, sender, subject, sent, message, imagename, imagelink, thumblink FROM articles WHERE parent = ? AND parent != article_uid ORDER BY sent ASC', (root_uid,)).fetchall():
      #message_id_hash = sha1(child_row[0]).hexdigest()[:10]#self.sqlite_hashes.execute('SELECT message_id_hash from article_hashes WHERE message_id = ?', (child_row[0],)).fetchone()
      #if hash_result:
      #  message_id_hash = hash_result[0]
      #else:
      #  self.log('message hash for {0} not found. wtf?'.format(child_row[0]), 0)
      #  continue
      if child_row[6] != '':
        if child_row[7] != 'invalid':
          child_thumblink = child_row[7]
        else:
          child_thumblink = self.invalid_file
        childTemplate = self.template_message_child_pic.replace('%%imagelink%%', child_row[6])
        childTemplate = childTemplate.replace('%%thumblink%%', child_thumblink)
        childTemplate = childTemplate.replace('%%imagename%%', child_row[5])
      else:
        childTemplate = self.template_message_child_nopic
      childTemplate = childTemplate.replace('%%articlehash%%', sha1(child_row[0]).hexdigest()[:10])
      childTemplate = childTemplate.replace('%%author%%', child_row[1])
      childTemplate = childTemplate.replace('%%subject%%', child_row[2])
      childTemplate = childTemplate.replace('%%sent%%', datetime.utcfromtimestamp(child_row[3]).strftime('%Y/%m/%d %H:%M'))
      childTemplate = childTemplate.replace('%%message%%', child_row[4])
      childs.append(childTemplate)
    threadsTemplate = self.template_board_threads.replace('%%message_root%%', rootTemplate)
    threadsTemplate = threadsTemplate.replace('%%message_childs%%', ''.join(childs))
    boardlist = list()
    for group_row in self.sqlite.execute('SELECT group_name, group_id FROM groups ORDER by group_name ASC').fetchall():
      boardlist.append('&nbsp;<a href="{0}-1.html">{0}</a>&nbsp;|'.format(self.basicHTMLencode(group_row[0].split('.', 1)[1])))
      if group_row[1] == root_row[8]:
        group_name = group_row[0]
    boardlist[-1] = boardlist[-1][:-1]
    threadSingle = self.template_thread_single.replace('%%boardlist%%', ''.join(boardlist))
    threadSingle = threadSingle.replace('%%thread_id%%', root_message_id_hash)
    # FIXME group_name may contain " and thus allow html code injection, if encoded postman won't recognize so change must be at both sides
    threadSingle = threadSingle.replace('%%board%%', group_name)
    threadSingle = threadSingle.replace('%%target%%', "{0}-1.html".format(group_name.split('.', 1)[1]))
    threadSingle = threadSingle.replace('%%thread_single%%', threadsTemplate)
    f = codecs.open(os.path.join(self.output_directory, 'thread-{0}.html'.format(root_message_id_hash[:10])), 'w', 'UTF-8')
    f.write(threadSingle)
    f.close()
    del childs
    del boardlist

if __name__ == '__main__':
  # FIXME fix this shit
  overchan = main('overchan', args)
  while True:
    try:
      print "signal.pause()"
      signal.pause()
    except KeyboardInterrupt as e:
      print
      self.sqlite_conn.close()
      self.log('bye', 2)
      exit(0)
    except Exception as e:
      print "Exception:", e  
      self.sqlite_conn.close()
      self.log('bye', 2)
      exit(0)
