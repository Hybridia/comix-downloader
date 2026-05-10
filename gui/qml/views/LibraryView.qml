import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: libraryView

    readonly property color bgCard: "#1C1C24"
    readonly property color textPrimary: "#F5F5F0"
    readonly property color textSecondary: "#8B8B99"
    readonly property color textTertiary: "#5C5C66"
    readonly property color accentPrimary: "#E8A54B"

    property var entries: []
    property string busyUrl: ""
    property var statusByUrl: ({})  // source_url -> status string

    function refresh() {
        entries = LibraryBridge.listEntries()
        entryModel.clear()
        for (var i = 0; i < entries.length; i++) {
            entryModel.append({"source_url": entries[i].source_url})
        }
    }

    function entryFor(url) {
        for (var i = 0; i < entries.length; i++) {
            if (entries[i].source_url === url) return entries[i]
        }
        return null
    }

    function setStatus(url, msg) {
        var copy = {}
        for (var k in statusByUrl) copy[k] = statusByUrl[k]
        if (msg) {
            copy[url] = msg
        } else {
            delete copy[url]
        }
        statusByUrl = copy
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        // HEADER
        RowLayout {
            Layout.fillWidth: true

            ColumnLayout {
                spacing: 4
                Text {
                    text: "LIBRARY"
                    font.family: "Segoe UI"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: textPrimary
                }
                Text {
                    text: "Everything you've downloaded — re-fetch any of them to grab new chapters"
                    font.pixelSize: 13
                    color: textSecondary
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Refresh List"
                onClicked: libraryView.refresh()
            }
        }

        // EMPTY STATE
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: bgCard
            radius: 12
            visible: entryModel.count === 0

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 12

                Text {
                    text: "📚"
                    font.pixelSize: 48
                    color: textTertiary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "Your library is empty"
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    color: textPrimary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "Download a manga from the Browse tab to add it here."
                    font.pixelSize: 13
                    color: textSecondary
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "The Browse tab lists every site you can paste a URL from."
                    font.pixelSize: 11
                    color: textTertiary
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }

        // ENTRY LIST
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: entryModel.count > 0
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 10

                Repeater {
                    model: ListModel { id: entryModel }

                    LibraryCard {
                        entry: libraryView.entryFor(model.source_url)
                        statusMessage: libraryView.statusByUrl[model.source_url] || ""
                        busy: libraryView.busyUrl === model.source_url

                        onUpdateRequested: {
                            libraryView.busyUrl = model.source_url
                            libraryView.setStatus(model.source_url,
                                                  "Checking for new chapters…")
                            LibraryBridge.updateEntry(model.source_url)
                        }
                        onRemoveRequested: {
                            LibraryBridge.removeEntry(model.source_url)
                        }
                        onOpenFolderRequested: {
                            LibraryBridge.openFolder(model.source_url)
                        }
                    }
                }
            }
        }
    }

    // BRIDGE SIGNALS
    Connections {
        target: LibraryBridge

        function onEntriesChanged() {
            libraryView.refresh()
        }
        function onUpdateStarted(url, title, count) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url,
                "Downloading " + count + " new chapter" + (count === 1 ? "" : "s") + "…")
        }
        function onNoUpdatesAvailable(url, title) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url, "Up to date")
        }
        function onUpdateFailed(url, error) {
            libraryView.busyUrl = ""
            libraryView.setStatus(url, "Update failed: " + error)
        }
    }

    // Refresh whenever a download finishes — that's when the library
    // grows or its chapter count changes.
    Connections {
        target: DownloadBridge
        function onDownloadFinished(jobId, successful, failed) {
            libraryView.refresh()
        }
    }
}
