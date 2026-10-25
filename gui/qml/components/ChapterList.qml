import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    
    ListModel { id: chapterModel }
    property var allChapters: []  // Store original list for filtering
    property string currentFilter: "Any"

    // Explicit selection counter. QML's binding system doesn't fire
    // change signals on in-place mutations of a `property var` array
    // (allChapters[i].selected = true …), so the previous binding to
    // `getSelectedChapters().length` never re-evaluated. We update
    // this manually from every toggle path: per-row click, Select
    // All, None, and the initial filter rebuild.
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
    
    function setChapters(chapterList) {
        allChapters = chapterList
        applyFilter(currentFilter)
        recountSelected()
    }

    function applyFilter(filter) {
        currentFilter = filter
        chapterModel.clear()

        for (var i = 0; i < allChapters.length; i++) {
            var ch = allChapters[i]
            if (filter === "Any" || !filter || ch.group_name === filter) {
                chapterModel.append(ch)
            }
        }
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
            
            Item { Layout.fillWidth: true }
            
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
            spacing: 4
            
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
                    
                    Behavior on color { ColorAnimation { duration: 150 } }
                }
            }
            
            delegate: ChapterDelegate {
                id: chapterDelegate
                width: listView.width - 10
                chapter: ({
                    "chapter_id": model.chapter_id,
                    "number": model.number,
                    "title": model.title,
                    "group_name": model.group_name,
                    "selected": model.selected
                })
                onToggled: {
                    var isSelected = !model.selected
                    chapterModel.setProperty(index, "selected", isSelected)

                    // Match the corresponding entry in allChapters by a
                    // compound key. chapter_id alone is unreliable —
                    // providers that don't expose numeric chapter ids
                    // (manhwa18, manhwabuddy, manhwaread, toonily,
                    // mangadistrict, webtoonscan) set chapter_id=0
                    // for every chapter, so matching on id-only flips
                    // allChapters[0] every time. ``volume`` carries
                    // the chapter URL on those providers and is
                    // guaranteed unique; ``number`` + ``group_name``
                    // disambiguate the multi-scanlator case on comix.
                    for (var j = 0; j < root.allChapters.length; j++) {
                        var c = root.allChapters[j]
                        if (c.chapter_id === model.chapter_id
                            && c.number === model.number
                            && (c.volume || "") === (model.volume || "")
                            && (c.group_name || "") === (model.group_name || "")) {
                            c.selected = isSelected
                            break
                        }
                    }
                    root.selectedCount += isSelected ? 1 : -1
                }
                
                // Reference the parent ChapterList
                property var chapterList: root
            }
            
            Text {
                anchors.centerIn: parent
                text: currentFilter !== "Any" ? "No chapters from this scanlator" : "Enter a manga URL to see chapters"
                font.pixelSize: 14
                color: textTertiary
                visible: chapterModel.count === 0
            }
        }
        
        // SELECTION CONTROLS
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            
            Rectangle {
                implicitWidth: allText.width + 16
                implicitHeight: 28
                color: allArea.containsMouse ? bgElevated : "transparent"
                border.color: textTertiary; border.width: 1; radius: 6
                Text { id: allText; anchors.centerIn: parent; text: "Select All"; font.pixelSize: 12; color: textSecondary }
                MouseArea { id: allArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        for (var i = 0; i < chapterModel.count; i++) {
                            chapterModel.setProperty(i, "selected", true)
                        }
                        for (var j = 0; j < allChapters.length; j++) {
                            allChapters[j].selected = true
                        }
                        recountSelected()
                    }
                }
            }
            
            Rectangle {
                implicitWidth: noneText.width + 16
                implicitHeight: 28
                color: noneArea.containsMouse ? bgElevated : "transparent"
                border.color: textTertiary; border.width: 1; radius: 6
                Text { id: noneText; anchors.centerIn: parent; text: "None"; font.pixelSize: 12; color: textSecondary }
                MouseArea { id: noneArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        for (var i = 0; i < chapterModel.count; i++) {
                            chapterModel.setProperty(i, "selected", false)
                        }
                        for (var j = 0; j < allChapters.length; j++) {
                            allChapters[j].selected = false
                        }
                        recountSelected()
                    }
                }
            }
            
            Item { Layout.fillWidth: true }
            
            Text {
                text: root.selectedCount + " selected"
                font.pixelSize: 12
                color: accentPrimary
            }
        }
    }
}
