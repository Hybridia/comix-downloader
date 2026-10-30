import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../fx"
import "../logic/motion.js" as Motion

// Copy to iCloud: chapters waiting in ./downloads that aren't in the
// series' iCloud folder yet (IcloudBridge, logic in src/utils/icloud_push.py).
//
// Copies, never moves — the downloads files stay. Nothing is ticked until
// the user picks series (all their chapters) or single chapters.
// Selection lives in `sel` (row key → {numbers: true}); `selVersion` is
// bumped on every change because bindings don't see inside a JS object.
Item {
    id: icloudView

    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color accentPrimary: Theme.accent
    readonly property color borderColor: Theme.border

    property var rows: []
    property var sel: ({})
    property int selVersion: 0
    property bool scanning: false
    property bool copying: false
    property int copyDone: 0
    property int copyTotal: 0
    property string copyName: ""
    // After copying: waiting for macOS to upload the copies to iCloud.
    property bool uploading: false
    property int uploadDone: 0
    property int uploadTotal: 0
    property int uploadActive: 0      // macOS is sending these right now
    property int uploadRetrying: 0    // iCloud reported an error and retries by itself
    property string uploadReason: ""
    property real uploadBytes: 0
    property real uploadBytesTotal: 0
    property string summary: ""
    readonly property int selectedCount: (selVersion, countSelected())

    function refresh() {
        scanning = true
        IcloudBridge.scan()
    }

    function rowByKey(key) {
        for (var i = 0; i < rows.length; i++) if (rows[i].key === key) return rows[i]
        return null
    }

    function picked(key) { return sel[key] || {} }

    function toggleRow(key) {
        var r = rowByKey(key)
        if (!r) return
        if (Object.keys(picked(key)).length > 0) delete sel[key]
        else {
            var all = {}
            for (var i = 0; i < r.chapters.length; i++) all[r.chapters[i].number] = true
            sel[key] = all
        }
        selVersion++
    }

    function toggleChapter(key, number) {
        var p = sel[key] || {}
        if (p[number]) delete p[number]
        else p[number] = true
        if (Object.keys(p).length > 0) sel[key] = p
        else delete sel[key]
        selVersion++
    }

    function setAll(on) {
        var next = {}
        if (on) {
            for (var i = 0; i < rows.length; i++) {
                var all = {}
                for (var j = 0; j < rows[i].chapters.length; j++) all[rows[i].chapters[j].number] = true
                next[rows[i].key] = all
            }
        }
        sel = next
        selVersion++
    }

    function countSelected() {
        var n = 0
        for (var key in sel) n += Object.keys(sel[key]).length
        return n
    }

    function copySelected() {
        var items = []
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i], p = picked(r.key), paths = []
            for (var j = 0; j < r.chapters.length; j++)
                if (p[r.chapters[j].number]) paths.push(r.chapters[j].path)
            if (paths.length) items.push({ key: r.key, paths: paths })
        }
        if (!items.length) return
        copying = true
        copyDone = 0
        copyTotal = countSelected()
        uploading = false
        uploadDone = 0
        uploadTotal = 0
        uploadActive = 0
        uploadRetrying = 0
        uploadReason = ""
        summary = ""
        IcloudBridge.copy(items)
    }

    function fmtSize(b) {
        return b >= 1e9 ? (b / 1e9).toFixed(1) + " GB" : Math.max(1, Math.round(b / 1e6)) + " MB"
    }

    function rowSize(r) {
        var b = 0
        for (var i = 0; i < r.chapters.length; i++) b += r.chapters[i].size
        return b
    }

    Connections {
        target: IcloudBridge
        function onPendingReady(list) {
            icloudView.rows = list
            icloudView.scanning = false
            var next = {}
            for (var i = 0; i < list.length; i++) {
                var p = icloudView.sel[list[i].key]
                if (!p) continue
                var keep = {}
                for (var j = 0; j < list[i].chapters.length; j++)
                    if (p[list[i].chapters[j].number]) keep[list[i].chapters[j].number] = true
                if (Object.keys(keep).length) next[list[i].key] = keep
            }
            icloudView.sel = next
            icloudView.selVersion++
        }
        function onCopyProgress(done, total, name) {
            icloudView.copyDone = done
            icloudView.copyTotal = total
            icloudView.copyName = name
        }
        function onUploadProgress(s) {
            icloudView.uploading = true
            icloudView.uploadDone = s.uploaded
            icloudView.uploadTotal = s.total
            icloudView.uploadActive = s.uploading
            icloudView.uploadRetrying = s.retrying
            icloudView.uploadReason = s.reason
            icloudView.uploadBytes = s.done_bytes
            icloudView.uploadBytesTotal = s.total_bytes
        }
        function onCopyFinished(result) {
            icloudView.copying = false
            icloudView.uploading = false
            icloudView.summary = result.message
            icloudView.sel = ({})
            icloudView.selVersion++
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 32
        spacing: 16

        // ── Header ───────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Text {
                    text: "Copy to iCloud"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: textPrimary
                }
                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Chapters in your download folder that aren't in the series' iCloud Manga folder yet. "
                          + "Copying puts them in that folder (a new folder for a new series); chapters already "
                          + "there are never overwritten, and the downloads copies stay."
                    font.pixelSize: 13
                    color: textSecondary
                }
            }

            FxButton {
                id: copyBtn
                objectName: "icloudCopyBtn"
                Layout.preferredHeight: 34
                Layout.preferredWidth: implicitWidth + 30
                enabled: icloudView.selectedCount > 0 && !icloudView.copying
                fontSize: 12
                text: icloudView.selectedCount > 0
                      ? "☁ Copy " + icloudView.selectedCount + " chapter" + (icloudView.selectedCount === 1 ? "" : "s") + " to iCloud"
                      : "☁ Copy to iCloud"
                onClicked: icloudView.copySelected()
            }
        }

        // ── Progress / summary banner ────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            visible: icloudView.copying || icloudView.summary.length > 0
            radius: 8
            color: bgCard
            border.width: 1
            border.color: icloudView.copying ? accentPrimary : Theme.success

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                spacing: 10
                BusyIndicator {
                    visible: icloudView.copying
                    running: icloudView.copying
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    palette.dark: accentPrimary
                }
                Text {
                    visible: !icloudView.copying
                    text: "✓"
                    font.pixelSize: 16
                    color: Theme.success
                }
                Text {
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    font.pixelSize: 13
                    color: textPrimary
                    text: icloudView.uploading
                          ? ("Uploading to iCloud — " + icloudView.uploadDone + " of " + icloudView.uploadTotal
                             + " in iCloud"
                             + (icloudView.uploadBytesTotal > 0
                                ? " (" + (icloudView.uploadBytes / 1e6).toFixed(1) + " of "
                                  + (icloudView.uploadBytesTotal / 1e6).toFixed(1) + " MB)" : "")
                             + (icloudView.uploadActive ? " · ⬆ " + icloudView.uploadActive + " uploading" : "")
                             + (icloudView.uploadRetrying ? " · ↻ iCloud retrying " + icloudView.uploadRetrying : "")
                             + ". Keep the downloads copies until this is done.")
                          : icloudView.copying
                          ? ("Copying " + icloudView.copyDone + " of " + icloudView.copyTotal
                             + (icloudView.copyName ? ": " + icloudView.copyName : ""))
                          : icloudView.summary
                }
                Text {
                    visible: !icloudView.copying
                    text: "✕"
                    color: textSecondary
                    font.pixelSize: 14
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: icloudView.summary = ""
                    }
                }
            }
        }

        // Progress: blue = copied into the iCloud folder, green = uploaded to iCloud.
        Rectangle {
            id: bar
            objectName: "icloudProgress"
            Layout.fillWidth: true
            Layout.preferredHeight: 8
            visible: icloudView.copying
            radius: 4
            color: bgElevated
            clip: true
            readonly property real copiedFrac: icloudView.uploading ? 1
                : (icloudView.copyTotal ? icloudView.copyDone / icloudView.copyTotal : 0)
            // green follows the bytes (like Finder), falling back to whole files
            readonly property real upFrac: icloudView.uploadBytesTotal > 0
                ? icloudView.uploadBytes / icloudView.uploadBytesTotal
                : (icloudView.uploadTotal ? icloudView.uploadDone / icloudView.uploadTotal : 0)
            Rectangle {
                height: parent.height
                radius: 4
                color: Qt.lighter(Theme.accent, 1.1)
                opacity: 0.55
                width: parent.width * bar.copiedFrac
                Behavior on width { NumberAnimation { duration: Theme.dur(500); easing.type: Easing.OutCubic } }
                SequentialAnimation on opacity {
                    running: icloudView.copying && Theme.animations
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.85; duration: Theme.dur(700) }
                    NumberAnimation { to: 0.45; duration: Theme.dur(700) }
                }
            }
            Rectangle {
                height: parent.height
                radius: 4
                color: Theme.success
                width: parent.width * bar.upFrac
                Behavior on width { NumberAnimation { duration: Theme.dur(600); easing.type: Easing.OutCubic } }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: icloudView.uploading && icloudView.uploadReason.length > 0
            wrapMode: Text.WordWrap
            font.pixelSize: 12
            color: Theme.warning
            text: "iCloud says “" + icloudView.uploadReason + "” — it keeps retrying by itself, nothing is lost."
        }

        // ── Toolbar ──────────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            visible: icloudView.rows.length > 0
            spacing: 16
            Text {
                text: {
                    var n = 0
                    for (var i = 0; i < icloudView.rows.length; i++) n += icloudView.rows[i].chapters.length
                    return icloudView.rows.length + " series · " + n + " chapters not in iCloud yet"
                }
                font.pixelSize: 12
                color: textSecondary
            }
            Text {
                text: "Select all"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: icloudView.setAll(true) }
            }
            Text {
                text: "Select none"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: icloudView.setAll(false) }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "↻ Rescan"
                font.pixelSize: 12
                color: accentPrimary
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: icloudView.refresh() }
            }
        }

        // ── Empty state ──────────────────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: icloudView.rows.length === 0
            spacing: 8
            Item { Layout.fillHeight: true; Layout.fillWidth: true }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "☁️"
                font.pixelSize: 40
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: icloudView.scanning ? "Looking at your download folder…" : "Everything is in iCloud"
                font.pixelSize: 16
                font.weight: Font.DemiBold
                color: textPrimary
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                visible: !icloudView.scanning
                text: "Chapters you download show up here until they're in the series' iCloud folder."
                font.pixelSize: 13
                color: textSecondary
            }
            Item { Layout.fillHeight: true }
        }

        // ── Series list ──────────────────────────────────────────────
        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: icloudView.rows.length > 0
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: scroller.availableWidth
                spacing: 10

                Repeater {
                    model: icloudView.rows

                    delegate: Rectangle {
                        id: card
                        required property var modelData
                        required property int index
                        readonly property var row: modelData
                        readonly property var p: (icloudView.selVersion, icloudView.picked(row.key))
                        readonly property int nPicked: Object.keys(p).length
                        transform: Translate { id: cardShift }
                        Component.onCompleted: if (Theme.animations && index < 16) cardIn.start()
                        SequentialAnimation {
                            id: cardIn
                            PropertyAction { target: cardShift; property: "y"; value: 18 }
                            PauseAnimation { duration: Motion.staggerDelay(card.index) }
                            NumberAnimation { target: cardShift; property: "y"; to: 0; duration: Theme.dur(450); easing.type: Easing.OutQuint }
                        }

                        Layout.fillWidth: true
                        implicitHeight: body.implicitHeight + 28
                        radius: 10
                        color: bgCard
                        border.width: 1
                        border.color: nPicked > 0 ? Qt.darker(accentPrimary, 1.6) : borderColor

                        RowLayout {
                            id: body
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 14
                            spacing: 14

                            Rectangle {
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 2
                                width: 20; height: 20; radius: 4
                                color: card.nPicked > 0 ? accentPrimary : "transparent"
                                border.width: 1
                                border.color: card.nPicked > 0 ? accentPrimary : textTertiary
                                Text {
                                    anchors.centerIn: parent
                                    visible: card.nPicked > 0
                                    text: card.nPicked === card.row.chapters.length ? "✓" : "–"
                                    color: Theme.surface
                                    font.pixelSize: 13
                                    font.weight: Font.Bold
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: icloudView.toggleRow(card.row.key)
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                Text {
                                    Layout.fillWidth: true
                                    text: card.row.title
                                    elide: Text.ElideRight
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    color: textPrimary
                                }
                                Text {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    font.pixelSize: 12
                                    color: textSecondary
                                    text: card.row.chapters.length + " chapter" + (card.row.chapters.length === 1 ? "" : "s")
                                          + " (" + icloudView.fmtSize(icloudView.rowSize(card.row)) + ")  →  "
                                          + (card.row.target_exists ? "" : "new folder ") + "iCloud / " + card.row.target
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Repeater {
                                        model: card.row.chapters
                                        delegate: Rectangle {
                                            id: chip
                                            required property var modelData
                                            readonly property bool on: (icloudView.selVersion, !!card.p[modelData.number])
                                            height: 24
                                            width: chipText.implicitWidth + 18
                                            radius: 12
                                            color: on ? Qt.darker(accentPrimary, 2.2) : "transparent"
                                            border.width: 1
                                            border.color: on ? accentPrimary : borderColor
                                            Behavior on color { ColorAnimation { duration: Theme.dur(150) } }
                                            Text {
                                                id: chipText
                                                anchors.centerIn: parent
                                                text: (chip.on ? "✓ " : "") + "Ch " + chip.modelData.number
                                                font.pixelSize: 11
                                                color: chip.on ? accentPrimary : textSecondary
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: icloudView.toggleChapter(card.row.key, chip.modelData.number)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
