import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root
    
    property var manga: null
    
    // Theme colors
    readonly property color bgCard: "#1C1C24"
    readonly property color bgElevated: "#252530"
    readonly property color accentPrimary: "#E8A54B"
    readonly property color textPrimary: "#F5F5F0"
    readonly property color textSecondary: "#8B8B99"
    readonly property color textTertiary: "#5C5C66"
    readonly property color success: "#7CB342"
    readonly property color error: "#E57373"
    
    color: bgCard
    radius: 12
    
    // Fade-in animation
    opacity: manga ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
    
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
    
    ScrollView {
        anchors.fill: parent
        anchors.margins: 16
        clip: true
        contentWidth: availableWidth
        
        // Hide scrollbar (users can still scroll with mouse wheel)
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AlwaysOff
        }
        ScrollBar.horizontal: ScrollBar {
            policy: ScrollBar.AlwaysOff
        }
        
        ColumnLayout {
            width: parent.width
            spacing: 16
            
            // ─────────────────────────────────────────────────────────────
            // COVER IMAGE (fixed aspect ratio, not cropped)
            // ─────────────────────────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: width * 1.4  // Manga cover ratio ~1:1.4
                color: bgElevated
                radius: 12
                clip: true
                
                Image {
                    id: coverImage
                    anchors.fill: parent
                    source: manga ? manga.poster_url : ""
                    fillMode: Image.PreserveAspectFit  // Don't crop
                    
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 400 } }
                }
                
                Text {
                    anchors.centerIn: parent
                    text: "📖"
                    font.pixelSize: 48
                    opacity: coverImage.status !== Image.Ready ? 0.3 : 0
                }
            }
            
            // ─────────────────────────────────────────────────────────────
            // TITLE
            // ─────────────────────────────────────────────────────────────
            Text {
                Layout.fillWidth: true
                text: manga ? manga.title : ""
                font.family: "Segoe UI"
                font.pixelSize: 18
                font.weight: Font.Bold
                color: textPrimary
                wrapMode: Text.WordWrap
            }
            
            // ─────────────────────────────────────────────────────────────
            // NSFW BADGE (if applicable)
            // ─────────────────────────────────────────────────────────────
            Rectangle {
                visible: manga && manga.is_nsfw
                width: 50; height: 22; radius: 4
                color: error
                opacity: 0.9
                Text { anchors.centerIn: parent; text: "NSFW"; font.pixelSize: 10; font.weight: Font.Bold; color: textPrimary }
            }
            
            // ─────────────────────────────────────────────────────────────
            // INFO ROWS
            // ─────────────────────────────────────────────────────────────
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 8
                
                // Type
                Text { text: "Type"; font.pixelSize: 12; color: textTertiary }
                Text { text: manga ? manga.manga_type : ""; font.pixelSize: 12; color: textSecondary; Layout.fillWidth: true }
                
                // Original Language
                Text { text: "Language"; font.pixelSize: 12; color: textTertiary; visible: manga && manga.original_language }
                Text { 
                    text: manga && manga.original_language ? getLanguageName(manga.original_language) : ""
                    font.pixelSize: 12
                    color: accentPrimary
                    visible: manga && manga.original_language
                }
                
                // Status
                Text { text: "Status"; font.pixelSize: 12; color: textTertiary }
                Text { 
                    text: manga ? manga.status : ""
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    color: manga && manga.status === "releasing" ? success : textSecondary
                    Layout.fillWidth: true
                }
                
                // Year
                Text { text: "Year"; font.pixelSize: 12; color: textTertiary; visible: manga && manga.year > 0 }
                Text { text: manga && manga.year > 0 ? manga.year : ""; font.pixelSize: 12; color: textSecondary; visible: manga && manga.year > 0 }
                
                // Latest Chapter
                Text { text: "Latest"; font.pixelSize: 12; color: textTertiary; visible: manga && manga.latest_chapter }
                Text { text: manga ? "Ch. " + manga.latest_chapter : ""; font.pixelSize: 12; color: accentPrimary; visible: manga && manga.latest_chapter }
                
                // Followers
                Text { text: "Followers"; font.pixelSize: 12; color: textTertiary }
                Text { text: manga ? (manga.follows_total ? manga.follows_total.toLocaleString() : "0") : "0"; font.pixelSize: 12; color: textSecondary }
            }
            
            // ─────────────────────────────────────────────────────────────
            // RATING
            // ─────────────────────────────────────────────────────────────
            RowLayout {
                spacing: 6
                Text { text: "Rating"; font.pixelSize: 12; color: textTertiary }
                Row {
                    spacing: 2
                    Repeater {
                        model: 5
                        Text {
                            text: "★"
                            font.pixelSize: 14
                            color: index < Math.round(manga ? manga.rated_avg : 0) ? accentPrimary : textTertiary
                        }
                    }
                }
                Text { text: manga ? manga.rated_avg.toFixed(1) + "/5" : "0.0"; font.pixelSize: 12; color: textSecondary }
            }
            
            // ─────────────────────────────────────────────────────────────
            // DESCRIPTION
            // ─────────────────────────────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                visible: manga && manga.description
                
                Text { text: "Description"; font.pixelSize: 12; color: textTertiary }
                Text {
                    Layout.fillWidth: true
                    text: manga ? manga.description.substring(0, 200) + (manga.description.length > 200 ? "..." : "") : ""
                    font.pixelSize: 11
                    color: textSecondary
                    wrapMode: Text.WordWrap
                    lineHeight: 1.3
                }
            }
            
            Item { height: 8 }
        }
    }
}
