.pragma library
// Downloads sidebar badge: chapters still queued or downloading.
// Immutable reducer over {jobs: {jobId: remaining}}.

function empty() { return { jobs: {} } }

function _copy(s) {
    var jobs = {}
    for (var k in s.jobs) jobs[k] = s.jobs[k]
    return { jobs: jobs }
}

function jobStarted(s, jobId, total) {
    var n = _copy(s)
    n.jobs[jobId] = Math.max(0, total | 0)
    return n
}

function chapterDone(s, jobId) {
    if (!(jobId in s.jobs)) return s
    var n = _copy(s)
    n.jobs[jobId] = Math.max(0, n.jobs[jobId] - 1)
    return n
}

// Finished, cancelled or errored: the job's leftovers stop counting.
function jobEnded(s, jobId) {
    if (!(jobId in s.jobs)) return s
    var n = _copy(s)
    delete n.jobs[jobId]
    return n
}

function count(s) {
    var total = 0
    for (var k in s.jobs) total += s.jobs[k]
    return Math.max(0, total)
}
