#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Snippet to instantiate the status page app from somewhere else
"""
from flask import Flask
from webservice.flaskws import status_page

app = Flask(__name__)
app.register_blueprint(status_page)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
