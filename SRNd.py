#!/usr/bin/python
import sys
import os
import time
import socket
import pwd
import threading
import sqlite3
from distutils.dir_util import copy_tree

import dropper
import feed

class SRNd(threading.Thread):
  def __init__(self):

    self.read_and_parse_config()

    # create some directories
    for directory in ('filesystem', 'outfeeds', 'plugins'):
      dir = os.path.join(self.data_dir, 'config', 'hooks', directory)
      if not os.path.exists(dir):
        os.makedirs(dir)
      os.chmod(dir, 0o777) # FIXME think about this, o+r should be enough?

    # install / update plugins
    print "[SRNd] installing / updating plugins"
    for directory in os.listdir('install_files'):
      result = copy_tree(os.path.join('install_files', directory), os.path.join(self.data_dir, directory), preserve_times=True, update=True)
    if self.setuid != '':
      print "[SRNd] fixing plugin permissions"
      for directory in os.listdir(os.path.join(self.data_dir, 'plugins')):
        try:
          os.chown(os.path.join(self.data_dir, 'plugins', directory), self.uid, self.gid)
        except OSError as e:
          if e.errno == 1:
            print "[warning] couldn't change owner of {0}. {1} will likely fail to create own directories.".format(os.path.join(self.data_dir, 'plugins', directory), directory)
          else:
            print "[error] trying to chown plugin directory {0} failed: ".format(os.path.join(self.data_dir, 'plugins', directory)), e
            exit(1)

    # start listening
    if self.ipv6:
      self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    else:
      self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
      print "[SRNd] start listening at {0}:{1}".format(self.ip, self.port)
      self.socket.bind((self.ip, self.port))
    except socket.error as e:
      if e.errno == 13:
        print "[error] current user account does not have CAP_NET_BIND_SERVICE: ", e
        print "        You have three options:"
        print "         - run SRNd as root"
        print "         - assign CAP_NET_BIND_SERVICE to the user you intend to use"
        print "         - use a port > 1024 by setting bind_port at {0}".format(os.path.join(self.data_dir, 'config', 'SRNd.conf'))
        exit(2)
      elif e.errno == 98:
        print "[error] {0}:{1} already in use, change to a different port by setting bind_port at {2}".format(self.ip, self.port, os.path.join(self.data_dir, 'config', 'SRNd.conf'))
        exit(2)
      else:
        raise e
    self.socket.listen(5)

    # create jail
    os.chdir(self.data_dir)

    # reading and starting plugins
    # we need to do this before chrooting because plugins may need to import other libraries
    self.plugins = dict()
    self.update_plugins()

    if self.chroot:
      print "[SRNd] chrooting.."
      try:
        os.chroot('.')
      except OSError as e:
        if e.errno == 1:
          print "[error] current user account does not have CAP_SYS_CHROOT."
          print "        You have three options:"
          print "         - run SRNd as root"
          print "         - assign CAP_SYS_CHROOT to the user you intend to use"
          print "         - disable chroot in {0} by setting chroot=False".format(os.path.join(self.data_dir, 'config', 'SRNd.conf'))
          exit(3)
        else:
          raise e

    if self.setuid != '':
      print "[SRNd] dropping privileges.."
      try:
        os.setgid(self.gid)
        os.setuid(self.uid)
      except OSError as e:
        if e.errno == 1:
          print "[error] current user account does not have CAP_SETUID/CAP_SETGID: ", e
          print "        You have three options:"
          print "         - run SRNd as root"
          print "         - assign CAP_SETUID and CAP_SETGID to the user you intend to use"
          print "         - disable setuid in {0} by setting setuid=".format(os.path.join(self.data_dir, 'config', 'SRNd.conf'))
          exit(4)
        else:
          raise e

    # check for directory structure
    directories = (
        'incoming',
        os.path.join('incoming', 'tmp'),
        'articles',
        os.path.join('articles', 'invalid'),
        os.path.join('articles', 'duplicate'),
        'groups',
        'hooks',
        'stats',
        'plugins')
    for directory in directories:
      if not os.path.exists(directory):
        os.mkdir(directory)
    threading.Thread.__init__(self)
    self.name = "SRNd-listener"
    # FIXME add config var for dropper_debug
    self.dropper = dropper.dropper(self.socket, self, self.dropper_debug)

  def read_and_parse_config(self):
    # read configuration
    # FIXME think about path.. always use data/config/SRNd.conf unless argument states otherwise?
    config_file = os.path.join('data', 'config', 'SRNd.conf')
    if os.path.exists(config_file):
      self.ip = ''
      self.port = 0
      self.hostname = ''
      self.data_dir = ''
      self.chroot = ''
      self.setuid = ''
      self.ipv6 = ''
      self.infeed_debug = -1
      self.dropper_debug = -1
      f = open(config_file, 'r')
      config = f.read()
      f.close()
      lines = config.split('\n')
      for line in lines:
        if len(line) == 0:
          continue
        if line[0] == '#':
          continue
        if not '=' in line:
          print "[SRNd] error: no = in setting '{0}'".format(line)
          continue
        key = line.split('=', 1)[0]
        value = line.split('=', 1)[1]
        #self.config[key] = value
        if key == 'bind_ip':
          self.ip = value
        elif key == 'bind_port':
          try:
            self.port = int(value)
          except ValueError as e:
            self.port = 0
        elif key == 'bind_use_ipv6':
          if value.lower() == 'true':
            self.ipv6 = True
          elif value.lower() == 'false':
            self.ipv6 = False
          else:
            print "[SRNd] bind_user_ipv6: unknown value. only accepting true or false. using default of false"
            self.ipv6 = False
        elif key == 'data_dir':
          self.data_dir = value
        elif key == 'use_chroot':
          if value.lower() == 'true':
            self.chroot = True
          elif value.lower() == 'false':
            self.chroot = False
          else:
            print "[SRNd] use_chroot: unknown value. only accepting true or false. using default of true"
            self.chroot = True
        elif key == 'setuid':
          self.setuid = value
        elif key == 'infeed_debuglevel':
          error = False
          try:
            self.infeed_debug = int(value)
            if self.infeed_debug > 5 or self.infeed_debug < 0:
              error = True
          except ValueError as e:
            error = True
          if error:
            self.infeed_debug = 2
            print "[SRNd] infeed_debuglevel: only accepting integer between 0 and 5. using default of 2"
        elif key == 'dropper_debuglevel':
          error = False
          try:
            self.dropper_debug = int(value)
            if self.dropper_debug > 5 or self.dropper_debug < 0:
              error = True
          except ValueError as e:
            error = True
          if error:
            self.dropper_debug = 2
            print "[SRNd] dropper_debuglevel: only accepting integer between 0 and 5. using default of 2"

      # initialize required variables if currently unset
      if self.ip == '':
        self.ip = ''
        writeConfig = True
      if self.port == 0:
        self.port = 119
        writeConfig = True
      #if self.hostname == '':
      #  self.config = 'some random NNTPd v 0.1'
      #  writeConfig = True
      if self.data_dir == '':
        self.data_dir = 'data'
        writeConfig = True
      if self.ipv6 == '':
        self.ipv6 = False
        writeConfig = True
      if self.infeed_debug == -1:
        self.infeed_debug = 2
        writeConfig = True
      if self.dropper_debug == -1:
        self.dropper_debug = 2
        writeConfig = True
    else:
      # initialize variables with sane defaults
      self.ip = ''
      self.port = 119
      #self.config = 'some random NNTPd v 0.1'
      self.data_dir = 'data'
      self.chroot = True
      self.setuid = 'news'
      self.ipv6 = False
      self.infeed_debug = 2
      self.dropper_debug = 2
      writeConfig = True
    if self.setuid != '':
      try:
        self.uid, self.gid = pwd.getpwnam(self.setuid)[2:4]
      except KeyError as e:
        print "[error] '{0}' is not a valid user on this system.".format(self.setuid)
        print "[error] either create {0} or change setuid at '{1}' into a valid username or an empty value to disable setuid".format(self.setuid, config_file)
        exit(1)
    else:
      if self.chroot:
        print "[error] You defined use_chroot=True and set setuid to an empty value."
        print "[error] This would result in chrooting without dropping privileges which defeats the purpose of chrooting completely."
        exit(3)
    if writeConfig:
      configPath = os.path.join(self.data_dir, 'config')
      if not os.path.exists(configPath):
        os.makedirs(configPath)
        if self.setuid != '':
          try:
            os.chown(self.data_dir, self.uid, self.gid)
            os.chown(configPath, self.uid, self.gid)
          except OSError as e:
            if e.errno == 1:
              print "[warning] can't change ownership of newly generated data directory."
              print "[warning] If you don't intend to run SRNd as root and let it chroot and setuid/gid itself (which is the recommend way to run SRNd), you"
              print "[warning] need to modify the configuration file at {0} and set setuid to an empty value.".format(os.path.join(self.data_dir, 'config', 'SRNd.conf'))
              print "[warning] If you want to run as root delete the data directory before you restart SRNd."
            else:
              print "[error] trying to chown configuration files failed: ", e
              exit(1)
      f = open(os.path.join(configPath, 'SRNd.conf'), 'w')
      f.write('# changing this file requires a restart of SRNd\n')
      f.write('# empty lines or lines starting with # are ignored\n')
      f.write('# do not add whitespaces before or after =\n')
      f.write('# additional data in this file will be overwritten every time a value has been changed\n')
      f.write('\n')
      f.write('bind_ip={0}\n'.format(self.ip))
      f.write('bind_port={0}\n'.format(self.port))
      f.write('bind_use_ipv6={0}\n'.format(self.ipv6))
      f.write('data_dir={0}\n'.format(self.data_dir))
      f.write('use_chroot={0}\n'.format(self.chroot))
      f.write('setuid={0}\n'.format(self.setuid))
      f.write('infeed_debuglevel={0}\n'.format(self.infeed_debug))
      f.write('dropper_debuglevel={0}\n'.format(self.dropper_debug))
      f.close()

  def update_hooks(self):
    print "[SRNd] reading hook configuration.."
    self.hooks = dict()
    self.hook_blacklist = dict()
    total = 0
    for hook_type in ('filesystem', 'outfeeds', 'plugins'):
      directory = os.path.join('config', 'hooks', hook_type)
      found = 0
      for hook in os.listdir(directory):
        link = os.path.join(directory, hook)
        if not os.path.isfile(link):
          continue
        # FIXME ignore new plugin hooks after startup, needs a boolean somewhere
        # FIXME if hook_type == "plugins" and "plugin-{0}".format(hook) not in self.
        # read hooks into self.hooks[group_name] = hook_name
        f = open(link, 'r')
        line = f.readline()
        while line != "":
          if len(line) == 1:
            line = f.readline()
            continue
          if line[0] == '#':
            line = f.readline()
            continue
          line = line[:-1]
          if line[0] == '!':
            # blacklist
            line = line[1:]
            if line[0] == '*':
              print "[SRNd] invalid blacklist rule: !* is not allowed. everything not whitelisted will be rejected automatically."
              line = f.readline()
              continue
            if not line in self.hook_blacklist:
              self.hook_blacklist[line] = list()
            name = '{0}-{1}'.format(hook_type, hook)
            if not name in self.hook_blacklist[line]:
              self.hook_blacklist[line].append(name)
              found += 1
          else:
            # whitelist
            if not line in self.hooks:
              self.hooks[line] = list()
            name = '{0}-{1}'.format(hook_type, hook)
            if not name in self.hooks[line]:
              self.hooks[line].append(name)
              found += 1
          line = f.readline()
        f.close()
        if hook_type == 'filesystem':
          # create hook directory
          hook_dir = os.path.join('hooks', hook)
          if not os.path.exists(hook_dir):
            os.mkdir(hook_dir)
            os.chmod(hook_dir, 0o777)
      total += found
    #if not '*' in self.hooks:
    #  self.hooks['*'] = list()
    if total > 0:
      print "[SRNd] found {0} hooks:".format(total)
      print "whitelist"
      for pattern in self.hooks:
        print ' ' + pattern
        for hook in self.hooks[pattern]:
          print '   ' + hook
      print "blacklist"
      for pattern in self.hook_blacklist:
        print ' ' + pattern
        for hook in self.hook_blacklist[pattern]:
          print '   ' + hook
    else:
      print "[SRNd] did not find any hook"

  def update_plugins(self):
    print "[SRNd] importing plugins.."
    new_plugins = list()
    current_plugin = None
    for plugin in os.listdir(os.path.join('config', 'hooks', 'plugins')):
      link = os.path.join('config', 'hooks', 'plugins', plugin)
      if os.path.isfile(link):
        plugin_path = os.path.join('plugins', plugin)
        if not plugin_path in sys.path:
          sys.path.append(plugin_path)
        name = 'plugin-' + plugin
        if name in self.plugins:
          continue
        args = dict()
        f = open(link, 'r')
        line = f.readline()
        while line != "":
          if len(line) == 1:
            line = f.readline()
            continue
          if line.startswith('#start_param '):
            line = line[13:-1]
            key = line.split('=', 1)[0]
            args[key] = line.split('=', 1)[1]
          line = f.readline()
        f.close()
        #print "[SRNd] trying to import {0}..".format(name)
        try:
          current_plugin = __import__(plugin)
          self.plugins[name] = current_plugin.main(name, args)
          new_plugins.append(name)
        except Exception as e:
          print "[SRNd] error while importing {0}: {1}".format(name, e)
          if name in self.plugins:
            del self.plugins[name]
          continue
    del current_plugin
    print "[SRNd] added {0} new plugins".format(len(new_plugins))
    # TODO: stop and remove plugins not listed at config/plugins anymore

  def update_outfeeds(self):
    print "[SRNd] reading outfeeds.."
    counter_new = 0
    current_feedlist = list()
    for outfeed in os.listdir(os.path.join('config', 'hooks', 'outfeeds')):
      if os.path.isfile(os.path.join('config', 'hooks', 'outfeeds', outfeed)):
        if ':' in outfeed:
          host = ':'.join(outfeed.split(':')[:-1])
          port = int(outfeed.split(':')[-1])
        else:
          # FIXME: how to deal with ipv6 and no default port?
          host = outfeed
          port = 119
        name = "outfeed-{0}-{1}".format(host, port)
        current_feedlist.append(name)
        if name not in self.feeds:
          self.feeds[name] = feed.feed(self, outstream=True, host=host, port=port, debug=2)
          self.feeds[name].start()
          counter_new += 1
    counter_removed = 0
    feeds = list()
    for name in self.feeds:
      if name.startswith('outfeed'):
        feeds.append(name)
    for name in feeds:
      if not name in current_feedlist and name in self.feeds:
        self.feeds[name].shutdown()
        counter_removed += 1
    print "[SRNd] outfeeds added: {0}".format(counter_new)
    print "[SRNd] outfeeds removed: {0}".format(counter_removed)

  def update_hooks_outfeeds_plugins(self, signum, frame):
    self.update_outfeeds()
    self.update_plugins()
    self.update_hooks()

  def run(self):
    self.running = True
    self.feeds = dict()
    self.update_outfeeds()
    if len(self.plugins) > 0:
      print "[SRNd] starting plugins.."
      for plugin in self.plugins:
        self.plugins[plugin].start()
      time.sleep(0.1)
    self.update_hooks()

    #  self.feeds[name].start()
    print
    #files = filter(os.path.isfile, os.listdir('articles'))
    files = filter(lambda f: os.path.isfile(os.path.join('articles', f)), os.listdir('articles'))
    files.sort(key=lambda f: os.path.getmtime(os.path.join('articles', f)))
    for name in self.feeds:
      if name.startswith('outfeed'):
        for item in files:
          self.feeds[name].add_article(item)

    self.dropper.start()
    while self.running:
      try:
        con = self.socket.accept()
        name = 'infeed-{0}-{1}'.format(con[1][0], con[1][1])
        if name not in self.feeds:
          if con[1][0] != '127.0.0.1':
            self.feeds[name] = feed.feed(self, connection=con, debug=self.infeed_debug)
          else:
            self.feeds[name] = feed.feed(self, connection=con, debug=self.infeed_debug)
          self.feeds[name].start()
        else:
          print "[SRNd] got connection from {0} but its still in feeds. wtf?".format(name)
      except socket.error as e:
        if e.errno == 22:
          break
        elif e.errno == 4:
          # system call interrupted
          continue
        else:
          raise e
    self.socket.close()

  def terminate_feed(self, name):
    if name in self.feeds:
      del self.feeds[name]
    else:
      print "[SRNd] should remove {0} but not in dict. wtf?".format(name)

  def relay_dropper_handler(self, signum, frame):
    #print "[relay_handler]"
    #print "signum: ", signum
    #print "frame: ", frame
    self.dropper.handler_progress_incoming(signum, frame)

  def watching(self):
    return self.dropper.watching

  def shutdown(self):
    self.dropper.running = False
    self.running = False
    print "[SRNd] closing listener.."
    self.socket.shutdown(socket.SHUT_RDWR)
    print "[SRNd] closing plugins.."
    for plugin in self.plugins:
      self.plugins[plugin].shutdown()
    print "[SRNd] closing feeds.."
    feeds = list()
    for name in self.feeds:
      feeds.append(name)
    for name in feeds:
      if name in self.feeds:
        self.feeds[name].shutdown()
    print "[SRNd] waiting for feeds to shut down.."
