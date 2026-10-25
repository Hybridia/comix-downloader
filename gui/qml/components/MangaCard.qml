import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "../fx"

Rectangle {
    id: root
    objectName: "mangaCard"
    
    property var manga: null
    // A fetch is in flight and its manga hasn't arrived yet → skeleton.
    property bool loading: false
    property bool descOpen: false
    
    // Theme colors
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color success: Theme.success
    readonly property color error: Theme.error
    
    color: bgCard
    radius: 12
    border.color: Theme.border
    clip: true
    
    // Fade-in animation
    opacity: manga || loading ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutCubic } }

    Connections {
        target: MangaBridge
        function onLoadingChanged(isLoading) { if (isLoading) root.loading = true }
        function onErrorOccurred(err) { root.loading = false }
    }
    onMangaChanged: {
        loading = false
        descOpen = false
        if (manga) reveal.restart()
    }
    
    // Language code mapping
    function getLanguageName(code) {
        var languages = {
            "zh": "Chinese",
            "ko": "Korean",
            "ja": "Japanese",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "pt": "Portuguese",
            "id": "Indonesian",
            "th": "Thai",
            "vi": "Vietnamese"
        }
        return languages[code] || code.toUpperCase()
    }

    // ── Reveal choreography ────────────────────────────────────────
    property real coverBlur: 0
    property real coverScale: 1
    property real sweepX: -1.2
    property real tagsGate: 1          // tags pop after the title
    property int revealSeq: 0
    ParallelAnimation {
        id: reveal
        onStarted: root.revealSeq++
        SequentialAnimation {
            PropertyAction { target: root; property: "coverBlur"; value: 1 }
            NumberAnimation { target: root; property: "coverBlur"; to: 0; duration: Theme.dur(900); easing.type: Easing.OutQuint }
        }
        SequentialAnimation {
            PropertyAction { target: root; property: "coverScale"; value: 0.92 }
            NumberAnimation { target: root; property: "coverScale"; to: 1; duration: Theme.dur(900); easing.type: Easing.OutBack }
        }
        SequentialAnimation {
            PropertyAction { target: root; property: "sweepX"; value: -1.2 }
            PauseAnimation { duration: Theme.dur(500) }
            NumberAnimation { target: root; property: "sweepX"; to: 1.2; duration: Theme.dur(1100); easing.type: Easing.OutQuint }
        }
    }

    // ── Skeleton while fetching ─────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12
        visible: root.loading
        Skeleton { Layout.fillWidth: true; Layout.preferredHeight: width * 1.4; radius: 12 }
        Skeleton { Layout.preferredWidth: parent.width * 0.75; Layout.preferredHeight: 20 }
        Skeleton { Layout.preferredWidth: parent.width * 0.45; Layout.preferredHeight: 12 }
        Skeleton { Layout.fillWidth: true; Layout.preferredHeight: 12 }
        Skeleton { Layout.preferredWidth: parent.width * 0.85; Layout.preferredHeight: 12 }
        Skeleton { Layout.preferredWidth: parent.width * 0.6; Layout.preferredHeight: 12 }
        Item { Layout.fillHeight: true }
    }
    
    ScrollView {
        anchors.fill: parent
        anchors.margins: 16
        clip: true
        contentWidth: availableWidth
        visible: !root.loading && root.manga
        
        // Hide scrollbar (users can still scroll with mouse wheel)
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
        }
        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AlwaysOff
        }
        
        ColumnLayout {
            width: parent.width
            spacing: 14
            
            // ─────────────────────────────────────────────────────────────
            // COVER IMAGE — blurs into focus with a light sweep
            // ─────────────────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: width * 1.4  // Manga cover ratio ~1:1.4
                color: bgElevated
                radius: 12
                clip: true
                scale: root.coverScale
                
                Image {
                    id: coverImage
                    anchors.fill: parent
                    source: manga ? manga.poster_url : ""
                    fillMode: Image.PreserveAspectFit  // Don't crop
                    
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.dur(400) } }
                    layer.enabled: root.coverBlur > 0.01 && !Theme.software
                    layer.effect: MultiEffect {
                        blurEnabled: true
                        blur: root.coverBlur
                        blurMax: 48
                        saturation: -0.6 * root.coverBlur
                    }
                }
                
                Text {
                    anchors.centerIn: parent
                    text: "📖"
                    font.pixelSize: 48
                    opacity: coverImage.status !== Image.Ready ? 0.3 : 0
                }

                Rectangle {
                    width: parent.width * 0.5
                    height: parent.height * 1.6
                    y: -parent.height * 0.3
                    rotation: 18
                    x: root.sweepX * parent.width + parent.width * 0.25
                    visible: root.sweepX > -1.15 && root.sweepX < 1.15
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: "transparent" }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.3) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                }
            }
            
            // ─────────────────────────────────────────────────────────────
            // TITLE — letters rise in one by one
            // ─────────────────────────────────────────────────────────────
            Flow {
                id: titleFlow
                Layout.fillWidth: true
                spacing: 5
                Repeater {
                    model: manga ? String(manga.title).split(" ") : []
                    Row {
                        id: word
                        required property string modelData
                        required property int index
                        readonly property int offset: {
                            var words = String(root.manga ? root.manga.title : "").split(" ")
                            var n = 0
                            for (var i = 0; i < index; i++) n += words[i].length
                            return n
                        }
                        Repeater {
                            model: word.modelData.length
                            Text {
                                id: letter
                                required property int index
                                text: word.modelData.charAt(index)
                                font.family: "Segoe UI"
                                font.pixelSize: 18
                                font.weight: Font.Bold
                                color: textPrimary
                                property int seq: root.revealSeq
                                onSeqChanged: rise.restart()
                                Component.onCompleted: rise.restart()
                                transform: Translate { id: lift; y: 0 }
                                SequentialAnimation {
                                    id: rise
                                    PropertyAction { target: letter; property: "opacity"; value: Theme.animations ? 0 : 1 }
                                    PropertyAction { target: lift; property: "y"; value: Theme.animations ? 14 : 0 }
                                    PauseAnimation { duration: Theme.dur(Math.min(word.offset + letter.index, 40) * 40) }
                                    ParallelAnimation {
                                        NumberAnimation { target: letter; property: "opacity"; to: 1; duration: Theme.dur(450); easing.type: Easing.OutQuint }
                                        NumberAnimation { target: lift; property: "y"; to: 0; duration: Theme.dur(500); easing.type: Easing.OutQuint }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            
            // ─────────────────────────────────────────────────────────────
            // TAGS (NSFW first) — pop in after the title
            // ─────────────────────────────────────────────────────────────
            Flow {
                Layout.fillWidth: true
                spacing: 6
                visible: tagRepeater.count > 0
                Repeater {
                    id: tagRepeater
                    model: {
                        if (!manga) return []
                        var t = []
                        if (manga.is_nsfw) t.push("NSFW")
                        if (manga.status) t.push(manga.status)
                        var tags = manga.tags || []
                        for (var i = 0; i < tags.length && t.length < 9; i++) t.push(tags[i])
                        return t
                    }
                    Rectangle {
                        id: tag
                        required property string modelData
                        required property int index
                        readonly property bool nsfw: modelData === "NSFW"
                        height: 22
                        width: tagText.implicitWidth + 16
                        radius: 7
                        color: nsfw ? error : bgElevated
                        property int seq: root.revealSeq
                        onSeqChanged: pop.restart()
                        Component.onCompleted: pop.restart()
                        Text {
                            id: tagText
                            anchors.centerIn: parent
                            text: tag.modelData
                            font.pixelSize: 11
                            font.weight: tag.nsfw ? Font.Bold : Font.Normal
                            color: tag.nsfw ? "#FFFFFF" : textSecondary
                        }
                        SequentialAnimation {
                            id: pop
                            PropertyAction { target: tag; property: "scale"; value: Theme.animations ? 0.5 : 1 }
                            PropertyAction { target: tag; property: "opacity"; value: Theme.animations ? 0 : 1 }
                            PauseAnimation { duration: Theme.dur(600 + tag.index * 70) }
                            ParallelAnimation {
                                NumberAnimation { target: tag; property: "scale"; to: 1; duration: Theme.dur(450); easing.type: Easing.OutBack }
                                NumberAnimation { target: tag; property: "opacity"; to: 1; duration: Theme.dur(300) }
                            }
                        }
                    }
                }
            }
            
            // ─────────────────────────────────────────────────────────────
            // STATS — numbers count up
            // ─────────────────────────────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                Stat {
                    label: "LATEST"
                    visible: manga && manga.latest_chapter
                    CountUpText { value: manga && manga.latest_chapter ? Number(manga.latest_chapter) || 0 : 0; font.pixelSize: 18; font.weight: Font.Bold }
                }
                Stat {
                    label: "FOLLOWERS"
                    CountUpText { objectName: "mangaFollowers"; value: manga && manga.follows_total ? manga.follows_total : 0; font.pixelSize: 18; font.weight: Font.Bold }
                }
                Stat {
                    label: "RATING"
                    visible: manga && manga.rated_avg > 0
                    CountUpText { value: manga ? manga.rated_avg || 0 : 0; decimals: 1; font.pixelSize: 18; font.weight: Font.Bold; color: accentPrimary }
                }
            }
            
            // ─────────────────────────────────────────────────────────────
            // INFO ROWS
            // ─────────────────────────────────────────────────────────────
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 6
                
                Text { text: "Type"; font.pixelSize: 12; color: textTertiary }
                Text { text: manga ? manga.manga_type : ""; font.pixelSize: 12; color: textSecondary; Layout.fillWidth: true }
                
                Text { text: "Language"; font.pixelSize: 12; color: textTertiary; visible: manga && manga.original_language }
                Text { 
                    text: manga && manga.original_language ? getLanguageName(manga.original_language) : ""
                    font.pixelSize: 12
                    color: accentPrimary
                    visible: manga && manga.original_language
                }
                
                Text { text: "Year"; font.pixelSize: 12; color: textTertiary; visible: manga && manga.year > 0 }
                Text { text: manga && manga.year > 0 ? manga.year : ""; font.pixelSize: 12; color: textSecondary; visible: manga && manga.year > 0 }
            }
            
            // ─────────────────────────────────────────────────────────────
            // DESCRIPTION — collapsed, "Read more" expands smoothly
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                visible: manga && manga.description
                
                Text { text: "Description"; font.pixelSize: 12; color: textTertiary }
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.descOpen ? descText.implicitHeight : Math.min(descText.implicitHeight, 4 * 15)
                    clip: true
                    Behavior on Layout.preferredHeight { NumberAnimation { duration: Theme.dur(500); easing.type: Easing.OutQuint } }
                    Text {
                        id: descText
                        width: parent.width
                        text: manga && manga.description ? manga.description : ""
                        font.pixelSize: 11
                        color: textSecondary
                        wrapMode: Text.WordWrap
                        lineHeight: 1.3
                    }
                }
                Text {
                    visible: descText.implicitHeight > 4 * 15
                    text: root.descOpen ? "Show less ▲" : "Read more ▼"
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    color: accentPrimary
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.descOpen = !root.descOpen
                    }
                }
            }
            
            Item { height: 8 }
        }
    }

    component Stat: ColumnLayout {
        property string label: ""
        spacing: 0
        Text { text: parent.label; font.pixelSize: 10; font.letterSpacing: 1.2; color: textTertiary }
    }
}
