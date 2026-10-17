#!/usr/bin/env python
# License: GPL v3

from calibre.customize import InterfaceActionBase


class MoonSyncPlugin(InterfaceActionBase):
    name = 'Moon+ Reader Sync'
    description = ('Share reading positions between Moon+ Reader (via its '
                   'synced .po files) and the calibre e-book viewer')
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Spagoodlers'
    version = (0, 4, 0)
    minimum_calibre_version = (6, 0, 0)
    actual_plugin = 'calibre_plugins.moonsync.ui:MoonSyncAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.moonsync.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
        ac = self.actual_plugin_
        if ac is not None:
            ac.settings_changed()
