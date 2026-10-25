.pragma library
// Chapter-list helpers for the Browse view.

// Case-insensitive substring match on the chapter number or title.
// A blank query matches everything.
function matches(chapter, query) {
    var q = String(query || "").trim().toLowerCase()
    if (!q) return true
    var num = String(chapter && chapter.number !== undefined ? chapter.number : "").toLowerCase()
    var title = String(chapter && chapter.title ? chapter.title : "").toLowerCase()
    return num.indexOf(q) !== -1 || title.indexOf(q) !== -1
}

// Inclusive ascending indices between the shift-click anchor and the
// clicked row. No anchor yet → just the clicked row.
function rangeIndices(anchor, index) {
    if (anchor < 0) return [index]
    var lo = Math.min(anchor, index), hi = Math.max(anchor, index)
    var out = []
    for (var i = lo; i <= hi; i++) out.push(i)
    return out
}
