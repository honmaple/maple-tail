#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ********************************************************************************
# Copyright © 2018 honmaple
# File Name: log.py
# Author: honmaple
# Email: xiyang0807@gmail.com
# Created: 2018-03-26 17:49:35 (CST)
# Last Update: Thursday 2018-04-12 10:31:23 (CST)
#          By:
# Description:
# ********************************************************************************
from tornado.websocket import WebSocketHandler
from tornado.escape import json_decode
from tornado import ioloop
from tornado.web import Application, RequestHandler
from tornado.template import Template
from tornado.options import (define, options, parse_command_line)
import os
import sys

TEMPLATE = Template('''\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <title>Tail Logs</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
  </head>
  <body>
    {% if not logs %}
    file is not exist
    {% else %}
        <ul>
        {% for log in logs %}
        <li><a href="{{ log }}">{{ log }}</a></li>
        {% end %}
        </ul>
    {% end %}
  </body>
</html>
''')

TAIL_TEMPLATE = Template('''\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <title>Ansible</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.bootcss.com/jquery/2.1.4/jquery.min.js"></script>
    <script type="text/javascript">
     $(function() {
         console.log(window.location.href)
         if ("MozWebSocket" in window) {
             WebSocket = MozWebSocket;
         }
         if (WebSocket) {
             var ws = new WebSocket("ws://127.0.0.1:{{ port }}/tail/" + "{{ name }}");
             ws.onopen = function() {};
             ws.onmessage = function (evt) {
                 console.log(evt.data)
                 $("#log").append(evt.data + "<br/>")
             };
             ws.onclose = function() {
                 console.log("close")
             };
         } else {
             alert("WebSocket not supported");
         }
     })
    </script>
    <style>
     #log {
         max-width:800px;
         width: 100%;
         margin:0 auto;
     }
    </style>
  </head>
  <body>
    <div id="log"></div>
  </body>
</html>
''')


def import_string(import_name):
    try:
        __import__(import_name)
    except ImportError:
        if '.' not in import_name:
            raise
    else:
        return sys.modules[import_name]

    module_name, obj_name = import_name.rsplit('.', 1)
    try:
        module = __import__(module_name, None, None, [obj_name])
    except ImportError:
        # support importing modules not yet set up by the parent module
        # (or package for that matter)
        module = import_string(module_name)

    try:
        return getattr(module, obj_name)
    except AttributeError as e:
        raise ImportError(e)


def is_log(path):
    if os.path.exists(path):
        return os.path.isfile(path) and path.endswith(".log")
    return False


def is_dir(path):
    return os.path.exists(path) and os.path.isdir(path)


class HomeHandler(RequestHandler):
    def get(self):
        logs = self.settings['tail_logs']
        self.write(TEMPLATE.generate(logs=logs))


class LogHandler(RequestHandler):
    def get(self, name):
        logs = []
        path = os.path.join(self.settings['tail_path'], name)
        if is_log(path):
            return self.write(
                TAIL_TEMPLATE.generate(
                    name=name, port=options.port))
        elif is_dir(path):
            logs = ["{0}/{1}".format(name, i) for i in os.listdir(path)
                    if is_log(path) or is_dir(path)]
        return self.write(TEMPLATE.generate(logs=logs))


class TailHandler(WebSocketHandler):
    def _run_callback(self, f, *a, **kw):
        def wrapper():
            try:
                f(*a, **kw)
            except Exception as e:
                print(e)

        return super()._run_callback(wrapper)

    def check_origin(self, origin):
        return True

    def open(self, filename='default'):
        print("WebSocket opened")
        self.filename = os.path.join(self.settings['tail_path'], filename)
        if is_log(self.filename):
            tail.listeners.setdefault(self.filename, [])
            tail.listeners[self.filename].append(self)
        else:
            self.write_message('file is not exist')

    def on_message(self, message):
        msg = json_decode(message)
        print(msg)

    def on_close(self):
        print("WebSocket closed")
        if self in tail.listeners[self.filename]:
            tail.listeners[self.filename].remove(self)
        if not tail.listeners[self.filename]:
            tail.listeners.pop(self.filename, None)


class Tail(object):
    def __init__(self):
        self.listeners = {}
        self.log_files = {}

    def __call__(self):
        '''
        tail all log file
        '''
        for name in self.listeners:
            self.tail(name)

    def tail(self, name):
        if name not in self.log_files:
            self.log_files[name] = open(name)
            self.log_files[name].seek(os.path.getsize(name))
        where = self.log_files[name].tell()
        line = self.log_files[name].readline()
        if not line:
            self.log_files[name].seek(where)
        elif name in self.listeners:
            for listener in self.listeners[name]:
                listener.write_message(line)


def create_app(settings={}):
    handlers = [(r'/', HomeHandler),
                (r'/tail/(.*)', TailHandler),
                (r'/(.*)', LogHandler), ]
    settings.update(**{'handlers': handlers})
    app = Application(**settings)
    return app


define("config", default="config", help="release config")
define("port", default=8001, help="release port")
parse_command_line()

settings = import_string(options.config)
tail = Tail()
app = create_app({
    "tail_path": settings.TAIL_PATH,
    'tail_logs': settings.TAIL_LOGS,
    "debug": settings.DEBUG
})
app.listen(options.port)
if __name__ == '__main__':
    ioloop.PeriodicCallback(tail, 5).start()
    io_loop = ioloop.IOLoop.current()
    # io_loop = ioloop.IOLoop.instance()
    try:
        io_loop.start()
    except SystemExit as KeyboardInterrupt:
        io_loop.stop()
        for name, f in tail.log_files.items():
            f.close()
