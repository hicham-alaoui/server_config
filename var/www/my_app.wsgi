#! /usr/bin/python
import sys
import logging
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0,"/var/www/my_app/")

# project points to the project.py file
from project import app as application
application.secret_key = "somesecretsessionkey"
