def classFactory(iface):
    from .spotter_plugin import SpotterPlugin
    return SpotterPlugin(iface)
