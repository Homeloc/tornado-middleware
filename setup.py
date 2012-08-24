#!/usr/bin/env python

import os

from setuptools import setup

setup(
    name             = 'tornado_middleware',
    version          = '0.1.1',
    description      = 'A Pluggable Middleware Request class for Tornado.',
    author           = 'The Homeloc Team !',
    author_email     = 'contact@homeloc.com',
    url              = 'www.homeloc.com/',
    packages         = ['tornado_middleware'],
    install_requires = ['tornado']
)
