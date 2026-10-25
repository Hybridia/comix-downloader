import QtQuick
import Style
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property bool isOpen: false

    // Mirror toomics auth into local state so the textareas stay editable
    // until the user hits Save / Login.
    property string toomicsEmailDraft: SettingsBridge ? SettingsBridge.toomicsEmail : ""
    property string toomicsPasswordDraft: SettingsBridge ? SettingsBridge.toomicsPassword : ""
    property string toomicsCookieDraft: SettingsBridge ? SettingsBridge.toomicsCookie : ""
    property string toomicsUaDraft: SettingsBridge ? SettingsBridge.toomicsUserAgent : ""
    property string toomicsStatusText: ""
    property string toomicsStatusLevel: "" // "ok" | "warn" | "err" | ""

    Connections {
        target: SettingsBridge
        function onToomicsStatus(level, message) {
            root.toomicsStatusLevel = level
            root.toomicsStatusText = message
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
    
    visible: isOpen
    color: Qt.rgba(0, 0, 0, 0.7)
    
    // Click outside to close
    MouseArea {
        anchors.fill: parent
        onClicked: root.isOpen = false
    }
    
    // Settings Panel
    Rectangle {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 380
        color: bgSurface
        
        x: root.isOpen ? 0 : width
        Behavior on x { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
        
        MouseArea { anchors.fill: parent } // Prevent click-through
        
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 24
            
            // Header
            RowLayout {
                Layout.fillWidth: true
                
                Text {
                    text: "⚙️ SETTINGS"
                    font.family: "Segoe UI"
                    font.pixelSize: 22
                    font.weight: Font.Bold
                    color: textPrimary
                }
                
                Item { Layout.fillWidth: true }
                
                Rectangle {
                    width: 32; height: 32; radius: 6
                    color: closeArea.containsMouse ? bgElevated : "transparent"
                    Text { anchors.centerIn: parent; text: "×"; font.pixelSize: 18; font.weight: Font.Bold; color: textSecondary }
                    MouseArea { id: closeArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.isOpen = false }
                }
            }
            
            // Scrollable settings body so the toomics section (which
            // adds two TextAreas and a few buttons) can grow past the
            // visible panel height.
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
                spacing: 20
                
                // Output Format
                SettingItem {
                    label: "Output Format"
                    RowLayout {
                        spacing: 8
                        Repeater {
                            model: ["images", "pdf", "cbz"]
                            Rectangle {
                                width: 75; height: 36; radius: 8
                                color: (SettingsBridge ? SettingsBridge.outputFormat : "") === modelData ? accentPrimary : bgElevated
                                border.color: (SettingsBridge ? SettingsBridge.outputFormat : "") === modelData ? accentPrimary : textTertiary
                                border.width: 1
                                
                                Text { 
                                    anchors.centerIn: parent
                                    text: modelData.toUpperCase()
                                    font.pixelSize: 12
                                    font.weight: Font.Bold
                                    color: (SettingsBridge ? SettingsBridge.outputFormat : "") === modelData ? bgDeep : textSecondary 
                                }
                                MouseArea { 
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: SettingsBridge.setValue("output_format", modelData) 
                                }
                            }
                        }
                    }
                }
                
                // Keep Images
                SettingItem {
                    label: "Keep Images After Conversion"
                    ToggleSwitch {
                        checked: SettingsBridge ? SettingsBridge.keepImages : false
                        onToggled: if (SettingsBridge) SettingsBridge.setValue("keep_images", checked)
                    }
                }
                
                // Enable Logs
                SettingItem {
                    label: "Enable Debug Logs"
                    ToggleSwitch {
                        checked: SettingsBridge ? (SettingsBridge.getValue("enable_logs") || false) : false
                        onToggled: if (SettingsBridge) SettingsBridge.setValue("enable_logs", checked)
                    }
                }
                
                // Download Path
                SettingItem {
                    label: "Download Path"
                    Rectangle {
                        width: 220; height: 40; radius: 8
                        color: bgElevated
                        border.color: textTertiary; border.width: 1
                        
                        TextInput {
                            anchors.fill: parent
                            anchors.leftMargin: 12; anchors.rightMargin: 12
                            verticalAlignment: Text.AlignVCenter
                            text: SettingsBridge ? SettingsBridge.downloadPath : ""
                            color: textPrimary
                            font.pixelSize: 14
                            clip: true
                            selectByMouse: true
                            onEditingFinished: if (SettingsBridge) SettingsBridge.setValue("download_path", text)
                        }
                    }
                }
                
                // Max Chapter Workers
                SettingItem {
                    label: "Max Chapter Workers (1-10)"
                    NumberInput {
                        value: SettingsBridge ? SettingsBridge.maxChapterWorkers : 3
                        minValue: 1; maxValue: 10
                        onValueChanged: if (SettingsBridge && value !== SettingsBridge.maxChapterWorkers) SettingsBridge.setValue("max_chapter_workers", value)
                    }
                }
                
                // Max Image Workers
                SettingItem {
                    label: "Max Image Workers (1-20)"
                    NumberInput {
                        value: SettingsBridge ? SettingsBridge.maxImageWorkers : 5
                        minValue: 1; maxValue: 20
                        onValueChanged: if (SettingsBridge && value !== SettingsBridge.maxImageWorkers) SettingsBridge.setValue("max_image_workers", value)
                    }
                }

                // ─── Divider ─────────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    height: 1
                    color: textTertiary
                    opacity: 0.3
                }

                // ─── Toomics auth ────────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "TOOMICS LOGIN"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        color: accentPrimary
                        Layout.topMargin: 4
                    }
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

                    // ── Credentials (preferred) ──────────────────
                    Text {
                        text: "Email"
                        font.pixelSize: 12
                        color: textSecondary
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 8
                        color: bgElevated
                        border.color: textTertiary; border.width: 1
                        TextInput {
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            font.pixelSize: 13
                            clip: true
                            selectByMouse: true
                            inputMethodHints: Qt.ImhEmailCharactersOnly | Qt.ImhNoAutoUppercase
                            text: root.toomicsEmailDraft
                            onTextChanged: root.toomicsEmailDraft = text
                        }
                    }

                    Text {
                        text: "Password"
                        font.pixelSize: 12
                        color: textSecondary
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 8
                        color: bgElevated
                        border.color: textTertiary; border.width: 1
                        TextInput {
                            id: toomicsPwField
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            font.pixelSize: 13
                            echoMode: TextInput.Password
                            clip: true
                            selectByMouse: true
                            text: root.toomicsPasswordDraft
                            onTextChanged: root.toomicsPasswordDraft = text
                        }
                    }

                    // Login button — runs the email/password flow, populates
                    // cookie + UA automatically.
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 8
                        color: loginArea.containsMouse ? accentPrimary : bgElevated
                        border.color: accentPrimary; border.width: 1
                        Text {
                            anchors.centerIn: parent
                            text: "🔐 Login"
                            font.pixelSize: 13
                            font.weight: Font.Bold
                            color: loginArea.containsMouse ? bgDeep : accentPrimary
                        }
                        MouseArea {
                            id: loginArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: if (SettingsBridge) {
                                SettingsBridge.loginToomics(
                                    root.toomicsEmailDraft,
                                    root.toomicsPasswordDraft,
                                    true
                                )
                            }
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

                    Text {
                        text: "Session cookie"
                        font.pixelSize: 12
                        color: textSecondary
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        radius: 8
                        color: bgElevated
                        border.color: textTertiary; border.width: 1
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
                                selectByMouse: true
                                text: root.toomicsCookieDraft
                                onTextChanged: root.toomicsCookieDraft = text
                            }
                        }
                    }

                    Text {
                        text: "User-agent"
                        font.pixelSize: 12
                        color: textSecondary
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 8
                        color: bgElevated
                        border.color: textTertiary; border.width: 1
                        TextInput {
                            id: toomicsUaField
                            anchors.fill: parent
                            anchors.leftMargin: 10; anchors.rightMargin: 10
                            verticalAlignment: TextInput.AlignVCenter
                            color: textPrimary
                            font.pixelSize: 12
                            font.family: "Menlo"
                            clip: true
                            selectByMouse: true
                            text: root.toomicsUaDraft
                            onTextChanged: root.toomicsUaDraft = text
                        }
                    }

                    // Buttons row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Rectangle {
                            Layout.preferredWidth: 90
                            Layout.preferredHeight: 36
                            radius: 8
                            color: saveArea.containsMouse ? accentPrimary : bgElevated
                            border.color: accentPrimary; border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "Save"
                                font.pixelSize: 12
                                font.weight: Font.Bold
                                color: saveArea.containsMouse ? bgDeep : accentPrimary
                            }
                            MouseArea {
                                id: saveArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (SettingsBridge) {
                                    SettingsBridge.saveToomicsAuth(
                                        root.toomicsCookieDraft,
                                        root.toomicsUaDraft
                                    )
                                }
                            }
                        }

                        Rectangle {
                            Layout.preferredWidth: 90
                            Layout.preferredHeight: 36
                            radius: 8
                            color: testArea.containsMouse ? bgElevated : "transparent"
                            border.color: textSecondary; border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "Test"
                                font.pixelSize: 12
                                font.weight: Font.Bold
                                color: textPrimary
                            }
                            MouseArea {
                                id: testArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (SettingsBridge) SettingsBridge.testToomicsAuth()
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Rectangle {
                            Layout.preferredWidth: 70
                            Layout.preferredHeight: 36
                            radius: 8
                            color: clearArea.containsMouse ? error : "transparent"
                            border.color: error; border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: "Clear"
                                font.pixelSize: 12
                                font.weight: Font.Bold
                                color: clearArea.containsMouse ? textPrimary : error
                            }
                            MouseArea {
                                id: clearArea
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (SettingsBridge) {
                                    root.toomicsCookieDraft = ""
                                    root.toomicsUaDraft = ""
                                    SettingsBridge.clearToomicsAuth()
                                }
                            }
                        }
                    }

                    // Status line
                    Text {
                        Layout.fillWidth: true
                        visible: root.toomicsStatusText !== ""
                        text: root.toomicsStatusText
                        wrapMode: Text.WordWrap
                        font.pixelSize: 11
                        color: root.toomicsStatusLevel === "ok" ? success :
                               root.toomicsStatusLevel === "warn" ? accentPrimary :
                               root.toomicsStatusLevel === "err" ? error : textSecondary
                    }
                }

                // ─── End toomics auth ────────────────────────────────

                Item { Layout.preferredHeight: 4 }

                // Reset Button
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 180; height: 44; radius: 8
                    color: resetArea.containsMouse ? error : "transparent"
                    border.color: error; border.width: 2

                    Text {
                        anchors.centerIn: parent
                        text: "Reset to Defaults"
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                        color: resetArea.containsMouse ? textPrimary : error
                    }

                    MouseArea {
                        id: resetArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: SettingsBridge.resetToDefaults()
                    }
                }
            } // settingsCol
            } // Flickable
        }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // SETTING ITEM COMPONENT
    // ═══════════════════════════════════════════════════════════════
    component SettingItem: ColumnLayout {
        property string label: ""
        default property alias content: contentArea.children
        
        Layout.fillWidth: true
        spacing: 8
        
        Text { 
            text: label
            font.pixelSize: 13
            font.weight: Font.Medium
            color: textSecondary 
        }
        Row { id: contentArea; spacing: 8 }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // TOGGLE SWITCH COMPONENT
    // ═══════════════════════════════════════════════════════════════
    component ToggleSwitch: Rectangle {
        property bool checked: false
        signal toggled()
        
        width: 52; height: 28; radius: 14
        color: checked ? accentPrimary : bgElevated
        border.color: checked ? accentPrimary : textTertiary; border.width: 1
        
        Behavior on color { ColorAnimation { duration: 150 } }
        
        Rectangle {
            width: 22; height: 22; radius: 11
            anchors.verticalCenter: parent.verticalCenter
            x: parent.checked ? parent.width - width - 3 : 3
            color: textPrimary
            
            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
        
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: { parent.checked = !parent.checked; parent.toggled() }
        }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // NUMBER INPUT COMPONENT (custom spinbox replacement)
    // ═══════════════════════════════════════════════════════════════
    component NumberInput: Rectangle {
        property int value: 0
        property int minValue: 0
        property int maxValue: 100
        
        width: 120; height: 40; radius: 8
        color: bgElevated
        border.color: textTertiary; border.width: 1
        
        RowLayout {
            anchors.fill: parent
            anchors.margins: 4
            spacing: 0
            
            // Minus button
            Rectangle {
                Layout.preferredWidth: 32; Layout.fillHeight: true
                radius: 6
                color: minusArea.containsMouse ? bgCard : "transparent"
                
                Text {
                    anchors.centerIn: parent
                    text: "−"
                    font.pixelSize: 18
                    font.weight: Font.Bold
                    color: value > minValue ? accentPrimary : textTertiary
                }
                
                MouseArea {
                    id: minusArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (value > minValue) value--
                }
            }
            
            // Value display
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                
                Text {
                    anchors.centerIn: parent
                    text: value
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    color: textPrimary
                }
            }
            
            // Plus button
            Rectangle {
                Layout.preferredWidth: 32; Layout.fillHeight: true
                radius: 6
                color: plusArea.containsMouse ? bgCard : "transparent"
                
                Text {
                    anchors.centerIn: parent
                    text: "+"
                    font.pixelSize: 18
                    font.weight: Font.Bold
                    color: value < maxValue ? accentPrimary : textTertiary
                }
                
                MouseArea {
                    id: plusArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (value < maxValue) value++
                }
            }
        }
    }
}
