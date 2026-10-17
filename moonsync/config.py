#!/usr/bin/env python
# License: GPL v3

import os

from qt.core import QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/moonsync')
prefs.defaults['folder'] = ''
prefs.defaults['open_all'] = True
prefs.defaults['save_all'] = True
prefs.defaults['create_missing'] = True


def default_folder():
    # Moon+ Pro's Dropbox sync location
    home = os.path.expanduser('~')
    for base in (os.path.join(home, 'Dropbox'), os.path.join(home, 'Documents', 'Dropbox')):
        guess = os.path.join(base, 'Apps', 'Books', '.Moon+', 'Cache')
        if os.path.isdir(guess):
            return guess
    return ''


class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        l = QVBoxLayout(self)
        l.addWidget(QLabel(
            'Folder containing Moon+ Reader position files (*.po). With Moon+ '
            'Dropbox sync this is <code>Apps/Books/.Moon+/Cache</code> inside your Dropbox.'))
        row = QHBoxLayout()
        self.folder = QLineEdit(prefs['folder'] or default_folder())
        row.addWidget(self.folder)
        b = QPushButton('&Browse...')
        b.clicked.connect(self.browse)
        row.addWidget(b)
        l.addLayout(row)
        self.open_all = QCheckBox('Always &open books at their Moon+ position (when it is newer than calibre\'s)')
        self.open_all.setToolTip('Applies however a book is opened: double click, the View button, etc.')
        self.open_all.setChecked(prefs['open_all'])
        l.addWidget(self.open_all)
        self.save_all = QCheckBox('Always &save the calibre viewer position to Moon+')
        self.save_all.setToolTip('Written whenever the viewer saves your position, including when it closes.\n'
                                 'Works for any book opened while calibre is running.')
        self.save_all.setChecked(prefs['save_all'])
        l.addWidget(self.save_all)
        self.create_missing = QCheckBox('&Create Moon+ position files for books that do not have one yet')
        self.create_missing.setChecked(prefs['create_missing'])
        l.addWidget(self.create_missing)
        l.addStretch()

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, 'Choose Moon+ position folder', self.folder.text())
        if d:
            self.folder.setText(os.path.normpath(d))

    def save_settings(self):
        prefs['folder'] = self.folder.text().strip()
        prefs['open_all'] = self.open_all.isChecked()
        prefs['save_all'] = self.save_all.isChecked()
        prefs['create_missing'] = self.create_missing.isChecked()
