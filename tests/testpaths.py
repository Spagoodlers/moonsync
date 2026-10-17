'''Where the test scripts find your data: the paths given on the command line,
or else the library calibre last opened and the folder set in the plugin's
settings.'''
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def library():
    if len(sys.argv) > 1:
        return sys.argv[1]
    from calibre.utils.config import prefs
    return prefs['library_path']


def moon_folder():
    if len(sys.argv) > 2:
        return sys.argv[2]
    from moonsync.config import default_folder, prefs
    return prefs['folder'] or default_folder()
