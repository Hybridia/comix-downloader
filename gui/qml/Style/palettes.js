.pragma library
// Theme palettes. Status colours are shared and live in Theme.qml.

var THEMES = ["ink", "neon", "ember"]

var PALETTES = {
    ink: {
        bg: "#0B0F1A", surface: "#111726", card: "#172033", elevated: "#1F2A42",
        border: "#2A3652", accent: "#FF7A93", accent2: "#E8506E", highlight: "#FFC2CF",
        cool: "#8FD3FF", textPrimary: "#F3EFE6", textSecondary: "#9AA3B8", textTertiary: "#5F6880"
    },
    neon: {
        bg: "#07060E", surface: "#100E1C", card: "#17142A", elevated: "#211C3A",
        border: "#2D2650", accent: "#FF3DA8", accent2: "#B03CFF", highlight: "#FF9BE0",
        cool: "#35F0FF", textPrimary: "#F4F0FF", textSecondary: "#9A90C0", textTertiary: "#5E5680"
    },
    ember: {
        bg: "#0A0A0C", surface: "#141419", card: "#1C1C24", elevated: "#252530",
        border: "#2A2A33", accent: "#E8A54B", accent2: "#D4873A", highlight: "#FFD93D",
        cool: "#4ECDC4", textPrimary: "#F5F5F0", textSecondary: "#8B8B99", textTertiary: "#5C5C66"
    }
}

function palette(name) {
    return PALETTES[name] || PALETTES.ink
}
