""" CollectorError is a user-defined exception for handilg run-time
errors in the data collector.

Typical usage:
try:
  containers_list = requests.get(url).json()
except:
  msg = 'fetching %s failed with exception %s' % (url, sys.exc_info()[0])
  current_app.logger.exception(msg)
  raise CollectorError(s)
"""

import types

class CollectorError(Exception):

  def __init__(self, message):
    assert isinstance(message, types.StringTypes)
    self._message = message

  def __str__(self):
    return repr(self._message)
