import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import "../logic/chapters.js" as Chapters
import "../logic/motion.js" as Motion

Rectangle {
    id: root
    objectName: "chapterList"
    
    ListModel { id: chapterModel }
    
    property var allChapters: []  // Store original list for filtering
    property string currentFilter: "Any"   // scanlator filter
    property string textFilter: ""         // number / title search
    // Rows currently shown (pass both filters).
    property int visibleCount: 0
    // Shift-click anchor (model index), -1 = none yet.
    property int anchorIndex: -1
    // Delegates created within this window after a load play the
    // staggered entrance; ones created later by scrolling don't.
    property real loadedAt: 0
    
    // Explicit selection counter. QML's binding system doesn't fire
    // change signals on in-place mutations of a `property var` array
    // (allChapters[i].selected = true …), so we update this manually
    // from every toggle path.
    property int selectedCount: 0
    function recountSelected() {
        var n = 0
        for (var i = 0; i < allChapters.length; i++) {
            if (allChapters[i].selected) n++
        }
        selectedCount = n
    }
    
    // Theme colors
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    
    color: bgCard
    radius: 12
    border.color: Theme.border
    
    function setChapters(chapterList) {
        allChapters = chapterList
        anchorIndex = -1
        loadedAt = Date.now()
        applyFilter(currentFilter)
        recountSelected()
    }
    
    // Scanlator filter: rebuilds the model.
    function applyFilter(filter) {
        currentFilter = filter
        chapterModel.clear()
        for (var i = 0; i < allChapters.length; i++) {
            var ch = allChapters[i]
            if (filter === "Any" || !filter || ch.group_name === filter) {
                var row = {}
                for (var k in ch) row[k] = ch[k]
                row.shown = Chapters.matches(ch, textFilter)
                row.waveDelay = 0
                row.wave = 0
                chapterModel.append(row)
            }
        }
        anchorIndex = -1
        recountVisible()
        recountSelected()
    }

    // Text filter: rows collapse / expand in place (animated).
    function setTextFilter(q) {
        textFilter = q
        for (var i = 0; i < chapterModel.count; i++)
            chapterModel.setProperty(i, "shown", Chapters.matches(chapterModel.get(i), q))
        anchorIndex = -1
        recountVisible()
    }

    function recountVisible() {
        var n = 0
        for (var i = 0; i < chapterModel.count; i++) if (chapterModel.get(i).shown) n++
        visibleCount = n
    }

    function visibleIndices() {
        var out = []
        for (var i = 0; i < chapterModel.count; i++) if (chapterModel.get(i).shown) out.push(i)
        return out
    }

    // Write a row's selection to both the model and allChapters.
    function _setSelected(i, on, waveDelay) {
        var row = chapterModel.get(i)
        if (row.selected === on && waveDelay === undefined) return
        chapterModel.setProperty(i, "waveDelay", waveDelay === undefined ? 0 : waveDelay)
        chapterModel.setProperty(i, "selected", on)
        if (waveDelay !== undefined) chapterModel.setProperty(i, "wave", row.wave + 1)
        // Match allChapters by a compound key. chapter_id alone is
        // unreliable — several providers set chapter_id=0 for every
        // chapter; ``volume`` carries the chapter URL on those and is
        // unique; ``number`` + ``group_name`` disambiguate comix's
        // multi-scanlator case.
        for (var j = 0; j < allChapters.length; j++) {
            var c = allChapters[j]
            if (c.chapter_id === row.chapter_id
                && c.number === row.number
                && (c.volume || "") === (row.volume || "")
                && (c.group_name || "") === (row.group_name || "")) {
                c.selected = on
                break
            }
        }
    }

    // Click on a row. Shift extends from the anchor over visible rows,
    // applying the clicked row's new state, with a ripple "wave".
    function toggleAt(index, shift) {
        var on = !chapterModel.get(index).selected
        if (shift && anchorIndex >= 0) {
            var vis = visibleIndices()
            var a = vis.indexOf(anchorIndex), b = vis.indexOf(index)
            if (a >= 0 && b >= 0) {
                var span = Chapters.rangeIndices(a, b)
                for (var k = 0; k < span.length; k++)
                    _setSelected(vis[span[k]], on, Math.abs(span[k] - b) * 25)
            } else {
                _setSelected(index, on)
            }
        } else {
            _setSelected(index, on)
        }
        anchorIndex = index
        recountSelected()
    }

    // Select All / None over visible rows, cascading top to bottom.
    function selectAllVisible(on) {
        var vis = visibleIndices()
        for (var k = 0; k < vis.length; k++)
            _setSelected(vis[k], on, Math.min(k, 20) * 22)
        recountSelected()
    }
    
    function getSelectedChapters() {
        var selected = []
        for (var i = 0; i < allChapters.length; i++) {
            if (allChapters[i].selected) selected.push(allChapters[i])
        }
        return selected
    }
    
    function getScanlators() {
        var scanlators = new Set()
        for (var i = 0; i < allChapters.length; i++) {
            if (allChapters[i].group_name) {
                scanlators.add(allChapters[i].group_name)
            }
        }
        var result = ["Any"]
        scanlators.forEach(function(s) { result.push(s) })
        return result
    }
    
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 8
        
        // HEADER
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            
            Text {
                text: "CHAPTERS"
                font.family: "Segoe UI"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                color: textPrimary
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: -2
                    width: parent.width
                    height: 2
                    color: accentPrimary
                    opacity: 0.5
                    radius: 1
                }
            }

            // "N / M selected" — the number ticks when it changes
            Row {
                spacing: 4
                Text {
                    id: selNum
                    text: root.selectedCount
                    font.pixelSize: 12; font.weight: Font.Bold
                    color: accentPrimary
                    property int last: 0
                    onTextChanged: { tick.restart() }
                    transform: Translate { id: tickShift }
                    SequentialAnimation {
                        id: tick
                        ParallelAnimation {
                            NumberAnimation { target: tickShift; property: "y"; to: -4; duration: Theme.dur(120) }
                            NumberAnimation { target: selNum; property: "scale"; to: 1.3; duration: Theme.dur(120) }
                        }
                        ParallelAnimation {
                            NumberAnimation { target: tickShift; property: "y"; to: 0; duration: Theme.dur(260); easing.type: Easing.OutBack }
                            NumberAnimation { target: selNum; property: "scale"; to: 1; duration: Theme.dur(260); easing.type: Easing.OutBack }
                        }
                    }
                }
                Text {
                    text: "/ " + root.visibleCount + " selected"
                    font.pixelSize: 12
                    color: textSecondary
                }
            }
            
            Item { Layout.fillWidth: true }

            // Text filter — widens when focused
            Rectangle {
                Layout.preferredWidth: filterField.activeFocus || filterField.text ? 210 : 150
                Layout.preferredHeight: 30
                Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutBack } }
                radius: 8
                color: bgElevated
                border.color: filterField.activeFocus ? accentPrimary : Theme.border
                Behavior on border.color { ColorAnimation { duration: Theme.dur(250) } }
                TextField {
                    id: filterField
                    anchors.fill: parent
                    leftPadding: 10
                    placeholderText: "🔍 Filter…"
                    font.pixelSize: 12
                    color: textPrimary
                    placeholderTextColor: textTertiary
                    palette.text: textPrimary
                    palette.placeholderText: textTertiary
                    palette.highlight: accentPrimary
                    palette.highlightedText: Theme.bg
                    selectionColor: accentPrimary
                    selectedTextColor: Theme.bg
                    background: Item {}
                    onTextChanged: root.setTextFilter(text)
                }
            }
            
            // Show filtered / total count
            Text {
                text: {
                    if (currentFilter !== "Any") {
                        return chapterModel.count + " shown (of " + allChapters.length + ")"
                    }
                    return allChapters.length + " available"
                }
                font.pixelSize: 12
                color: currentFilter !== "Any" ? accentPrimary : textTertiary
            }
        }
        
        // CHAPTER LIST
        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            model: chapterModel
            clip: true
            spacing: 0
            reuseItems: false
            
            ScrollBar.vertical: ScrollBar { 
                policy: ScrollBar.AsNeeded
                background: Rectangle {
                    implicitWidth: 8
                    color: bgElevated
                    radius: 4
                }
                contentItem: Rectangle {
                    implicitWidth: 8
                    radius: 4
                    color: parent.pressed ? accentPrimary : (parent.hovered ? Qt.lighter(accentPrimary, 1.3) : textTertiary)
                    Behavior on color { ColorAnimation { duration: Theme.dur(150) } }
                }
            }
            
            delegate: ChapterDelegate {
                width: listView.width - 10
                chapter: ({
                    "chapter_id": model.chapter_id,
                    "number": model.number,
                    "title": model.title,
                    "group_name": model.group_name,
                    "selected": model.selected
                })
                shown: model.shown
                waveDelay: model.waveDelay
                wave: model.wave
                entranceDelay: Date.now() - root.loadedAt < 1000 ? Motion.staggerDelay(index) : -1
                onToggled: (shift) => root.toggleAt(index, shift)
            }
            
            Text {
                anchors.centerIn: parent
                text: currentFilter !== "Any" ? "No chapters from this scanlator"
                      : (root.allChapters.length > 0 ? "No chapters match the filter" : "Enter a manga URL to see chapters")
                font.pixelSize: 14
                color: textTertiary
                visible: root.visibleCount === 0
            }
        }
        
        // SELECTION CONTROLS
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            
            SmallButton { text: "Select All"; onClicked: root.selectAllVisible(true) }
            SmallButton { text: "None"; onClicked: root.selectAllVisible(false) }
            
            Item { Layout.fillWidth: true }
            
            Text {
                text: "Shift-click selects a range"
                font.pixelSize: 11
                color: textTertiary
            }
        }
    }

    component SmallButton: Rectangle {
        id: sb
        property string text: ""
        signal clicked()
        implicitWidth: sbText.width + 18
        implicitHeight: 28
        color: sbArea.containsMouse ? bgElevated : "transparent"
        border.color: sbArea.containsMouse ? accentPrimary : Theme.border
        border.width: 1; radius: 7
        scale: sbArea.pressed ? 0.9 : 1
        Behavior on scale { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutBack } }
        Behavior on border.color { ColorAnimation { duration: Theme.dur(200) } }
        Text { id: sbText; anchors.centerIn: parent; text: sb.text; font.pixelSize: 12; color: textSecondary }
        MouseArea { id: sbArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: sb.clicked() }
    }
}
