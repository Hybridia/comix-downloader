pragma Singleton
import QtQuick
import "palettes.js" as P

// Single source of colour and motion for the whole GUI. Every component
// binds its colours here, so changing SettingsBridge.theme recolours
// the app live.
QtObject {
    id: theme

    readonly property string name: typeof SettingsBridge !== "undefined" && SettingsBridge ? SettingsBridge.theme : "ink"
    readonly property var _p: P.palette(name)

    // Palette
    readonly property color bg: _p.bg
    readonly property color surface: _p.surface
    readonly property color card: _p.card
    readonly property color elevated: _p.elevated
    readonly property color border: _p.border
    readonly property color accent: _p.accent
    readonly property color accent2: _p.accent2
    readonly property color highlight: _p.highlight
    readonly property color cool: _p.cool
    readonly property color textPrimary: _p.textPrimary
    readonly property color textSecondary: _p.textSecondary
    readonly property color textTertiary: _p.textTertiary
    readonly property color glow: Qt.rgba(accent.r, accent.g, accent.b, 0.45)

    // Status colours — shared by every theme
    readonly property color success: "#7CB342"
    readonly property color error: "#E57373"
    readonly property color warning: "#FFB74D"
    readonly property color info: "#64B5F6"

    // Motion
    readonly property bool animations: typeof SettingsBridge !== "undefined" && SettingsBridge ? SettingsBridge.animationsEnabled : true
    readonly property bool ambient: typeof SettingsBridge !== "undefined" && SettingsBridge ? SettingsBridge.ambientGlow : true
    // Software rendering (--cpu): no blur, masks or shader effects.
    readonly property bool software: typeof SoftwareRendering !== "undefined" && SoftwareRendering

    // Duration helper: every animation goes through this so the
    // Animations switch can collapse motion to instant.
    function dur(ms) { return animations ? ms : 0 }

    readonly property var themes: P.THEMES
}
