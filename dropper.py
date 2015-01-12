#!/usr/bin/python
import threading
import sqlite3
import os
import time
import codecs
import random
import string
import signal
from hashlib import sha1

class dropper(threading.Thread):
  def __init__(self, listener, master, debug=3):
    self.SRNd = master
    self.socket = listener
    self.watching = os.path.join(os.getcwd(), "incoming")
    self.sqlite_conn = sqlite3.connect('dropper.db3')
    self.sqlite = self.sqlite_conn.cursor()
    self.sqlite.execute('''CREATE TABLE IF NOT EXISTS groups
               (group_id INTEGER PRIMARY KEY AUTOINCREMENT, group_name text UNIQUE, lowest_id INTEGER, highest_id INTEGER, article_count INTEGER, flag text, group_added_at INTEGER, last_update INTEGER)''')
    self.sqlite.execute('''CREATE TABLE IF NOT EXISTS articles
               (message_id text, group_id INTEGER, article_id INTEGER, received INTEGER, PRIMARY KEY (article_id, group_id))''')
    self.sqlite_conn.commit()
    self.sqlite_hasher_conn = sqlite3.connect('hashes.db3')
    self.sqlite_hasher = self.sqlite_hasher_conn.cursor()
    self.sqlite_hasher.execute('''CREATE TABLE IF NOT EXISTS article_hashes
               (message_id text PRIMARY KEY, message_id_hash text)''')
    self.sqlite_hasher_conn.commit()
    self.reqs = ['message-id', 'newsgroups', 'date', 'subject', 'from', 'path']
    threading.Thread.__init__(self)
    self.name = "SRNd-dropper"
    self.debug = debug
    #self.handler_reconfigure_hooks(None, None)

  def handler_progress_incoming(self, signum, frame):
    if not self.running: return
    if self.busy:
      self.retry = True
      return
    self.busy = True
    for item in os.listdir('incoming'):
      link = os.path.join('incoming', item)
      if os.path.isfile(link):
        if self.debug > 2: print "[dropper] processing new article: {0}".format(link)
        f = open(link, 'r')
        article = f.readlines()
        f.close()
        if not self.validate(article):
          if self.debug > 1: print "[dropper] article is invalid: {0}".format(item)
          os.rename(link, os.path.join('articles', 'invalid', item))
          continue
        message_id, groups, additional_headers = self.sanitize(article)
        if len(groups) == 0:
          if self.debug > 1: print "[dropper] article is invalid. newsgroup missing: {0}".format(item)
          os.rename(link, os.path.join('articles', 'invalid', item))
          continue
        if int(self.sqlite.execute('SELECT count(message_id) FROM articles WHERE message_id = ?', (message_id,)).fetchone()[0]) != 0:
          if self.debug > 2: print "[dropper] article is duplicate: {0}".format(item)
          os.rename(link, os.path.join('articles', 'duplicate', item))
          continue
        #print "[dropper] all good, writing article.."
        self.write(message_id, groups, additional_headers, article)
        os.remove(link)
    self.busy = False
    if self.retry:
      self.retry = False
      self.handler_progress_incoming(None, None)


  def validate(self, article):
    # check for header / body part exists in message
    # check if newsgroup exists in message
    # read required headers into self.dict
    if self.debug > 3: print "[dropper] validating article.."
    if not '\n' in article: return False
    return True

  def sanitize(self, article):
    # change required if necessary
    # don't read vars at all
    if self.debug > 3: print "[dropper] sanitizing article.."
    found = dict()
    vals = dict()
    for req in self.reqs:
      found[req] = False
    done = False
    for index in xrange(0, len(article)):
      for key in self.reqs:
        if article[index].lower().startswith(key + ':'):
          if key == 'path':
            article[index] = 'Path: sfor-SRNd!' + article[index].split(' ', 1)[1]
          elif key == 'from':
            # FIXME parse and validate from
            a = 1
          found[key] = True
          vals[key] = article[index].split(' ', 1)[1][:-1]
          #print "key: " + key + " value: " + vals[key]
        elif article[index] == '\n':
          done = True
          break
      if done: break

    additional_headers = list()
    for req in found:
      if not found[req]:
        if self.debug > 3: print '[dropper] {0} missing'.format(req)
        if req == 'message-id':
          if self.debug > 2: print "[dropper] should generate message-id.."
          rnd = ''.join(random.choice(string.ascii_lowercase) for x in range(10))
          vals[req] = '{0}{1}@dropper.SRNd'.format(rnd, int(time.time()))
          additional_headers.append('Message-ID: {0}\n'.format(vals[req]))
        elif req == 'newsgroups':
          vals[req] = list()
        elif req == 'date':
          if self.debug > 2: print "[dropper] should generate date.."
          #additional_headers.append('Date: {0}\n'.format(date format blah blah)
          # FIXME add current date in list, index 0 ?
        elif req == 'subject':
          if self.debug > 2: print "[dropper] should generate subject.."
          additional_headers.append('Subject: None\n')
        elif req == 'from':
          if self.debug > 2: print "[dropper] should generate sender.."
          additional_headers.append('From: Anonymous Coward <nobody@no.where>\n')
        elif req == 'path':
          if self.debug > 2: print "[dropper] should generate path.."
          additional_headers.append('Path: sfor-SRNd\n')
      else:
        if req == 'newsgroups':
          vals[req] = vals[req].split(',')
        #print "found {0}: {1}".format(req, vals[req])
    #print "got message_id:", vals['message-id']
    return (vals['message-id'], vals['newsgroups'], additional_headers)

  def write(self, message_id, groups, additional_headers, article):
    if self.debug > 3: print "[dropper] writing article.."
    link = os.path.join('articles', message_id)
    if os.path.exists(link):
      if self.debug > 0: print "[dropper] got duplicate: {0} which is not in database, this should not happen.".format(message_id)
      if self.debug > 0: print "[dropper] trying to fix by moving old file to articles/invalid so new article can be processed correctly."
      os.rename(link, os.path.join('articles', 'invalid', message_id))
    if self.debug > 3: print "[dropper] writing to", link
    #f = codecs.open(link, 'w', 'UTF-8')
    f = open(link, 'w')
    for index in xrange(0, len(additional_headers)):
      f.write(additional_headers[index])
    for index in xrange(0, len(article)):
      f.write(article[index])
    f.close()
    self.sqlite_hasher.execute('INSERT INTO article_hashes VALUES (?, ?)', (message_id, sha1(message_id).hexdigest()))
    self.sqlite_hasher_conn.commit()
    hooks = dict()
    for group in groups:
      if self.debug > 3: print "[dropper] creating link for", group
      article_link = '../../' + link
      group_dir = os.path.join('groups', group)
      if not os.path.exists(group_dir):
        self.sqlite.execute('INSERT INTO groups VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (None, group, 1, 0, 0, 'y', int(time.time()), int(time.time())))
        article_id = 1
        if self.debug > 3: print "[dropper] creating directory", group_dir
        os.mkdir(group_dir)
      else:
        article_id = int(self.sqlite.execute('SELECT highest_id FROM groups WHERE group_name = ?', (group,)).fetchone()[0]) + 1
      group_id = int(self.sqlite.execute('SELECT group_id FROM groups WHERE group_name = ?', (group,)).fetchone()[0])
      group_link = os.path.join(group_dir, str(article_id))
      os.symlink(article_link, group_link)
      self.sqlite.execute('INSERT INTO articles VALUES (?, ?, ?, ?)', (message_id, group_id, article_id, int(time.time())))
      self.sqlite.execute('UPDATE groups SET highest_id = ?, article_count = article_count + 1, last_update = ? WHERE group_id = ?', (article_id, int(time.time()), group_id))
      self.sqlite_conn.commit()
      # whitelist
      for group_item in self.SRNd.hooks:
        if (group_item[-1] == '*' and group.startswith(group_item[:-1])) or group == group_item:
          for hook in self.SRNd.hooks[group_item]:
            hooks[hook] = message_id
      #for hook in self.hooks['*']:
      #  links[os.path.join('hooks', hook, message_id)] = True
      # blacklist
      for group_item in self.SRNd.hook_blacklist:
        if (group_item[-1] == '*' and group.startswith(group_item[:-1])) or group == group_item:
          for hook in self.SRNd.hook_blacklist[group_item]:
            if hook in hooks:
              del hooks[hook]

    # FIXME 1) crossposting may match multiple times and thus deliver same hook multiple times
    # FIXME 2) if doing this block after group loop blacklist may filter valid hook from another group
    # FIXME currently doing the second variant
    for hook in hooks:
      if hook.startswith('filesystem-'):
        link = os.path.join('hooks', hook[11:], hooks[hook])
        if not os.path.exists(link):
          os.symlink(article_link, link)
      elif hook.startswith('outfeeds-'):
        parts = hook[9:].split(':')
        name = 'outfeed-' + ':'.join(parts[:-1]) + '-' + parts[-1]
        if name in self.SRNd.feeds:
          self.SRNd.feeds[name].add_article(hooks[hook])
        else:
          print "[dropper] unknown outfeed detected. wtf? {0}".format(name)
      elif hook.startswith('plugins-'):
        name = 'plugin-' + hook[8:]
        if name in self.SRNd.plugins:
          self.SRNd.plugins[name].add_article(hooks[hook])
        else:
          print "[dropper] unknown plugin detected. wtf? {0}".format(name)
      else:
        print "[dropper] unknown hook detected. wtf? {0}".format(hook)

  def run(self):
    self.running = True
    self.busy = False
    self.retry = False
    while self.running:
      time.sleep(5)
      #signal.pause()
