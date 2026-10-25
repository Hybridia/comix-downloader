import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Style
import "../fx"
import "../Style/palettes.js" as Palettes

Item {
    id: root

    property bool isOpen: false
    // The app content behind the drawer — blurred while it's open.
    property Item backdropSource: null
    // Toomics login in flight (button shows a spinner).
    property bool loginBusy: false

    // Mirror toomics auth into local state so the textareas stay editable
    // until the user hits Save / Login.
    property string toomicsEmailDraft: SettingsBridge ? SettingsBridge.toomicsEmail : ""
    property string toomicsPasswordDraft: SettingsBridge ? SettingsBridge.toomicsPassword : ""
    property string toomicsCookieDraft: SettingsBridge ? SettingsBridge.toomicsCookie : ""
    property string toomicsUaDraft: SettingsBridge ? SettingsBridge.toomicsUserAgent : ""
    property string toomicsStatusText: ""
    property string toomicsStatusLevel: "" // "ok" | "warn" | "err" | ""

    readonly property var themeLabels: ({ ink: "Ink & Sakura", neon: "Neon Tokyo", ember: "Ember" })

    function chooseTheme(name, scenePoint) {
        if (SettingsBridge && SettingsBridge.theme === name) return
        Fx.themeWipeRequested(name, scenePoint)
    }
    function setAnimations(on) { SettingsBridge.animationsEnabled = on }
    function setAmbient(on) { SettingsBridge.ambientGlow = on }

    Connections {
        target: SettingsBridge
        function onToomicsStatus(level, message) {
            root.loginBusy = false
            root.toomicsStatusLevel = level
            root.toomicsStatusText = message
            if (level === "ok") Fx.toast("Toomics session saved", "ok")
            else if (level === "err") toomicsSection.shake()
        }
        function onSettingsChanged() {
            // Re-sync drafts when settings change externally.
            root.toomicsEmailDraft = SettingsBridge.toomicsEmail
            root.toomicsPasswordDraft = SettingsBridge.toomicsPassword
            root.toomicsCookieDraft = SettingsBridge.toomicsCookie
            root.toomicsUaDraft = SettingsBridge.toomicsUserAgent
        }
    }
    
    // Theme colors
    readonly property color bgDeep: Theme.bg
    readonly property color bgSurface: Theme.surface
    readonly property color bgCard: Theme.card
    readonly property color bgElevated: Theme.elevated
    readonly property color accentPrimary: Theme.accent
    readonly property color textPrimary: Theme.textPrimary
    readonly property color textSecondary: Theme.textSecondary
    readonly property color textTertiary: Theme.textTertiary
    readonly property color error: Theme.error
    readonly property color success: Theme.success
    
    visible: isOpen || panel.x < width

    // Blurred snapshot of the app behind the drawer (not in software).
    Loader {
        id: backdrop
        anchors.fill: parent
        active: root.visible && root.backdropSource !== null && !Theme.software && Theme.animations
        sourceComponent: Item {
            function refresh() {}
            opacity: root.isOpen ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.dur(450) } }
            ShaderEffectSource {
                id: snap
                anchors.fill: parent
                sourceItem: root.backdropSource
                // Only exists while the drawer is showing; the app behind
                // rarely changes then, so live updates are cheap.
                live: true
                visible: false
            }
            MultiEffect {
                anchors.fill: parent
                source: snap
                blurEnabled: true
                blur: 0.7
                blurMax: 32
            }
        }
    }

    // Dimmed scrim — click outside to close
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.45)
        opacity: root.isOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.dur(450) } }
        MouseArea {
            anchors.fill: parent
            enabled: root.isOpen
            onClicked: root.isOpen = false
        }
    }
    
    // Settings Panel — springs in from the right
    Rectangle {
        id: panel
        objectName: "settingsPanel"
        y: 0
        height: parent.height
        width: 420
        color: bgSurface
        border.color: Theme.border
        x: root.isOpen ? root.width - width : root.width + 24
        Behavior on x { NumberAnimation { duration: Theme.dur(600); easing.type: root.isOpen ? Easing.OutBack : Easing.InCubic; easing.overshoot: 0.9 } }
        
        MouseArea { anchors.fill: parent } // Prevent click-through
        
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14
            
            // Header
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 2
                    Text {
                        text: "SETTINGS"
                        font.pixelSize: 22
                        font.weight: Font.Bold
                        font.letterSpacing: 1.5
                        color: textPrimary
                    }
                    Text {
                        text: "Every change saves on its own"
                        font.pixelSize: 11
                        color: textTertiary
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 34; height: 34; radius: 17
                    color: closeArea.containsMouse ? bgElevated : bgCard
                    border.color: Theme.border
                    rotation: closeArea.containsMouse ? 90 : 0
                    scale: closeArea.containsMouse ? 1.1 : 1
                    Behavior on rotation { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutBack } }
                    Behavior on scale { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutBack } }
                    Text { anchors.centerIn: parent; text: "✕"; font.pixelSize: 14; color: textPrimary }
                    MouseArea { id: closeArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.isOpen = false }
                }
            }
            
            Flickable {
                id: settingsScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: settingsCol.width
                contentHeight: settingsCol.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds

            ColumnLayout {
                id: settingsCol
                width: settingsScroll.width
                spacing: 14

                // ─── Appearance ──────────────────────────────────────
                Section {
                    title: "APPEARANCE"
                    order: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: Theme.themes
                            ThemeCard {
                                required property string modelData
                                Layout.fillWidth: true
                                themeName: modelData
                            }
                        }
                    }
                    ToggleRow {
                        label: "Animations"
                        checked: SettingsBridge ? SettingsBridge.animationsEnabled : true
                        onToggled: (on) => root.setAnimations(on)
                    }
                    ToggleRow {
                        label: "Drifting background glow"
                        checked: SettingsBridge ? SettingsBridge.ambientGlow : true
                        onToggled: (on) => root.setAmbient(on)
                    }
                }

                // ─── Downloads ───────────────────────────────────────
                Section {
                    title: "DOWNLOADS"
                    order: 1

                    Text { text: "Output format"; font.pixelSize: 13; color: textSecondary }
                    FormatSelector { Layout.fillWidth: true }

                    ToggleRow {
                        label: "Keep images after conversion"
                        checked: SettingsBridge ? SettingsBridge.keepImages : false
                        onToggled: (on) => SettingsBridge.setValue("keep_images", on)
                    }
                    ToggleRow {
                        label: "Enable debug logs"
                        checked: SettingsBridge ? (SettingsBridge.getValue("enable_logs") || false) : false
                        onToggled: (on) => SettingsBridge.setValue("enable_logs", on)
                    }

                    SliderRow {
                        label: "Chapter workers"
                        from: 1; to: 10
                        value: SettingsBridge ? SettingsBridge.maxChapterWorkers : 3
                        onMoved: (v) => { if (SettingsBridge && v !== SettingsBridge.maxChapterWorkers) SettingsBridge.setValue("max_chapter_workers", v) }
                    }
                    SliderRow {
                        label: "Image workers"
                        from: 1; to: 20
                        value: SettingsBridge ? SettingsBridge.maxImageWorkers : 5
                        onMoved: (v) => { if (SettingsBridge && v !== SettingsBridge.maxImageWorkers) SettingsBridge.setValue("max_image_workers", v) }
                    }

                    Text { text: "Download path"; font.pixelSize: 13; color: textSecondary; Layout.topMargin: 4 }
                    InputBox {
                        Layout.fillWidth: true
                        TextInput {
                            anchors.fill: parent
                            anchors.leftMargin: 12; anchors.rightMargin: 12
                            verticalAlignment: Text.AlignVCenter
                            text: SettingsBridge ? SettingsBridge.downloadPath : ""
                            color: textPrimary
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.bg
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            onEditingFinished: if (SettingsBridge) SettingsBridge.setValue("download_path", text)
                        }
                    }
                }

                // ─── Toomics auth ────────────────────────────────────
                Section {
                    id: toomicsSection
                    title: "TOOMICS LOGIN"
                    order: 2

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "global.toomics.com needs your paid-member session. " +
                              "Easiest path: enter email + password and click <b>Login</b> — " +
                              "we'll fetch the session cookie for you. " +
                              "Stored locally in <code>secrets.json</code> (gitignored, mode 0600). " +
                              "If toomics blocks the form (captcha, MFA), fall back to pasting " +
                              "the <code>cookie</code> request header from devtools."
                        textFormat: Text.RichText
                        font.pixelSize: 11
                        color: textSecondary
                        lineHeight: 1.3
                    }

                    Text { text: "Email"; font.pixelSize: 12; color: textSecondary }
                    InputBox {
                        Layout.fillWidth: true
                        TextInput {
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.bg
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            inputMethodHints: Qt.ImhEmailCharactersOnly | Qt.ImhNoAutoUppercase
                            text: root.toomicsEmailDraft
                            onTextChanged: root.toomicsEmailDraft = text
                        }
                    }
                    Text { text: "Password"; font.pixelSize: 12; color: textSecondary }
                    InputBox {
                        Layout.fillWidth: true
                        TextInput {
                            id: toomicsPwField
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.bg
                            font.pixelSize: 13
                            echoMode: TextInput.Password
                            clip: true
                            selectByMouse: true
                            text: root.toomicsPasswordDraft
                            onTextChanged: root.toomicsPasswordDraft = text
                        }
                    }

                    // Login button — morphs into a spinner while waiting.
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Item {
                            Layout.preferredWidth: root.loginBusy ? 40 : 130
                            Layout.preferredHeight: 40
                            Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutQuint } }
                            FxButton {
                                anchors.fill: parent
                                text: root.loginBusy ? "" : "🔐 Login"
                                radius: root.loginBusy ? 20 : 10
                                Behavior on radius { NumberAnimation { duration: Theme.dur(400) } }
                                onClicked: if (SettingsBridge && !root.loginBusy) {
                                    root.loginBusy = true
                                    root.toomicsStatusText = ""
                                    SettingsBridge.loginToomics(root.toomicsEmailDraft, root.toomicsPasswordDraft, true)
                                }
                            }
                            Spinner {
                                anchors.centerIn: parent
                                width: 22; height: 22
                                visible: root.loginBusy
                                color: Theme.bg
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.toomicsStatusText
                            wrapMode: Text.WordWrap
                            font.pixelSize: 11
                            color: root.toomicsStatusLevel === "ok" ? success :
                                   root.toomicsStatusLevel === "warn" ? accentPrimary :
                                   root.toomicsStatusLevel === "err" ? error : textSecondary
                            opacity: text !== "" ? 1 : 0
                            transform: Translate {
                                y: root.toomicsStatusText !== "" ? 0 : 6
                                Behavior on y { NumberAnimation { duration: Theme.dur(400); easing.type: Easing.OutBack } }
                            }
                            Behavior on opacity { NumberAnimation { duration: Theme.dur(300) } }
                        }
                    }

                    // ── Manual cookie fallback ──────────────────
                    Text {
                        Layout.topMargin: 8
                        text: "— or paste cookie manually —"
                        font.pixelSize: 11
                        color: textTertiary
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text { text: "Session cookie"; font.pixelSize: 12; color: textSecondary }
                    InputBox {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        ScrollView {
                            anchors.fill: parent
                            anchors.margins: 8
                            clip: true
                            TextArea {
                                id: toomicsCookieField
                                wrapMode: TextArea.WrapAnywhere
                                color: textPrimary
                                font.pixelSize: 11
                                font.family: "Menlo"
                                background: null
                                placeholderText: "Paste cookie: <name>=<value>; <name>=<value>; …"
                                placeholderTextColor: textTertiary
                                palette.text: textPrimary
                                palette.placeholderText: textTertiary
                                palette.highlight: Theme.accent
                                palette.highlightedText: Theme.bg
                                selectionColor: Theme.accent
                                selectedTextColor: Theme.bg
                                selectByMouse: true
                                text: root.toomicsCookieDraft
                                onTextChanged: root.toomicsCookieDraft = text
                            }
                        }
                    }
                    Text { text: "User-agent"; font.pixelSize: 12; color: textSecondary }
                    InputBox {
                        Layout.fillWidth: true
                        TextInput {
                            id: toomicsUaField
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            selectionColor: Theme.accent
                            selectedTextColor: Theme.bg
                            font.pixelSize: 12
                            font.family: "Menlo"
                            clip: true
                            selectByMouse: true
                            text: root.toomicsUaDraft
                            onTextChanged: root.toomicsUaDraft = text
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        FxButton {
                            Layout.preferredWidth: 90; Layout.preferredHeight: 36
                            text: "Save"
                            onClicked: if (SettingsBridge) SettingsBridge.saveToomicsAuth(root.toomicsCookieDraft, root.toomicsUaDraft)
                        }
                        FxButton {
                            Layout.preferredWidth: 90; Layout.preferredHeight: 36
                            text: "Test"
                            primary: false
                            onClicked: if (SettingsBridge) SettingsBridge.testToomicsAuth()
                        }
                        Item { Layout.fillWidth: true }
                        FxButton {
                            Layout.preferredWidth: 80; Layout.preferredHeight: 36
                            text: "Clear"
                            primary: false
                            onClicked: if (SettingsBridge) {
                                root.toomicsCookieDraft = ""
                                root.toomicsUaDraft = ""
                                SettingsBridge.clearToomicsAuth()
                            }
                        }
                    }
                }

                // ─── Danger zone ─────────────────────────────────────
                Section {
                    title: "DANGER ZONE"
                    order: 3
                    HoldButton {
                        objectName: "holdReset"
                        Layout.fillWidth: true
                        text: "Hold to reset to defaults"
                        onConfirmed: {
                            SettingsBridge.resetToDefaults()
                            Fx.toast("Settings reset to defaults", "ok")
                        }
                    }
                }

                Item { Layout.preferredHeight: 8 }
            } // settingsCol
            } // Flickable
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // COMPONENTS
    // ═══════════════════════════════════════════════════════════════

    // Card that slides in (staggered by `order`) each time the drawer opens.
    component Section: Rectangle {
        id: sec
        property string title: ""
        property int order: 0
        default property alias content: secCol.data
        function shake() { shakeAnim.restart() }

        Layout.fillWidth: true
        implicitHeight: secCol.implicitHeight + 30
        radius: 14
        color: bgCard
        border.color: Theme.border
        opacity: 0
        transform: Translate { id: secShift; x: 30 }

        Connections {
            target: root
            function onIsOpenChanged() { if (root.isOpen) secIn.restart() }
        }
        Component.onCompleted: if (root.isOpen) secIn.restart()

        SequentialAnimation {
            id: secIn
            PropertyAction { target: sec; property: "opacity"; value: 0 }
            PropertyAction { target: secShift; property: "x"; value: 30 }
            PauseAnimation { duration: Theme.dur(80 + sec.order * 80) }
            ParallelAnimation {
                NumberAnimation { target: sec; property: "opacity"; to: 1; duration: Theme.dur(450); easing.type: Easing.OutQuint }
                NumberAnimation { target: secShift; property: "x"; to: 0; duration: Theme.dur(550); easing.type: Easing.OutQuint }
            }
        }
        SequentialAnimation {
            id: shakeAnim
            loops: 2
            NumberAnimation { target: secShift; property: "x"; to: -7; duration: Theme.dur(56) }
            NumberAnimation { target: secShift; property: "x"; to: 7; duration: Theme.dur(112) }
            NumberAnimation { target: secShift; property: "x"; to: 0; duration: Theme.dur(56) }
        }

        ColumnLayout {
            id: secCol
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10
            Text {
                text: sec.title
                font.pixelSize: 11
                font.weight: Font.Bold
                font.letterSpacing: 2
                color: textTertiary
            }
        }
    }

    // Theme preview card: click → circular colour wipe to that theme.
    component ThemeCard: Rectangle {
        id: card
        property string themeName: "ink"
        readonly property var pal: Palettes.palette(themeName)
        readonly property bool selected: SettingsBridge && SettingsBridge.theme === themeName
        objectName: "themeCard_" + themeName

        implicitHeight: 86
        radius: 12
        color: "transparent"
        border.width: 2
        border.color: selected ? Theme.accent : (cardArea.containsMouse ? Theme.textTertiary : Theme.border)
        Behavior on border.color { ColorAnimation { duration: Theme.dur(250) } }
        transform: Translate {
            y: cardArea.containsMouse ? -3 : 0
            Behavior on y { NumberAnimation { duration: Theme.dur(300); easing.type: Easing.OutBack } }
        }
        // glow ring when selected
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: 15
            color: "transparent"
            border.width: 3
            border.color: Theme.glow
            opacity: card.selected ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.dur(300) } }
        }
        Rectangle {
            id: prev
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
            height: 44
            radius: 7
            color: card.pal.bg
            Rectangle { x: 6; y: 6; width: 16; height: parent.height - 12; radius: 4; color: card.pal.card }
            Rectangle { x: 28; y: 8; width: parent.width - 36; height: 8; radius: 4; color: card.pal.accent }
            Rectangle { x: 28; y: 22; width: (parent.width - 36) * 0.45; height: 6; radius: 3; color: card.pal.cool }
        }
        Text {
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 8 }
            text: root.themeLabels[card.themeName] || card.themeName
            font.pixelSize: 11
            font.weight: card.selected ? Font.DemiBold : Font.Normal
            color: card.selected ? textPrimary : textSecondary
        }
        MouseArea {
            id: cardArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: (m) => root.chooseTheme(card.themeName, card.mapToItem(null, m.x, m.y))
        }
    }

    // Label + springy switch.
    component ToggleRow: RowLayout {
        id: row
        property string label: ""
        property bool checked: false
        signal toggled(bool on)
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: row.label; font.pixelSize: 13; color: textPrimary }
        Rectangle {
            id: sw
            width: 46; height: 26; radius: 13
            color: row.checked ? accentPrimary : bgElevated
            border.color: row.checked ? accentPrimary : Theme.border
            Behavior on color { ColorAnimation { duration: Theme.dur(300) } }
            Rectangle {
                id: knob
                height: 20; radius: 10
                width: swArea.pressed ? 26 : 20
                anchors.verticalCenter: parent.verticalCenter
                x: row.checked ? sw.width - width - 3 : 3
                color: row.checked ? "#FFFFFF" : textSecondary
                Behavior on x { NumberAnimation { duration: Theme.dur(450); easing.type: Easing.OutBack; easing.overshoot: 1.6 } }
                Behavior on width { NumberAnimation { duration: Theme.dur(150) } }
            }
            MouseArea {
                id: swArea
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: row.toggled(!row.checked)
            }
        }
    }

    // Label + slider with a value bubble above the handle.
    component SliderRow: RowLayout {
        id: srow
        property string label: ""
        property int from: 1
        property int to: 10
        property int value: 1
        signal moved(int v)
        Layout.fillWidth: true
        Layout.topMargin: 18
        Text { Layout.fillWidth: true; text: srow.label; font.pixelSize: 13; color: textPrimary }
        Item {
            id: track
            Layout.preferredWidth: 170
            Layout.preferredHeight: 22
            readonly property real frac: (srow.value - srow.from) / Math.max(1, srow.to - srow.from)
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width; height: 4; radius: 2
                color: bgElevated
                Rectangle { width: parent.width * track.frac; height: parent.height; radius: 2; color: accentPrimary }
            }
            Rectangle {
                id: handle
                width: 16; height: 16; radius: 8
                anchors.verticalCenter: parent.verticalCenter
                x: track.frac * (track.width - width)
                color: accentPrimary
                border.color: Theme.highlight
                scale: dragArea.pressed ? 1.25 : 1
                Behavior on scale { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutBack } }
            }
            Rectangle {
                id: bubble
                width: bubbleText.implicitWidth + 12; height: 18; radius: 6
                color: accentPrimary
                x: handle.x + handle.width / 2 - width / 2
                y: -22
                scale: dragArea.pressed ? 1.25 : 1
                transformOrigin: Item.Bottom
                Behavior on scale { NumberAnimation { duration: Theme.dur(250); easing.type: Easing.OutBack } }
                Text { id: bubbleText; anchors.centerIn: parent; text: srow.value; font.pixelSize: 11; font.weight: Font.Black; color: Theme.bg }
            }
            MouseArea {
                id: dragArea
                anchors.fill: parent
                anchors.margins: -6
                cursorShape: Qt.PointingHandCursor
                function pick(mx) {
                    var f = Math.max(0, Math.min(1, (mx - 6) / track.width))
                    var v = Math.round(srow.from + f * (srow.to - srow.from))
                    if (v !== srow.value) srow.moved(v)
                }
                onPressed: (m) => pick(m.x)
                onPositionChanged: (m) => { if (pressed) pick(m.x) }
            }
        }
    }

    // Text field frame with an accent glow while focused.
    component InputBox: Rectangle {
        id: box
        implicitHeight: 40
        radius: 9
        color: bgElevated
        readonly property bool focused: {
            for (var i = 0; i < children.length; i++)
                if (children[i].activeFocus) return true
            return false
        }
        border.color: focused ? Theme.accent : Theme.border
        Behavior on border.color { ColorAnimation { duration: Theme.dur(250) } }
    }

    // Press-and-hold confirm: fills while held, drains back if released.
    component HoldButton: Rectangle {
        id: hold
        property string text: ""
        property real progress: 0
        property int holdTime: 1400
        signal confirmed()
        function begin() {
            drain.stop()
            fill.from = hold.progress
            fill.duration = Math.max(1, hold.holdTime * (1 - hold.progress))
            fill.restart()
        }
        function end() {
            if (!fill.running) return
            fill.stop()
            drain.restart()
        }
        implicitHeight: 44
        radius: 10
        color: bgElevated
        border.color: holdArea.containsMouse ? Theme.error : Theme.border
        clip: true
        Rectangle {
            width: parent.width * hold.progress
            height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Theme.error }
                GradientStop { position: 1; color: Qt.lighter(Theme.error, 1.3) }
            }
            opacity: 0.85
        }
        Text {
            anchors.centerIn: parent
            text: hold.progress > 0 && hold.progress < 1 ? "Keep holding…" : hold.text
            font.pixelSize: 13; font.weight: Font.DemiBold
            color: textPrimary
        }
        NumberAnimation {
            id: fill
            target: hold; property: "progress"; to: 1
            onFinished: if (hold.progress >= 1) { hold.confirmed(); resetTimer.restart() }
        }
        NumberAnimation { id: drain; target: hold; property: "progress"; to: 0; duration: 300; easing.type: Easing.OutQuad }
        Timer { id: resetTimer; interval: 1200; onTriggered: hold.progress = 0 }
        MouseArea {
            id: holdArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: hold.begin()
            onReleased: hold.end()
            onCanceled: hold.end()
        }
    }
}
