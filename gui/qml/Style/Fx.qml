pragma Singleton
import QtQuick

// App-wide effect bus. Components ask for effects here; hosts living in
// main.qml (ToastHost, the fly-to bubble, ThemeWipe) perform them.
QtObject {
    signal toastRequested(string text, string kind)
    signal flyRequested(point from, int count)
    signal themeWipeRequested(string name, point origin)

    function toast(text, kind) { toastRequested(text, kind || "info") }
}
